"""Home Assistant integration tests for the DC (climate) module.

Covers the config flow (menu -> climate), entity creation, and the full
multi-module triangle: DC in cool mode publishes ``request_solar_shield`` to the
shared SDHB hub, and a DS shutter sharing that hub clamps its cover.
"""

from homeassistant.components.climate import HVACMode
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_TEMPERATURE
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from custom_components.dynamic_home import const, zones

CLIMATE = {
    const.CONF_NAME: "Salon",
    const.CONF_MODULE: const.MODULE_CLIMATE,
    const.CONF_DC_T_INT: "sensor.salon_temp",
    const.CONF_DC_T_EXT: "sensor.ext_temp",
    const.CONF_DC_TARGET: "ds",
}

SHUTTER = {
    const.CONF_NAME: "Persiana",
    const.CONF_MODULE: const.MODULE_SHUTTER,
    const.CONF_COVER: "cover.salon_real",
    const.CONF_FACADE_AZIMUTH: 180.0,
}


def _seed(hass: HomeAssistant) -> None:
    hass.states.async_set("sensor.salon_temp", "27")
    hass.states.async_set("sensor.ext_temp", "33")
    hass.states.async_set("sun.sun", "above_horizon",
                          {"azimuth": 180, "elevation": 30})
    hass.states.async_set("cover.salon_real", "open", {"supported_features": 15})


async def _add(hass: HomeAssistant, data: dict, title: str) -> MockConfigEntry:
    entry = MockConfigEntry(domain=const.DOMAIN, data=data, title=title)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_dc_auto_forecast_source_from_dynamic_weather(
        hass: HomeAssistant) -> None:
    """With no zone weather configured, DC's forecast bias auto-uses the module's."""
    _seed(hass)
    entry = await _add(hass, CLIMATE, "Salon")     # no CONF_DC_WEATHER set
    co = hass.data[const.DOMAIN][entry.entry_id]

    assert co._forecast_source() is None           # nothing published yet
    hass.data[const.DOMAIN][const.DATA_WEATHER] = {
        "source": "weather.casa", "alert": False}
    assert co._forecast_source() == "weather.casa"

    # An explicit per-zone weather overrides the auto source.
    co2 = hass.data[const.DOMAIN][
        (await _add(hass, {**CLIMATE, const.CONF_NAME: "Salon2",
                           const.CONF_DC_T_INT: "sensor.salon_temp",
                           const.CONF_DC_WEATHER: "weather.zona"},
                    "Salon2")).entry_id]
    assert co2._forecast_source() == "weather.zona"


async def test_climate_config_flow(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        const.DOMAIN, context={"source": "user"})
    assert result["type"] == FlowResultType.MENU

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "climate"})
    # No zone exists yet -> skip the copy picker, straight to the entity form.
    assert result["step_id"] == "climate_form"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={const.CONF_NAME: "Salon",
                    const.CONF_DC_T_INT: "sensor.salon_temp",
                    const.CONF_DC_TARGET: "ds"})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][const.CONF_MODULE] == const.MODULE_CLIMATE


async def test_climate_create_copies_from_template(hass: HomeAssistant) -> None:
    """Adding a 2nd zone can copy a sibling: form pre-filled + options cloned."""
    _seed(hass)
    hass.states.async_set("sensor.cocina_temp", "26")
    src = MockConfigEntry(
        domain=const.DOMAIN, title="Salón",
        data={**CLIMATE, const.CONF_DC_T_INT: "sensor.salon_temp"},
        options={"base_heat_day": 21.5})
    src.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        const.DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "climate"})
    # A sibling exists -> the copy picker shows first.
    assert result["step_id"] == "climate"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"copy_from": src.entry_id})
    assert result["step_id"] == "climate_form"

    # Only the indoor sensor (and name) differ; options come from the template.
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={const.CONF_NAME: "Cocina",
                    const.CONF_DC_T_INT: "sensor.cocina_temp",
                    const.CONF_DC_TARGET: "ds"})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][const.CONF_DC_T_INT] == "sensor.cocina_temp"
    assert result["options"] == {"base_heat_day": 21.5}   # tunables cloned
    await hass.async_block_till_done()


async def test_setup_creates_climate(hass: HomeAssistant) -> None:
    _seed(hass)
    entry = await _add(hass, CLIMATE, "Salon")
    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get("climate.salon") is not None


async def test_cold_surface_condensation_breakdown(hass: HomeAssistant) -> None:
    """A floor/water temp drives the cold-surface condensation check + sensors."""
    from homeassistant.helpers import entity_registry as er
    _seed(hass)
    hass.states.async_set("sensor.salon_rh", "65")
    hass.states.async_set("sensor.floor", "17.2")
    cfg = {**CLIMATE, const.CONF_DC_HUMIDITY: "sensor.salon_rh",
           const.CONF_DC_WATER_TEMP: "sensor.floor"}
    entry = await _add(hass, cfg, "Salon")
    co = hass.data[const.DOMAIN][entry.entry_id]

    await hass.services.async_call(
        "climate", "set_hvac_mode",
        {"entity_id": "climate.salon", "hvac_mode": HVACMode.COOL}, blocking=True)
    await co.async_refresh()
    await hass.async_block_till_done()

    # Floor 17.2 vs dew point ~17.0 -> real spread ~0.2 < 0.3 margin -> WET -> off.
    assert co.has_water() is True
    assert co.floor_temp_c == 17.2
    assert co.cond_spread_real is not None and co.cond_spread_real < 0.3
    assert co.cond_margin_corrected < 0          # corrected margin negative -> wet
    assert co.dew_risk_active is True            # zone stopped on condensation

    # The three breakdown sensors exist (gated on the floor temp).
    reg = er.async_get(hass)
    for key in ("floor_temp", "cond_spread", "cond_margin"):
        assert reg.async_get_entity_id(
            "sensor", const.DOMAIN, f"{entry.entry_id}_{key}") is not None

    # Warmer floor -> spread above the margin -> dry -> the gate releases.
    hass.states.async_set("sensor.floor", "21.0")
    await co.async_refresh()
    await hass.async_block_till_done()
    assert co.dew_risk_active is False


async def test_cooling_without_surface_sensor_warns(hass: HomeAssistant) -> None:
    """Radiant zone cooling without a floor temp -> warning + honest binary."""
    from homeassistant.helpers import entity_registry as er
    from homeassistant.helpers import issue_registry as ir
    _seed(hass)
    hass.states.async_set("sensor.salon_rh", "60")
    # No floor/water temp; emitter declared as radiant underfloor (F26 -> options).
    data = {**CLIMATE, const.CONF_DC_HUMIDITY: "sensor.salon_rh"}
    opts = {const.CONF_GENERATOR: "heatpump_air_water",
            const.CONF_EMISSION: "underfloor"}
    entry = await _add_opts(hass, data, "Salon", opts)
    co = hass.data[const.DOMAIN][entry.entry_id]

    await hass.services.async_call(
        "climate", "set_hvac_mode",
        {"entity_id": "climate.salon", "hvac_mode": HVACMode.COOL}, blocking=True)
    await co.async_refresh()
    await hass.async_block_till_done()

    # Air-only protection on a cold surface -> flagged, repair raised, the binary
    # refuses to claim "dry" (unavailable).
    assert co.cond_protection == "air"
    assert co.cond_unprotected is True
    assert ir.async_get(hass).async_get_issue(
        const.DOMAIN, co._cond_issue_id) is not None
    eid = er.async_get(hass).async_get_entity_id(
        "binary_sensor", const.DOMAIN, f"{entry.entry_id}_dew_risk")
    assert hass.states.get(eid).state == "unavailable"

    # Leaving cooling -> nothing to protect -> warning cleared.
    await hass.services.async_call(
        "climate", "set_hvac_mode",
        {"entity_id": "climate.salon", "hvac_mode": HVACMode.HEAT}, blocking=True)
    await co.async_refresh()
    await hass.async_block_till_done()
    assert co.cond_unprotected is False
    assert ir.async_get(hass).async_get_issue(
        const.DOMAIN, co._cond_issue_id) is None


async def test_cooling_non_radiant_emitter_not_warned(hass: HomeAssistant) -> None:
    """A declared non-radiant emitter (split) is fine on the air check -> no warn."""
    from homeassistant.helpers import issue_registry as ir
    _seed(hass)
    hass.states.async_set("sensor.salon_rh", "60")
    data = {**CLIMATE, const.CONF_DC_HUMIDITY: "sensor.salon_rh"}
    opts = {const.CONF_GENERATOR: "heatpump_air_air", const.CONF_EMISSION: "split"}
    entry = await _add_opts(hass, data, "Salon", opts)
    co = hass.data[const.DOMAIN][entry.entry_id]
    await hass.services.async_call(
        "climate", "set_hvac_mode",
        {"entity_id": "climate.salon", "hvac_mode": HVACMode.COOL}, blocking=True)
    await co.async_refresh()
    await hass.async_block_till_done()
    assert co.cond_protection == "air"
    assert co.cond_unprotected is False
    assert ir.async_get(hass).async_get_issue(
        const.DOMAIN, co._cond_issue_id) is None


async def test_full_triangle_dc_drives_ds(hass: HomeAssistant) -> None:
    """DC (cool) -> bus request_solar_shield -> DS cover clamps to 30%."""
    _seed(hass)
    dc_entry = await _add(hass, CLIMATE, "Salon")
    ds_entry = await _add(hass, SHUTTER, "Persiana")

    dc = hass.data[const.DOMAIN][dc_entry.entry_id]
    ds = hass.data[const.DOMAIN][ds_entry.entry_id]

    # Put the climate zone into cooling.
    await hass.services.async_call(
        "climate", "set_hvac_mode",
        {"entity_id": "climate.salon", "hvac_mode": HVACMode.COOL},
        blocking=True)
    await hass.async_block_till_done()

    # DC published a solar-shield intent to the bus...
    assert dc.data.published_intent == "request_solar_shield"

    # ...which DS consumes on its next evaluation, clamping the cover.
    await ds.async_refresh()
    await hass.async_block_till_done()
    assert ds.data.reason == "sdhb_solar_shield"
    assert ds.data.pos == 30
    assert hass.states.get("cover.persiana").attributes["current_position"] == 30


async def test_climate_manual_setpoint_is_override(hass: HomeAssistant) -> None:
    _seed(hass)
    await _add(hass, CLIMATE, "Salon")
    await hass.services.async_call(
        "climate", "set_temperature",
        {"entity_id": "climate.salon", ATTR_TEMPERATURE: 21.0}, blocking=True)
    await hass.async_block_till_done()
    state = hass.states.get("climate.salon")
    assert state.attributes["temperature"] == 21.0
    assert state.attributes["reason"] == "override"


# --- F27: real heating/cooling demand signal ---
async def test_real_demand_valve_reflects_relay(hass: HomeAssistant) -> None:
    """Source (c): the valve/relay state is reflected regardless of DC's command."""
    from homeassistant.helpers import entity_registry as er
    _seed(hass)
    hass.states.async_set("switch.valve", "on")
    entry = await _add(hass, {**CLIMATE, const.CONF_DC_VALVE: "switch.valve"}, "Salon")
    co = hass.data[const.DOMAIN][entry.entry_id]

    # Backup thermostat opened the relay even though the zone is OFF -> reflected.
    assert co.has_real_demand() is True
    assert co.real_demand_source == "valve"
    assert co.real_demand_open is True

    eid = er.async_get(hass).async_get_entity_id(
        "binary_sensor", const.DOMAIN, f"{entry.entry_id}_real_demand")
    assert eid is not None
    st = hass.states.get(eid)
    assert st.state == "on" and st.attributes["source"] == "valve"


async def test_real_demand_valve_power_threshold(hass: HomeAssistant) -> None:
    _seed(hass)
    hass.states.async_set("sensor.valve_power", "120")     # W, > valve_power_min
    entry = await _add(hass, {**CLIMATE, const.CONF_DC_VALVE: "sensor.valve_power"},
                       "Salon")
    co = hass.data[const.DOMAIN][entry.entry_id]
    assert co.real_demand_open is True
    hass.states.async_set("sensor.valve_power", "0")
    assert co.real_demand_open is False


async def test_real_demand_helper_priority(hass: HomeAssistant) -> None:
    """Source (b): the per-mode demand helper drives valve_open."""
    _seed(hass)
    hass.states.async_set("input_boolean.heat_demand", "on")
    entry = await _add(
        hass, {**CLIMATE, const.CONF_DC_DEMAND_HEAT: "input_boolean.heat_demand"},
        "Salon")
    co = hass.data[const.DOMAIN][entry.entry_id]
    await hass.services.async_call(
        "climate", "set_hvac_mode",
        {"entity_id": "climate.salon", "hvac_mode": HVACMode.HEAT}, blocking=True)
    await hass.async_block_till_done()
    assert co.real_demand_source == "helper"
    assert co.real_demand_open is True


async def test_real_demand_absent_falls_back_to_inference(
        hass: HomeAssistant) -> None:
    from homeassistant.helpers import entity_registry as er
    _seed(hass)
    entry = await _add(hass, CLIMATE, "Salon")
    co = hass.data[const.DOMAIN][entry.entry_id]

    assert co.has_real_demand() is False
    assert co.real_demand_source == "inferred"
    assert co.real_demand_open is None
    eid = er.async_get(hass).async_get_entity_id(
        "binary_sensor", const.DOMAIN, f"{entry.entry_id}_real_demand")
    assert eid is None


# --- F22: mold-risk index ---
async def test_mold_index_arms_alert_dry_request_and_dehumidifier(
        hass: HomeAssistant) -> None:
    from homeassistant.helpers import entity_registry as er
    from homeassistant.helpers import issue_registry as ir
    on_calls = async_mock_service(hass, "homeassistant", "turn_on")
    _seed(hass)
    hass.states.async_set("sensor.salon_rh", "85")          # high RH
    hass.states.async_set("switch.dehum", "off")
    entry = await _add(hass, {
        **CLIMATE,
        const.CONF_DC_HUMIDITY: "sensor.salon_rh",
        const.CONF_DC_DEHUMIDIFIER: "switch.dehum",
    }, "Salon")
    co = hass.data[const.DOMAIN][entry.entry_id]

    # Mold index sensor exists (RH source present).
    assert co.has_mold() is True
    assert er.async_get(hass).async_get_entity_id(
        "sensor", const.DOMAIN, f"{entry.entry_id}_mold_index") is not None

    # Force the index over the arm threshold and re-evaluate.
    co.mold_index = co._cfg().mold_on_h + 1
    await co.async_refresh()
    await hass.async_block_till_done()

    assert co._mold_active is True
    # Repairs issue raised, dehumidifier turned on, request_dry on the bus.
    assert ir.async_get(hass).async_get_issue(const.DOMAIN, co._mold_issue_id)
    assert any(c.data["entity_id"] == "switch.dehum" for c in on_calls)
    assert co.hub.winner("dv") == "request_dry"


async def test_mold_index_absent_without_rh(hass: HomeAssistant) -> None:
    from homeassistant.helpers import entity_registry as er
    _seed(hass)
    entry = await _add(hass, CLIMATE, "Salon")     # no CONF_DC_HUMIDITY
    co = hass.data[const.DOMAIN][entry.entry_id]
    assert co.has_mold() is False
    assert er.async_get(hass).async_get_entity_id(
        "sensor", const.DOMAIN, f"{entry.entry_id}_mold_index") is None


# --- F36: hardware mirror sensors (opt-in, stable per-role) ---
async def _add_opts(hass: HomeAssistant, data: dict, title: str,
                    options: dict) -> MockConfigEntry:
    entry = MockConfigEntry(domain=const.DOMAIN, data=data, title=title,
                            options=options)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_mirror_sensors_off_by_default(hass: HomeAssistant) -> None:
    from homeassistant.helpers import entity_registry as er
    _seed(hass)
    entry = await _add(hass, CLIMATE, "Salon")
    reg = er.async_get(hass)
    assert reg.async_get_entity_id(
        "sensor", const.DOMAIN, f"{entry.entry_id}_mirror_dc_t_int") is None


async def test_mirror_sensors_created_when_enabled(hass: HomeAssistant) -> None:
    from homeassistant.helpers import entity_registry as er
    _seed(hass)
    hass.states.async_set("sensor.salon_temp", "21.5",
                          {"unit_of_measurement": "°C",
                           "device_class": "temperature"})
    entry = await _add_opts(hass, CLIMATE, "Salon",
                            {const.CONF_EXPOSE_MIRRORS: True})
    reg = er.async_get(hass)
    mirror = reg.async_get_entity_id(
        "sensor", const.DOMAIN, f"{entry.entry_id}_mirror_dc_t_int")
    assert mirror is not None
    st = hass.states.get(mirror)
    assert st.state == "21.5"
    assert st.attributes.get("unit_of_measurement") == "°C"
    assert st.attributes.get("device_class") == "temperature"
    # No mirror for an unconfigured role.
    assert reg.async_get_entity_id(
        "sensor", const.DOMAIN, f"{entry.entry_id}_mirror_dc_wind") is None


async def test_mirror_toggle_reloads_entry(hass: HomeAssistant) -> None:
    from homeassistant.helpers import entity_registry as er
    _seed(hass)
    entry = await _add(hass, CLIMATE, "Salon")            # off
    reg = er.async_get(hass)
    uid = f"{entry.entry_id}_mirror_dc_t_int"
    assert reg.async_get_entity_id("sensor", const.DOMAIN, uid) is None
    # Flip the option -> the entry reloads and the mirror appears.
    hass.config_entries.async_update_entry(
        entry, options={const.CONF_EXPOSE_MIRRORS: True})
    await hass.async_block_till_done()
    assert reg.async_get_entity_id("sensor", const.DOMAIN, uid) is not None


# --- F31: adjacent warm-space advisory ---
async def test_adjacent_advisory_heat_and_cool(hass: HomeAssistant) -> None:
    from homeassistant.helpers import entity_registry as er
    events = []
    hass.bus.async_listen(const.EVENT_ADJACENT, lambda e: events.append(e.data))
    _seed(hass)
    hass.states.async_set("sensor.terraza", "50")
    hass.states.async_set("binary_sensor.puerta", "off")
    entry = await _add(hass, {
        **CLIMATE,
        const.CONF_DC_ADJ_TEMP: "sensor.terraza",
        const.CONF_DC_ADJ_DOOR: "binary_sensor.puerta",
    }, "Salon")
    co = hass.data[const.DOMAIN][entry.entry_id]

    assert co.has_adjacent() is True
    assert er.async_get(hass).async_get_entity_id(
        "sensor", const.DOMAIN, f"{entry.entry_id}_adjacent_advice") is not None

    # Heat + terrace much warmer + door closed -> advise opening for free gain.
    await hass.services.async_call(
        "climate", "set_hvac_mode",
        {"entity_id": "climate.salon", "hvac_mode": HVACMode.HEAT}, blocking=True)
    await co.async_refresh()
    await hass.async_block_till_done()
    assert co.adjacent_advice == "open_gain"
    assert events and events[-1]["advice"] == "open_gain"

    # Cool + terrace hot + door OPEN -> alarm (heat leaking in).
    await hass.services.async_call(
        "climate", "set_hvac_mode",
        {"entity_id": "climate.salon", "hvac_mode": HVACMode.COOL}, blocking=True)
    hass.states.async_set("binary_sensor.puerta", "on")
    await co.async_refresh()
    await hass.async_block_till_done()
    assert co.adjacent_advice == "close_alarm"
    assert events[-1]["advice"] == "close_alarm"


async def test_adjacent_absent_without_sensor(hass: HomeAssistant) -> None:
    from homeassistant.helpers import entity_registry as er
    _seed(hass)
    entry = await _add(hass, CLIMATE, "Salon")     # no CONF_DC_ADJ_TEMP
    co = hass.data[const.DOMAIN][entry.entry_id]
    assert co.has_adjacent() is False
    assert er.async_get(hass).async_get_entity_id(
        "sensor", const.DOMAIN, f"{entry.entry_id}_adjacent_advice") is None


# --- F20: open-window inference (latch / recovery), driven with injected time ---
async def test_window_inference_arm_and_stabilise(hass: HomeAssistant) -> None:
    _seed(hass)
    entry = await _add(hass, CLIMATE, "Salon")     # no CONF_DC_WINDOW
    co = hass.data[const.DOMAIN][entry.entry_id]
    cfg = co._cfg()
    assert co.has_window_infer() is True

    t = 1000.0
    # Anomaly (heating but temp dropping fast): debounced, not armed yet.
    assert co._infer_window(cfg, "heat", 20.0, -3.0, t) is False
    assert co._infer_window(cfg, "heat", 20.0, -3.0, t + 60) is False
    # Past the confirm window -> armed.
    armed_t = t + cfg.window_confirm_min * 60 + 1
    assert co._infer_window(cfg, "heat", 20.0, -3.0, armed_t) is True
    # Temperature stabilises: the recovery window counts from this moment.
    stable_t = armed_t + 60
    assert co._infer_window(cfg, "heat", 20.0, 0.0, stable_t) is True
    assert co._infer_window(
        cfg, "heat", 20.0, 0.0,
        stable_t + cfg.window_release_min * 60 + 1) is False


async def test_window_inference_safety_timeout(hass: HomeAssistant) -> None:
    _seed(hass)
    entry = await _add(hass, CLIMATE, "Salon")
    co = hass.data[const.DOMAIN][entry.entry_id]
    cfg = co._cfg()
    co._infer_window(cfg, "heat", 20.0, -3.0, 0.0)
    assert co._infer_window(cfg, "heat", 20.0, -3.0,
                            cfg.window_confirm_min * 60 + 1) is True
    # Anomaly persists, but the safety timeout forces recovery anyway.
    out = co._infer_window(
        cfg, "heat", 20.0, -3.0,
        co._window_armed_ts + cfg.window_max_lockout_min * 60 + 1)
    assert out is False


async def test_window_inference_disabled_with_sensor(hass: HomeAssistant) -> None:
    _seed(hass)
    hass.states.async_set("binary_sensor.ventana", "off")
    entry = await _add(hass, {**CLIMATE,
                              const.CONF_DC_WINDOW: "binary_sensor.ventana"}, "Salon")
    co = hass.data[const.DOMAIN][entry.entry_id]
    cfg = co._cfg()
    assert co.has_window_infer() is False
    co._infer_window(cfg, "heat", 20.0, -10.0, 100.0)
    assert co._infer_window(cfg, "heat", 20.0, -10.0, 100_000.0) is False


async def test_window_lockout_and_vacation(hass: HomeAssistant) -> None:
    """An open window forces OFF; vacation switch feeds the engine."""
    _seed(hass)
    hass.states.async_set("binary_sensor.ventana", "off")
    entry = await _add(hass, {
        const.CONF_NAME: "Salon", const.CONF_MODULE: const.MODULE_CLIMATE,
        const.CONF_DC_T_INT: "sensor.salon_temp",
        const.CONF_DC_WINDOW: "binary_sensor.ventana",
        const.CONF_DC_TARGET: "ds",
    }, "Salon")
    co = hass.data[const.DOMAIN][entry.entry_id]

    await hass.services.async_call(
        "climate", "set_hvac_mode",
        {"entity_id": "climate.salon", "hvac_mode": HVACMode.HEAT}, blocking=True)
    await co.async_refresh()
    await hass.async_block_till_done()
    assert co.data.action == "heat"

    # Open the window -> lockout -> OFF.
    hass.states.async_set("binary_sensor.ventana", "on")
    await co.async_refresh()
    await hass.async_block_till_done()
    assert co.data.action == "off" and co.data.reason == "off_window"

    # Vacation switch is registered and feeds the engine.
    from homeassistant.helpers import entity_registry as er
    assert er.async_get(hass).async_get_entity_id(
        "switch", const.DOMAIN, f"{entry.entry_id}_vacation") is not None
    co.vacation_enabled = True
    hass.states.async_set("binary_sensor.ventana", "off")
    await co.async_refresh()
    await hass.async_block_till_done()
    assert co.data.action == "heat"  # vacation uses the vacation base setpoint


async def test_observability_sensors(hass: HomeAssistant) -> None:
    """DC exposes pipeline values as diagnostic sensors for dashboards."""
    from homeassistant.helpers import entity_registry as er
    _seed(hass)
    entry = await _add(hass, {
        const.CONF_NAME: "Salon", const.CONF_MODULE: const.MODULE_CLIMATE,
        const.CONF_DC_T_INT: "sensor.salon_temp",
        const.CONF_DC_T_EXT: "sensor.ext_temp", const.CONF_DC_TARGET: "ds",
    }, "Salon")
    co = hass.data[const.DOMAIN][entry.entry_id]

    reg = er.async_get(hass)
    for key in ("target", "base", "target_raw", "dew_point", "reason",
                "bias_exterior", "bias_vmc", "bias_trend", "bias_brake",
                "bias_forecast", "bias_facade", "sdhb_bias", "mods_total"):
        assert reg.async_get_entity_id(
            "sensor", const.DOMAIN, f"{entry.entry_id}_{key}") is not None, key
    assert reg.async_get_entity_id(
        "binary_sensor", const.DOMAIN, f"{entry.entry_id}_dew_risk") is not None

    # In heat the pipeline breakdown is populated.
    await hass.services.async_call(
        "climate", "set_hvac_mode",
        {"entity_id": "climate.salon", "hvac_mode": HVACMode.HEAT}, blocking=True)
    await co.async_refresh()
    assert "bias_exterior" in co.data.details
    assert co.data.details["base"] is not None


# --- F06: energy (kWh) — accrues while calling for heat/cool, meter overrides ---
async def test_dc_energy_accumulates_while_on(hass: HomeAssistant) -> None:
    from homeassistant.helpers import entity_registry as er
    _seed(hass)
    entry = await _add(hass, CLIMATE, "Salon")
    co = hass.data[const.DOMAIN][entry.entry_id]
    cfg = co._cfg()

    # Calling for heat, no meter -> est_w_on (1000 W) for one hour = 1 kWh.
    co.hvac_mode = "heat"
    co._energy_ts = 1000.0
    co._accumulate_energy(cfg, 1000.0 + 3600.0)
    assert abs(co.energy_kwh - 1.0) < 1e-9

    # Idle -> no further accrual.
    co.hvac_mode = "off"
    co._energy_ts = 5000.0
    before = co.energy_kwh
    co._accumulate_energy(cfg, 5000.0 + 3600.0)
    assert co.energy_kwh == before

    eid = er.async_get(hass).async_get_entity_id(
        "sensor", const.DOMAIN, f"{entry.entry_id}_energy")
    assert eid is not None
    assert hass.states.get(eid).attributes["device_class"] == "energy"


async def test_dc_energy_real_meter_overrides_estimate(hass: HomeAssistant) -> None:
    _seed(hass)
    hass.states.async_set("sensor.dc_power", "800")
    entry = await _add(
        hass, {**CLIMATE, const.CONF_POWER_METER: "sensor.dc_power"}, "Salon")
    co = hass.data[const.DOMAIN][entry.entry_id]
    # Even idle, the real meter is integrated: 800 W * 1 h = 0.8 kWh.
    co.hvac_mode = "off"
    co._energy_ts = 1000.0
    co._accumulate_energy(co._cfg(), 1000.0 + 3600.0)
    assert abs(co.energy_kwh - 0.8) < 1e-9


# --- F21: weekly scheduler — absolute base setpoint + options editor ---
_ALLDAY_BASE = {str(d): [{"start": "00:00", "value": 20.0}] for d in range(7)}


async def test_dc_schedule_sets_absolute_base(hass: HomeAssistant) -> None:
    from homeassistant.helpers import entity_registry as er
    _seed(hass)
    entry = MockConfigEntry(domain=const.DOMAIN, data=CLIMATE,
                            options={const.CONF_SCHEDULE: _ALLDAY_BASE},
                            title="Salon")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    co = hass.data[const.DOMAIN][entry.entry_id]
    co.hvac_mode = "heat"

    # Disabled by default -> auto base.
    await co.async_refresh()
    await hass.async_block_till_done()
    assert co.data.details["base_source"] == "auto"

    # Enabled -> the active slot fixes the absolute base (biases still on top).
    co.schedule_enabled = True
    await co.async_refresh()
    await hass.async_block_till_done()
    assert co.data.details["base_source"] == "schedule"
    assert co.data.details["base"] == 20.0

    # The diagnostic schedule sensor exists.
    eid = er.async_get(hass).async_get_entity_id(
        "sensor", const.DOMAIN, f"{entry.entry_id}_schedule")
    assert eid is not None


async def test_dc_schedule_editor_persists_and_copies(hass: HomeAssistant) -> None:
    _seed(hass)
    entry = await _add(hass, CLIMATE, "Salon")
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    flow = await hass.config_entries.options.async_configure(
        flow["flow_id"], {"next_step_id": "schedule"})
    flow = await hass.config_entries.options.async_configure(
        flow["flow_id"], {"day": "0"})
    flow = await hass.config_entries.options.async_configure(
        flow["flow_id"],
        {"start_1": "07:00:00", "value_1": 21.0,
         "start_2": "23:00:00", "value_2": 19.0, "copy_to": ["1", "2"]})
    await hass.async_block_till_done()
    prof = entry.options[const.CONF_SCHEDULE]
    assert prof["0"] == [{"start": "07:00", "value": 21.0},
                         {"start": "23:00", "value": 19.0}]
    assert prof["1"] == prof["0"] and prof["2"] == prof["0"]   # copied
    assert prof["3"] == []                                     # untouched


# --- F09: short-cycle protection (shared compressor aggregate) ---
async def test_anticycle_hold_idles_in_mode_not_off(
        hass: HomeAssistant) -> None:
    # v0.99.0: a protective hold must NOT turn the thermostat off — that loses the
    # heat/cool reference a DS shield reads and, on aerotermia, it wouldn't
    # re-engage cleanly. It idles IN mode: keeps heat/cool and pushes the setpoint
    # out of reach (min_temp here, default 7) so there is no demand.
    from homeassistant.components.climate import ATTR_HVAC_MODE
    from homeassistant.util import dt as dt_util

    from custom_components.dynamic_home.anticycle import CompressorState
    _seed(hass)
    hass.states.async_set("climate.real", "off")
    entry = await _add(hass, {**CLIMATE, const.CONF_DC_CLIMATE: "climate.real"},
                       "Salon")
    # Mock AFTER setup: forwarding the climate platform loads the climate
    # component, which would otherwise re-register the real service over the mock.
    mode_calls = async_mock_service(hass, "climate", "set_hvac_mode")
    temp_calls = async_mock_service(hass, "climate", "set_temperature")
    co = hass.data[const.DOMAIN][entry.entry_id]
    co.hvac_mode = "heat"
    co.anticycle_enabled = True

    # Simulate the shared compressor having just stopped (within min OFF).
    ac = hass.data[const.DOMAIN]["_anticycle"]
    ac.state = CompressorState(on=False, last_off_ts=dt_util.utcnow().timestamp())
    await co.async_refresh()
    await hass.async_block_till_done()

    assert co.anticycle_hold is True
    assert co.anticycle_reason == "anticycle_min_off_hold"
    # Never OFF: the thermostat stays in HEAT so the reference survives...
    assert not any(c.data.get(ATTR_HVAC_MODE) == HVACMode.OFF for c in mode_calls)
    assert any(c.data.get(ATTR_HVAC_MODE) == HVACMode.HEAT for c in mode_calls)
    # ...idled by pushing the setpoint to the low end (min_temp / default 7).
    assert any(c.data.get(ATTR_TEMPERATURE) == 7 for c in temp_calls)


async def test_user_off_still_drives_thermostat_off(hass: HomeAssistant) -> None:
    # Only protective holds idle-in-mode; a genuine off (user turned the zone off)
    # still commands the real thermostat OFF.
    from homeassistant.components.climate import ATTR_HVAC_MODE
    _seed(hass)
    hass.states.async_set("climate.real", "heat")
    entry = await _add(hass, {**CLIMATE, const.CONF_DC_CLIMATE: "climate.real"},
                       "Salon")
    mode_calls = async_mock_service(hass, "climate", "set_hvac_mode")
    async_mock_service(hass, "climate", "set_temperature")
    co = hass.data[const.DOMAIN][entry.entry_id]
    co.hvac_mode = "off"
    await co.async_refresh()
    await hass.async_block_till_done()
    assert any(c.data.get(ATTR_HVAC_MODE) == HVACMode.OFF for c in mode_calls)


async def test_anticycle_disabled_does_not_hold(hass: HomeAssistant) -> None:
    from homeassistant.util import dt as dt_util

    from custom_components.dynamic_home.anticycle import CompressorState
    _seed(hass)
    entry = await _add(hass, CLIMATE, "Salon")
    co = hass.data[const.DOMAIN][entry.entry_id]
    co.hvac_mode = "heat"
    ac = hass.data[const.DOMAIN]["_anticycle"]
    ac.state = CompressorState(on=False, last_off_ts=dt_util.utcnow().timestamp())

    await co.async_refresh()
    await hass.async_block_till_done()
    assert co.anticycle_hold is False          # opt-in: off by default
    assert not ac.participates(co.entry.entry_id)  # not part of the aggregate


# --- F26: installation type (generator × distribution × emission) ---
async def test_install_sensor_absent_until_declared(hass: HomeAssistant) -> None:
    from homeassistant.helpers import entity_registry as er
    _seed(hass)
    entry = await _add(hass, CLIMATE, "Salon")
    co = hass.data[const.DOMAIN][entry.entry_id]
    assert co.has_install() is False
    assert co.install_profile is None
    assert er.async_get(hass).async_get_entity_id(
        "sensor", const.DOMAIN, f"{entry.entry_id}_install") is None


async def test_install_profile_and_sensor_individual_heatpump(
        hass: HomeAssistant) -> None:
    from homeassistant.helpers import entity_registry as er
    _seed(hass)
    entry = await _add_opts(hass, CLIMATE, "Salon", {
        const.CONF_GENERATOR: "heatpump_air_water",
        const.CONF_DISTRIBUTION: "individual",
        const.CONF_EMISSION: "underfloor"})
    co = hass.data[const.DOMAIN][entry.entry_id]
    assert co.has_install()
    assert co.install_profile == {"inertia": "high", "compressor": True,
                                  "peak": True, "community": False}
    eid = er.async_get(hass).async_get_entity_id(
        "sensor", const.DOMAIN, f"{entry.entry_id}_install")
    assert eid is not None
    st = hass.states.get(eid)
    assert st.state == "heatpump_air_water/individual/underfloor"
    assert st.attributes["compressor"] is True
    assert st.attributes["community"] is False


async def test_install_central_shared_is_community(hass: HomeAssistant) -> None:
    _seed(hass)
    entry = await _add_opts(hass, CLIMATE, "Salon", {
        const.CONF_GENERATOR: "gas_boiler",
        const.CONF_DISTRIBUTION: "central_shared",
        const.CONF_EMISSION: "radiators"})
    co = hass.data[const.DOMAIN][entry.entry_id]
    assert co.install_profile == {"inertia": "medium", "compressor": False,
                                  "peak": False, "community": True}


async def test_install_wizard_stores_triple_and_preloads_defaults(
        hass: HomeAssistant) -> None:
    _seed(hass)
    entry = await _add(hass, CLIMATE, "Salon")
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    flow = await hass.config_entries.options.async_configure(
        flow["flow_id"], {"next_step_id": "install"})
    assert flow["step_id"] == "install"
    # Pick an individual heat pump -> distribution step is shown.
    flow = await hass.config_entries.options.async_configure(
        flow["flow_id"], {"generator": "heatpump_air_water"})
    assert flow["step_id"] == "install_dist"
    flow = await hass.config_entries.options.async_configure(
        flow["flow_id"], {"distribution": "individual"})
    assert flow["step_id"] == "install_emission"
    flow = await hass.config_entries.options.async_configure(
        flow["flow_id"], {"emission": "underfloor"})
    await hass.async_block_till_done()
    o = entry.options
    assert o[const.CONF_GENERATOR] == "heatpump_air_water"
    assert o[const.CONF_DISTRIBUTION] == "individual"
    assert o[const.CONF_EMISSION] == "underfloor"
    # High-inertia defaults were pre-loaded (and are valid option keys).
    assert o["lead_base_h"] == 2.0
    assert o["anticycle_min_on_s"] == 900.0


async def test_install_wizard_skips_distribution_for_forced_individual(
        hass: HomeAssistant) -> None:
    _seed(hass)
    entry = await _add(hass, CLIMATE, "Salon")
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    flow = await hass.config_entries.options.async_configure(
        flow["flow_id"], {"next_step_id": "install"})
    # Direct electric is always individual -> the distribution step is skipped.
    flow = await hass.config_entries.options.async_configure(
        flow["flow_id"], {"generator": "electric_direct"})
    assert flow["step_id"] == "install_emission"
    flow = await hass.config_entries.options.async_configure(
        flow["flow_id"], {"emission": "convectors"})
    await hass.async_block_till_done()
    co = hass.data[const.DOMAIN][entry.entry_id]
    assert entry.options[const.CONF_DISTRIBUTION] == "individual"
    assert co.install_profile["peak"] is True
    assert co.install_profile["compressor"] is False


# --- F09 gating by the F26 install profile ---
async def _compressor_held(hass, install_opts):
    """Seed the shared compressor within min-OFF and return the refreshed zone."""
    from homeassistant.util import dt as dt_util

    from custom_components.dynamic_home.anticycle import CompressorState
    _seed(hass)
    entry = await _add_opts(hass, CLIMATE, "Salon", install_opts)
    co = hass.data[const.DOMAIN][entry.entry_id]
    co.hvac_mode = "heat"
    co.anticycle_enabled = True
    ac = hass.data[const.DOMAIN]["_anticycle"]
    ac.state = CompressorState(on=False, last_off_ts=dt_util.utcnow().timestamp())
    await co.async_refresh()
    await hass.async_block_till_done()
    return entry, co, ac


async def test_anticycle_gated_off_for_non_compressor_install(
        hass: HomeAssistant) -> None:
    # Gas boiler: no compressor -> F09 does not engage despite the switch.
    entry, co, ac = await _compressor_held(hass, {
        const.CONF_GENERATOR: "gas_boiler",
        const.CONF_DISTRIBUTION: "individual",
        const.CONF_EMISSION: "radiators"})
    assert co.anticycle_hold is False
    assert not ac.participates(entry.entry_id)


async def test_anticycle_gated_off_for_community(hass: HomeAssistant) -> None:
    # Communal heat pump: the building owns the compressor -> F09 off.
    entry, co, ac = await _compressor_held(hass, {
        const.CONF_GENERATOR: "heatpump_air_water",
        const.CONF_DISTRIBUTION: "central_shared",
        const.CONF_EMISSION: "underfloor"})
    assert co.anticycle_hold is False
    assert not ac.participates(entry.entry_id)


async def test_anticycle_active_for_individual_compressor(
        hass: HomeAssistant) -> None:
    # Individual heat pump: compressor under the occupant's control -> F09 holds.
    entry, co, ac = await _compressor_held(hass, {
        const.CONF_GENERATOR: "heatpump_air_water",
        const.CONF_DISTRIBUTION: "individual",
        const.CONF_EMISSION: "underfloor"})
    assert co.anticycle_hold is True
    assert ac.participates(entry.entry_id)


# --- F03 electrical-peak staging (DC) ---
async def test_peak_staggers_electric_zones(hass: HomeAssistant) -> None:
    _seed(hass)
    hass.states.async_set("sensor.b_temp", "18")
    opts = {const.CONF_GENERATOR: "electric_direct",
            const.CONF_EMISSION: "convectors",
            "peak_max_zones": 1, "peak_stagger_s": 0,
            "peak_comfort_bypass_c": 0}      # isolate budget gating from F03 bypass
    a = await _add_opts(hass, CLIMATE, "A", opts)
    b = await _add_opts(hass, {**CLIMATE, const.CONF_NAME: "B",
                               const.CONF_DC_T_INT: "sensor.b_temp"}, "B", opts)
    ca = hass.data[const.DOMAIN][a.entry_id]
    cb = hass.data[const.DOMAIN][b.entry_id]
    ca.hvac_mode = cb.hvac_mode = "heat"
    ca.peak_enabled = cb.peak_enabled = True
    await ca.async_refresh()
    await hass.async_block_till_done()
    await cb.async_refresh()
    await hass.async_block_till_done()
    assert ca.peak_hold is False           # first electric zone granted
    assert cb.peak_hold is True            # over the 1-zone budget -> deferred
    assert cb.peak_reason == "peak_over_budget"


async def test_peak_comfort_bypass_on_severe_deviation(
        hass: HomeAssistant) -> None:
    _seed(hass)
    hass.states.async_set("sensor.salon_temp", "17")     # ~4°C below setpoint
    hass.states.async_set("sensor.b_temp", "20.6")       # near setpoint
    opts = {const.CONF_GENERATOR: "electric_direct", const.CONF_EMISSION: "convectors",
            "peak_max_zones": 1, "peak_stagger_s": 0, "base_heat_day": 21.0}
    b = await _add_opts(hass, {**CLIMATE, const.CONF_NAME: "B",
                               const.CONF_DC_T_INT: "sensor.b_temp"}, "B",
                        {**opts, "peak_comfort_bypass_c": 0})
    a = await _add_opts(hass, CLIMATE, "A", opts)         # bypass default 2.5
    ca = hass.data[const.DOMAIN][a.entry_id]
    cb = hass.data[const.DOMAIN][b.entry_id]
    ca.hvac_mode = cb.hvac_mode = "heat"
    ca.peak_enabled = cb.peak_enabled = True
    await cb.async_refresh()                              # B takes the only slot
    await hass.async_block_till_done()
    await ca.async_refresh()
    await hass.async_block_till_done()
    assert cb.peak_hold is False
    # A is over the 1-zone budget, but being ~4°C cold it bypasses the peak limit.
    assert ca.peak_hold is False
    assert ca.peak_reason == "peak_comfort_bypass"


async def test_f09_gates_only_heat_pump_emitter(hass: HomeAssistant) -> None:
    from homeassistant.util import dt as dt_util

    from custom_components.dynamic_home.anticycle import CompressorState
    _seed(hass)
    hass.states.async_set("sensor.salon_temp", "18")     # below setpoint -> demand
    hass.states.async_set("climate.hp", "off")
    hass.states.async_set("switch.gas", "off")
    ems = [{"name": "HP", "generator": "heatpump_air_water", "emission": "underfloor",
            "climate": "climate.hp", "primary_heat": True},
           {"name": "Gas", "generator": "gas_boiler", "emission": "radiators",
            "switch": "switch.gas"}]
    entry = await _add_opts(hass, CLIMATE, "Salon", {
        "emitters": ems, "support_confirm_min": 0, "base_heat_day": 21.0})
    async_mock_service(hass, "climate", "set_hvac_mode")
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "homeassistant", "turn_on")
    async_mock_service(hass, "homeassistant", "turn_off")
    co = hass.data[const.DOMAIN][entry.entry_id]
    co.hvac_mode = "heat"
    co.anticycle_enabled = True
    ac = hass.data[const.DOMAIN]["_anticycle"]
    ac.state = CompressorState(on=False, last_off_ts=dt_util.utcnow().timestamp())
    await co.async_refresh()
    await hass.async_block_till_done()
    # The profile (heat-pump primary) is a compressor install -> the guard engages.
    assert co.anticycle_hold is True
    # ...but it only holds the heat-pump emitter; the gas boiler keeps heating.
    assert co.emitter_commands["hp"]["on"] is False
    # v0.99.0: the held heat-pump emitter idles IN its demanded direction (mode
    # kept, idle flag set) instead of being commanded off.
    assert co.emitter_commands["hp"]["idle"] is True
    assert co.emitter_commands["hp"]["mode"] == "heat"
    assert co.emitter_commands["gas"]["on"] is True
    assert co.emitter_commands["gas"]["idle"] is False


async def test_peak_gated_off_for_non_electric(hass: HomeAssistant) -> None:
    _seed(hass)
    entry = await _add_opts(hass, CLIMATE, "Salon", {
        const.CONF_GENERATOR: "gas_boiler", const.CONF_EMISSION: "radiators",
        "peak_max_zones": 1})
    co = hass.data[const.DOMAIN][entry.entry_id]
    co.hvac_mode = "heat"
    co.peak_enabled = True
    await co.async_refresh()
    await hass.async_block_till_done()
    assert co.peak_hold is False           # gas is not an electrical peak load
    assert entry.entry_id not in hass.data[const.DOMAIN]["_peak_dc"].state.active


# --- Hydraulic minimum flow (weights per zone) ---
async def test_hydro_small_zone_alone_is_held(hass: HomeAssistant) -> None:
    _seed(hass)
    hass.states.async_set("sensor.salon_temp", "18")     # cold -> demands heat
    entry = await _add_opts(hass, CLIMATE, "Bano", {
        "hydro_weight": 0.5, "hydro_min_weight": 2.0})
    co = hass.data[const.DOMAIN][entry.entry_id]
    co.hvac_mode = "heat"
    co.hydro_enabled = True
    await co.async_refresh()
    await hass.async_block_till_done()
    # A lone bathroom (0.5 < 2.0) is blocked, but its demand stays registered.
    assert co.hydro_hold is True
    assert co.hydro_reason == "hydro_min_weight"
    assert co.hydro_total == 0.5


async def test_hydro_partner_weight_unlocks_and_reblocks(
        hass: HomeAssistant) -> None:
    _seed(hass)
    hass.states.async_set("sensor.salon_temp", "18")
    hass.states.async_set("sensor.b_temp", "18")
    bath = await _add_opts(hass, CLIMATE, "Bano", {
        "hydro_weight": 0.5, "hydro_min_weight": 2.0})
    salon = await _add_opts(hass, {**CLIMATE, const.CONF_NAME: "Salon2",
                                   const.CONF_DC_T_INT: "sensor.b_temp"},
                            "Salon2", {"hydro_weight": 4.0,
                                       "hydro_min_weight": 2.0})
    cb = hass.data[const.DOMAIN][bath.entry_id]
    cs = hass.data[const.DOMAIN][salon.entry_id]
    cb.hvac_mode = cs.hvac_mode = "heat"
    cb.hydro_enabled = cs.hydro_enabled = True
    await cb.async_refresh()
    await hass.async_block_till_done()
    assert cb.hydro_hold is True                       # 0.5 alone: blocked
    await cs.async_refresh()
    await hass.async_block_till_done()
    assert cs.hydro_hold is False                      # 4.0 already ≥ 2.0
    await cb.async_refresh()
    await hass.async_block_till_done()
    assert cb.hydro_hold is False                      # total 4.5: both open
    assert cb.hydro_total == 4.5
    # The living room satisfies -> deregisters -> the bathroom re-blocks.
    hass.states.async_set("sensor.b_temp", "25")
    await cs.async_refresh()
    await hass.async_block_till_done()
    await cb.async_refresh()
    await hass.async_block_till_done()
    assert cb.hydro_hold is True
    assert cb.hydro_total == 0.5


async def test_hydro_held_zone_keeps_demanding_despite_closed_valve(
        hass: HomeAssistant) -> None:
    """While held, the real valve source (F27) reads OUR hold, not the room:
    the demand falls back to t_int vs target so the zone stays registered."""
    _seed(hass)
    hass.states.async_set("sensor.salon_temp", "18")
    hass.states.async_set("switch.valve", "on")        # thermostat calling
    entry = await _add_opts(hass, {**CLIMATE, const.CONF_DC_VALVE: "switch.valve"},
                            "Bano", {"hydro_weight": 0.5, "hydro_min_weight": 2.0})
    co = hass.data[const.DOMAIN][entry.entry_id]
    co.hvac_mode = "heat"
    co.hydro_enabled = True
    await co.async_refresh()
    await hass.async_block_till_done()
    assert co.hydro_hold is True
    # The hold idled the thermostat -> the valve relay drops. Still registered.
    hass.states.async_set("switch.valve", "off")
    await co.async_refresh()
    await hass.async_block_till_done()
    assert co.hydro_hold is True
    assert co.hydro_total == 0.5


async def test_hydro_disabled_zone_never_participates(hass: HomeAssistant) -> None:
    _seed(hass)
    hass.states.async_set("sensor.salon_temp", "18")
    entry = await _add_opts(hass, CLIMATE, "Bano", {
        "hydro_weight": 0.5, "hydro_min_weight": 2.0})
    co = hass.data[const.DOMAIN][entry.entry_id]
    co.hvac_mode = "heat"                              # switch left off (default)
    await co.async_refresh()
    await hass.async_block_till_done()
    assert co.hydro_hold is False
    assert co.hydro_total == 0.0


# --- F25 Phase A: multiple emitters + primary/support staging ---
_EMITTERS = [
    {"name": "Radiant", "generator": "heatpump_air_water", "emission": "underfloor",
     "switch": "switch.radiant", "primary_heat": True},
    {"name": "AC", "generator": "heatpump_air_air", "emission": "split",
     "climate": "climate.ac", "primary_cool": True},
]
_EMIT_OPTS = {"emitters": _EMITTERS, "support_confirm_min": 0,
              "support_release_min": 0}


async def test_multi_emitter_primary_and_staged_support(
        hass: HomeAssistant) -> None:
    _seed(hass)
    hass.states.async_set("sensor.salon_temp", "17")     # big heating lag
    hass.states.async_set("switch.radiant", "off")
    hass.states.async_set("climate.ac", "off")
    entry = await _add_opts(hass, CLIMATE, "Salon", _EMIT_OPTS)
    hvac_calls = async_mock_service(hass, "climate", "set_hvac_mode")
    async_mock_service(hass, "climate", "set_temperature")
    on_calls = async_mock_service(hass, "homeassistant", "turn_on")
    async_mock_service(hass, "homeassistant", "turn_off")
    co = hass.data[const.DOMAIN][entry.entry_id]
    co.hvac_mode = "heat"
    await co.async_refresh()
    await hass.async_block_till_done()

    cmds = co.emitter_commands
    assert cmds["radiant"]["primary"] is True and cmds["radiant"]["on"] is True
    assert cmds["ac"]["on"] is True                       # support armed (lag, confirm 0)
    # Radiant relay was turned on; the AC support was driven to heat.
    assert any(c.data["entity_id"] == "switch.radiant" for c in on_calls)
    assert any(c.data["entity_id"] == "climate.ac" for c in hvac_calls)
    # The profile is derived from the heating primary (aerothermal heat pump).
    assert co.install_profile["compressor"] is True


async def test_multi_emitter_support_retires_on_recovery(
        hass: HomeAssistant) -> None:
    _seed(hass)
    hass.states.async_set("sensor.salon_temp", "17")
    hass.states.async_set("switch.radiant", "off")
    hass.states.async_set("climate.ac", "off")
    entry = await _add_opts(hass, CLIMATE, "Salon", _EMIT_OPTS)
    async_mock_service(hass, "climate", "set_hvac_mode")
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "homeassistant", "turn_on")
    async_mock_service(hass, "homeassistant", "turn_off")
    co = hass.data[const.DOMAIN][entry.entry_id]
    co.hvac_mode = "heat"
    await co.async_refresh()
    await hass.async_block_till_done()
    assert co.emitter_commands["ac"]["on"] is True        # support engaged

    # Room recovers above target -> support retires (release 0).
    hass.states.async_set("sensor.salon_temp", "24")
    await co.async_refresh()
    await hass.async_block_till_done()
    assert co.emitter_commands["ac"]["on"] is False
    assert co.emitter_commands["radiant"]["on"] is False  # relay follows demand


async def test_single_emitter_zone_keeps_legacy_path(hass: HomeAssistant) -> None:
    # No emitters list -> legacy single-device path, emitter_commands stays empty.
    _seed(hass)
    entry = await _add(hass, {**CLIMATE, const.CONF_DC_CLIMATE: "climate.real"},
                       "Salon")
    co = hass.data[const.DOMAIN][entry.entry_id]
    co.hvac_mode = "heat"
    await co.async_refresh()
    await hass.async_block_till_done()
    assert co.emitter_commands == {}


# --- F25 Phase B: shared un-zoned duct reconciliation ---
def _duct(owner: bool) -> list[dict]:
    return [{"name": "Duct", "emission": "ducts", "climate": "climate.duct",
             "scope": "group_unzoned", "shared_emitter_id": "duct",
             "owner": owner, "primary_heat": True}]


async def test_shared_duct_owner_reconciles_with_undershoot_guard(
        hass: HomeAssistant) -> None:
    _seed(hass)
    hass.states.async_set("sensor.salon_temp", "18")     # owner, still short
    hass.states.async_set("sensor.dorm_temp", "20.7")    # sibling, satisfied
    hass.states.async_set("climate.duct", "off")
    base = {"base_heat_day": 21.0}                        # pin the target at 21°C
    owner = await _add_opts(hass, CLIMATE, "Salon",
                            {"emitters": _duct(True), **base})
    sib = await _add_opts(hass, {**CLIMATE, const.CONF_NAME: "Dorm",
                                 const.CONF_DC_T_INT: "sensor.dorm_temp"}, "Dorm",
                          {"emitters": _duct(False), **base})
    async_mock_service(hass, "climate", "set_hvac_mode")
    async_mock_service(hass, "climate", "set_temperature")
    co_o = hass.data[const.DOMAIN][owner.entry_id]
    co_s = hass.data[const.DOMAIN][sib.entry_id]
    co_o.hvac_mode = co_s.hvac_mode = "heat"
    await co_s.async_refresh()                            # sibling reports demand
    await hass.async_block_till_done()
    await co_o.async_refresh()                            # owner reconciles both
    await hass.async_block_till_done()

    eid = co_o._emitters[0]["id"]
    cmd = co_o.emitter_commands[eid]
    assert cmd["shared"] is True
    # v0.96.0: Dormitorio merely NEAR its setpoint no longer cuts the unit while
    # Salón genuinely lags (the old guard cut below setpoint and starved Salón).
    assert cmd["reason"] == "reconciled" and cmd["on"] is True
    # Dormitorio over-conditioned (past setpoint + margin) with Salón no longer
    # lagging -> NOW the guard cuts the whole unit (REQ-EMI-8).
    hass.states.async_set("sensor.dorm_temp", "21.8")
    hass.states.async_set("sensor.salon_temp", "21.2")
    await co_s.async_refresh()
    await hass.async_block_till_done()
    await co_o.async_refresh()
    await hass.async_block_till_done()
    cmd = co_o.emitter_commands[eid]
    assert cmd["reason"] == "undershoot_cut" and cmd["on"] is False
    # The non-owner never drives the shared unit.
    await co_s.async_refresh()
    await hass.async_block_till_done()
    assert co_s._emitters[0]["id"] not in co_s.emitter_commands


async def test_shared_duct_reconciles_when_all_zones_short(
        hass: HomeAssistant) -> None:
    _seed(hass)
    hass.states.async_set("sensor.salon_temp", "18")
    hass.states.async_set("sensor.dorm_temp", "18.5")    # both clearly short
    hass.states.async_set("climate.duct", "off")
    base = {"base_heat_day": 21.0}
    owner = await _add_opts(hass, CLIMATE, "Salon",
                            {"emitters": _duct(True), **base})
    sib = await _add_opts(hass, {**CLIMATE, const.CONF_NAME: "Dorm",
                                 const.CONF_DC_T_INT: "sensor.dorm_temp"}, "Dorm",
                          {"emitters": _duct(False), **base})
    async_mock_service(hass, "climate", "set_hvac_mode")
    async_mock_service(hass, "climate", "set_temperature")
    co_o = hass.data[const.DOMAIN][owner.entry_id]
    co_s = hass.data[const.DOMAIN][sib.entry_id]
    co_o.hvac_mode = co_s.hvac_mode = "heat"
    await co_s.async_refresh()
    await hass.async_block_till_done()
    await co_o.async_refresh()
    await hass.async_block_till_done()
    cmd = co_o.emitter_commands[co_o._emitters[0]["id"]]
    assert cmd["on"] is True and cmd["reason"] == "reconciled"
    assert cmd["target"] is not None


# --- F37 community changeover (seasonal water direction) ---
_COMMUNITY = {const.CONF_GENERATOR: "heatpump_air_water",
              const.CONF_DISTRIBUTION: "central_shared",
              const.CONF_EMISSION: "underfloor"}


def _set_changeover(hass, state):
    hass.data[const.DOMAIN][const.DATA_CHANGEOVER] = {"state": state}


async def test_community_zone_follows_changeover(hass: HomeAssistant) -> None:
    _seed(hass)
    entry = await _add_opts(hass, CLIMATE, "Salon", _COMMUNITY)
    co = hass.data[const.DOMAIN][entry.entry_id]
    co.hvac_mode = "heat"                       # user left it on "heat"

    # v0.95.0: building supplies cold water while the user asks heat -> the zone
    # RESTS (never silently inverts the user's intent) and flags the conflict.
    _set_changeover(hass, "cool")
    await co.async_refresh()
    await hass.async_block_till_done()
    assert co.data.action == "off"
    assert co.changeover_conflict is True
    assert co.hvac_effective == "off"

    # Hot water -> the user's heat runs (no conflict).
    _set_changeover(hass, "heat")
    await co.async_refresh()
    await hass.async_block_till_done()
    assert co.data.action == "heat"
    assert co.changeover_conflict is False
    assert co.hvac_effective == "heat"

    # Shoulder season (off) -> idle even though the zone is "on".
    _set_changeover(hass, "off")
    await co.async_refresh()
    await hass.async_block_till_done()
    assert co.data.action == "off"
    assert co.changeover_conflict is False

    # "Follow the building" mode still tracks the water direction.
    co.follow_changeover = True
    _set_changeover(hass, "cool")
    await co.async_refresh()
    await hass.async_block_till_done()
    assert co.data.action == "cool"
    assert co.changeover_conflict is False


async def test_individual_zone_ignores_changeover(hass: HomeAssistant) -> None:
    _seed(hass)
    entry = await _add_opts(hass, CLIMATE, "Salon", {
        const.CONF_GENERATOR: "electric_direct",
        const.CONF_EMISSION: "convectors"})       # individual install
    co = hass.data[const.DOMAIN][entry.entry_id]
    co.hvac_mode = "heat"
    _set_changeover(hass, "cool")                 # building cooling
    await co.async_refresh()
    await hass.async_block_till_done()
    assert co.data.action == "heat"               # its own mode wins


async def test_zone_changeover_override_beats_house(hass: HomeAssistant) -> None:
    _seed(hass)
    entry = await _add_opts(hass, CLIMATE, "Salon", _COMMUNITY)
    co = hass.data[const.DOMAIN][entry.entry_id]
    co.hvac_mode = "heat"
    # Assign the zone in the tree so the coordinator can resolve its zid.
    tree = zones.assign_modules(zones.add_zone({}, "Salon"), "salon",
                                [entry.entry_id])
    hass.data[const.DOMAIN][const.DATA_ZONES] = tree
    # The house is cooling, but this zone is overridden to heat.
    hass.data[const.DOMAIN][const.DATA_CHANGEOVER] = {
        "state": "cool", "zones": {"salon": "heat"}}
    await co.async_refresh()
    await hass.async_block_till_done()
    assert co.data.action == "heat"                   # per-zone override wins

    # An off override idles the zone even though the house is cooling.
    hass.data[const.DOMAIN][const.DATA_CHANGEOVER] = {
        "state": "cool", "zones": {"salon": "off"}}
    await co.async_refresh()
    await hass.async_block_till_done()
    assert co.data.action == "off"


async def test_no_changeover_is_back_compat(hass: HomeAssistant) -> None:
    _seed(hass)
    entry = await _add_opts(hass, CLIMATE, "Salon", _COMMUNITY)
    co = hass.data[const.DOMAIN][entry.entry_id]
    co.hvac_mode = "cool"
    # No DATA_CHANGEOVER published -> unchanged behaviour.
    await co.async_refresh()
    await hass.async_block_till_done()
    assert co.data.action == "cool"


# --- F34: grid import headroom tightens the F03 peak budget ---
async def test_headroom_tightens_peak_budget(hass: HomeAssistant) -> None:
    _seed(hass)
    entry = await _add_opts(hass, CLIMATE, "Salon", {
        const.CONF_GENERATOR: "electric_direct",
        const.CONF_EMISSION: "convectors"})       # electrical -> profile.peak
    co = hass.data[const.DOMAIN][entry.entry_id]
    co.hvac_mode = "heat"
    co.peak_enabled = True

    # Plenty of grid headroom (4750 W) vs the zone's ~1000 W -> it runs.
    hass.data[const.DOMAIN][const.DATA_ENERGY] = {"import_headroom_w": 4750.0}
    await co.async_refresh()
    await hass.async_block_till_done()
    assert co.peak_hold is False

    # Near the ICP: only 200 W of headroom -> the zone can't start (held off).
    hass.data[const.DOMAIN][const.DATA_ENERGY] = {"import_headroom_w": 200.0}
    hass.data[const.DOMAIN]["_peak_dc"].clear(entry.entry_id)
    await co.async_refresh()
    await hass.async_block_till_done()
    assert co.peak_hold is True
    assert co.peak_reason == "peak_over_budget"


async def test_emitter_editor_adds_and_deletes(hass: HomeAssistant) -> None:
    _seed(hass)
    entry = await _add(hass, CLIMATE, "Salon")
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    flow = await hass.config_entries.options.async_configure(
        flow["flow_id"], {"next_step_id": "emitters"})
    flow = await hass.config_entries.options.async_configure(
        flow["flow_id"], {"next_step_id": "emitter_add"})
    assert flow["step_id"] == "emitter_add"
    flow = await hass.config_entries.options.async_configure(
        flow["flow_id"],
        {"name": "AC", "generator": "heatpump_air_air",
         "distribution": "individual", "emission": "split",
         "climate": "climate.ac", "primary_cool": True,
         "scope": "zone", "policy": "weighted"})
    await hass.async_block_till_done()
    ems = entry.options["emitters"]
    assert len(ems) == 1 and ems[0]["name"] == "AC"
    assert ems[0]["climate"] == "climate.ac" and ems[0]["primary_cool"] is True

    # Edit -> delete it.
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    flow = await hass.config_entries.options.async_configure(
        flow["flow_id"], {"next_step_id": "emitters"})
    flow = await hass.config_entries.options.async_configure(
        flow["flow_id"], {"next_step_id": "emitter_edit"})
    flow = await hass.config_entries.options.async_configure(
        flow["flow_id"], {"emitter": "ac"})
    assert flow["step_id"] == "emitter_detail"
    flow = await hass.config_entries.options.async_configure(
        flow["flow_id"],
        {"name": "AC", "generator": "heatpump_air_air",
         "distribution": "individual", "emission": "split",
         "scope": "zone", "policy": "weighted", "delete": True})
    await hass.async_block_till_done()
    assert entry.options["emitters"] == []


# --- F34/REQ-TAR-4: tariff bias feeds the Adaptive Lead ---
async def test_dc_follows_tariff_lead(hass: HomeAssistant) -> None:
    """Cheap tariff widens the anticipation lead, peak trims it; no Energy = neutral."""
    _seed(hass)
    entry = await _add(hass, CLIMATE, "Salon")
    co = hass.data[const.DOMAIN][entry.entry_id]
    co.hvac_mode = "heat"

    hass.data[const.DOMAIN][const.DATA_ENERGY] = {"tariff_state": "peak"}
    await co.async_refresh()
    await hass.async_block_till_done()
    peak_lead = co.data.details["lead_h"]

    hass.data[const.DOMAIN][const.DATA_ENERGY] = {"tariff_state": "cheap"}
    await co.async_refresh()
    await hass.async_block_till_done()
    cheap_lead = co.data.details["lead_h"]

    # No Energy module published -> neutral lead, between the two (back-compat).
    hass.data[const.DOMAIN].pop(const.DATA_ENERGY)
    await co.async_refresh()
    await hass.async_block_till_done()
    neutral_lead = co.data.details["lead_h"]

    assert peak_lead < neutral_lead < cheap_lead


# --- F06/REQ-ENE-5: instantaneous power per module ---
async def test_dc_power_sensor_reflects_estimate(hass: HomeAssistant) -> None:
    """A heating zone without a meter exposes its estimated instantaneous power."""
    from homeassistant.helpers import entity_registry as er
    _seed(hass)
    entry = await _add(hass, CLIMATE, "Salon")
    co = hass.data[const.DOMAIN][entry.entry_id]
    co.hvac_mode = "heat"
    # Two cycles so the energy integrator sees dt > 0 and latches power_w.
    await co.async_refresh()
    await co.async_refresh()
    await hass.async_block_till_done()

    assert co.power_w == 1000.0                            # est_w_on while ON
    eid = er.async_get(hass).async_get_entity_id(
        "sensor", const.DOMAIN, f"{entry.entry_id}_power")
    assert eid is not None
    assert float(hass.states.get(eid).state) == 1000.0


async def test_anticycle_per_emitter_compressor_channels(
        hass: HomeAssistant) -> None:
    """F09 full: two heat pumps on distinct compressor_ids are anti-cycled apart."""
    from homeassistant.util import dt as dt_util

    from custom_components.dynamic_home.anticycle import CompressorState
    _seed(hass)
    hass.states.async_set("sensor.salon_temp", "18")       # demand heat
    hass.states.async_set("switch.hp_a", "off")
    hass.states.async_set("switch.hp_b", "off")
    emitters = [
        {"id": "ea", "name": "Bomba A", "generator": "heatpump_air_water",
         "distribution": "individual", "emission": "underfloor",
         "switch": "switch.hp_a", "primary_heat": True, "compressor_id": "hp_a"},
        {"id": "eb", "name": "Bomba B", "generator": "heatpump_air_water",
         "distribution": "individual", "emission": "fancoil",
         "switch": "switch.hp_b", "compressor_id": "hp_b"},
    ]
    entry = await _add_opts(hass, CLIMATE, "Salon", {"emitters": emitters})
    async_mock_service(hass, "homeassistant", "turn_on")
    async_mock_service(hass, "homeassistant", "turn_off")
    co = hass.data[const.DOMAIN][entry.entry_id]
    co.hvac_mode = "heat"
    co.anticycle_enabled = True
    ac = hass.data[const.DOMAIN]["_anticycle"]
    # Channel hp_b just stopped (within min OFF); hp_a is free.
    ac.channels["hp_b"] = CompressorState(
        on=False, last_off_ts=dt_util.utcnow().timestamp())
    await co.async_refresh()
    await hass.async_block_till_done()

    # Each compressor is judged on its own channel.
    assert co._channel_holds["hp_a"] is False
    assert co._channel_holds["hp_b"] is True
    # The primary on the free channel runs; the one on the blocked channel is held.
    assert co.emitter_commands["ea"]["on"] is True
    assert co.emitter_commands["eb"]["on"] is False


# --- F37: HEAT_COOL = "follow the building" (community zones) ---
async def test_heat_cool_follows_changeover_on_community_zone(
        hass: HomeAssistant) -> None:
    _seed(hass)
    entry = await _add_opts(hass, CLIMATE, "Salon", {
        const.CONF_GENERATOR: "heatpump_air_water",
        const.CONF_DISTRIBUTION: "central_shared",
        const.CONF_EMISSION: "underfloor"})
    co = hass.data[const.DOMAIN][entry.entry_id]

    # Community zone offers HEAT_COOL in its mode list.
    assert HVACMode.HEAT_COOL in hass.states.get(
        "climate.salon").attributes["hvac_modes"]

    # Pick HEAT_COOL with the house in cooling season -> resolves to cool.
    hass.data[const.DOMAIN][const.DATA_CHANGEOVER] = {"state": "cool"}
    await hass.services.async_call(
        "climate", "set_hvac_mode",
        {"entity_id": "climate.salon", "hvac_mode": HVACMode.HEAT_COOL},
        blocking=True)
    await hass.async_block_till_done()
    assert co.follow_changeover is True
    assert co.hvac_mode == "cool"                       # engine sees a concrete dir
    assert hass.states.get("climate.salon").state == HVACMode.HEAT_COOL  # honest UI

    # The building flips to heating -> the zone follows, no user action.
    hass.data[const.DOMAIN][const.DATA_CHANGEOVER] = {"state": "heat"}
    await co.async_refresh()
    await hass.async_block_till_done()
    assert co.hvac_mode == "heat"

    # Back to a concrete mode clears follow-the-building.
    await hass.services.async_call(
        "climate", "set_hvac_mode",
        {"entity_id": "climate.salon", "hvac_mode": HVACMode.HEAT}, blocking=True)
    await hass.async_block_till_done()
    assert co.follow_changeover is False


async def test_heat_cool_absent_on_individual_zone(hass: HomeAssistant) -> None:
    _seed(hass)
    await _add_opts(hass, CLIMATE, "Salon", {
        const.CONF_GENERATOR: "heatpump_air_water",
        const.CONF_DISTRIBUTION: "individual",
        const.CONF_EMISSION: "underfloor"})
    # An individual (non-community) zone does not offer the follow-the-building mode.
    assert HVACMode.HEAT_COOL not in hass.states.get(
        "climate.salon").attributes["hvac_modes"]


# --- F09: adaptive anti-cycle (autosize min ON/OFF from learned lag) ---
async def test_anticycle_autosize_overrides_min_on_off_when_mature(
        hass: HomeAssistant) -> None:
    from types import SimpleNamespace
    _seed(hass)
    entry = await _add_opts(hass, CLIMATE, "Salon", {
        const.CONF_GENERATOR: "heatpump_air_water",
        const.CONF_DISTRIBUTION: "individual",
        const.CONF_EMISSION: "underfloor"})
    co = hass.data[const.DOMAIN][entry.entry_id]
    co.anticycle_enabled = True
    co.anticycle_autosize_enabled = True
    co.learned_lag_h = 1.0                       # -> 1800 s bound
    co.adapt_ok_count = 10                        # mature

    cfg = co._cfg()
    assert cfg.anticycle_min_on_s == 600.0        # static default before
    co._anticycle_step(cfg, SimpleNamespace(action="heat"), 1000.0)
    assert cfg.anticycle_min_on_s == 1800.0       # autosized from the learned lag
    assert cfg.anticycle_min_off_s == 1800.0

    # Not yet mature -> the static configured value is kept.
    co.adapt_ok_count = 1
    cfg2 = co._cfg()
    co._anticycle_step(cfg2, SimpleNamespace(action="heat"), 1000.0)
    assert cfg2.anticycle_min_on_s == 600.0
