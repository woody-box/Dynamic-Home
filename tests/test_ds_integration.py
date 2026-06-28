"""Home Assistant integration tests for the DS (shutter) module.

Covers the config flow (menu -> shutter), entity creation, and — crucially —
the cross-module coordination: another module publishing ``request_solar_shield``
to the shared SDHB hub makes the cover clamp.
"""

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from custom_components.dynamic_home import const

SHUTTER = {
    const.CONF_NAME: "Salon",
    const.CONF_MODULE: const.MODULE_SHUTTER,
    const.CONF_COVER: "cover.salon_real",
    const.CONF_FACADE_AZIMUTH: 180.0,
}


def _seed(hass: HomeAssistant, position=None) -> None:
    attrs = {"supported_features": 15}
    if position is not None:
        attrs["current_position"] = position
    hass.states.async_set("cover.salon_real", "open", attrs)
    # Night / sun below horizon so the geometric impact is 0 by default.
    hass.states.async_set("sun.sun", "below_horizon",
                          {"azimuth": 180, "elevation": -10})


async def _setup(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(domain=const.DOMAIN, data=SHUTTER, title="Salon")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


# --- F17: anticipatory weather-alert protection ---
ALERTS = {
    **SHUTTER,
    const.CONF_DS_ALERT: "binary_sensor.meteo_alert",
    const.CONF_DS_ALERT_HAIL: "binary_sensor.meteo_hail",
    const.CONF_DS_ALERT_WIND: "binary_sensor.meteo_wind",
}


async def test_weather_alert_protects_min_and_holds(hass: HomeAssistant) -> None:
    _seed(hass)
    for e in ("binary_sensor.meteo_alert", "binary_sensor.meteo_hail",
              "binary_sensor.meteo_wind"):
        hass.states.async_set(e, "off")
    entry = MockConfigEntry(domain=const.DOMAIN, data=ALERTS, title="Salon")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    co = hass.data[const.DOMAIN][entry.entry_id]
    cfg = co._cfg()  # alert 0, hail 0, wind 50, hold 30 min

    # No alert -> None.
    assert co._weather_alert(cfg, 1000.0) is None
    # Wind alert -> its protection position (50).
    hass.states.async_set("binary_sensor.meteo_wind", "on")
    assert co._weather_alert(cfg, 1000.0) == 50
    # Hail also on -> most protective (min) wins (0).
    hass.states.async_set("binary_sensor.meteo_hail", "on")
    assert co._weather_alert(cfg, 1000.0) == 0
    # All clear -> held at the last position during the hold window...
    for e in ("binary_sensor.meteo_hail", "binary_sensor.meteo_wind"):
        hass.states.async_set(e, "off")
    assert co._weather_alert(cfg, 1000.0 + 60) == 0
    # ...then released after the hold elapses.
    assert co._weather_alert(cfg, 1000.0 + cfg.alert_hold_min * 60 + 2) is None


async def test_weather_alert_absent_without_sensors(hass: HomeAssistant) -> None:
    _seed(hass)
    entry = await _setup(hass)            # plain SHUTTER, no alert sensors
    co = hass.data[const.DOMAIN][entry.entry_id]
    assert co._weather_alert(co._cfg(), 1000.0) is None


# --- F16: seasonal night insulation ---
async def test_night_insulation_heat_and_cool(hass: HomeAssistant) -> None:
    _seed(hass)
    entry = await _setup(hass)
    co = hass.data[const.DOMAIN][entry.entry_id]
    cfg = co._cfg()  # close 0, open 100

    # Disabled by default (opt-in).
    assert co._night_iso(cfg, "heat", -5.0, 18.0, 2.0) is None
    co.night_iso_enabled = True

    # Daytime (sun up) -> no night strategy.
    assert co._night_iso(cfg, "heat", 10.0, 18.0, 2.0) is None
    # Heat at night -> close to insulate.
    assert co._night_iso(cfg, "heat", -5.0, 18.0, 2.0) == 0
    # Cool, cooler outside -> open to purge the mass.
    assert co._night_iso(cfg, "cool", -5.0, 26.0, 20.0) == 100
    # Cool, warmer outside -> close to protect the mass.
    assert co._night_iso(cfg, "cool", -5.0, 26.0, 30.0) == 0
    # Cool, temps unknown -> defer to the cascade.
    assert co._night_iso(cfg, "cool", -5.0, None, 20.0) is None


# --- F19: gradual sunrise ramp (driven with injected sun/time) ---
async def test_dawn_ramp_triggers_and_climbs(hass: HomeAssistant) -> None:
    _seed(hass, position=0)
    entry = await _setup(hass)
    co = hass.data[const.DOMAIN][entry.entry_id]
    co.dawn_enabled = True
    cfg = co._cfg()  # defaults: step 10% every 5 min, target 100, trigger 0°

    t = 1000.0
    # Sun still below horizon -> no ramp, just primes prev elevation.
    assert co._dawn_step(cfg, -1.0, 0, t) is None
    # Sun crosses the trigger upward -> ramp starts, first step immediately.
    assert co._dawn_step(cfg, 1.0, 0, t + 60) == 10
    # Climbs by a step every dawn_step_min.
    assert co._dawn_step(cfg, 2.0, 10, t + 60 + cfg.dawn_step_min * 60) == 20
    # Near the top it completes and hands back to the cascade (None).
    assert co._dawn_step(cfg, 5.0, 90, t + 60 + 60 * cfg.dawn_step_min * 60) is None


async def test_dawn_ramp_skips_when_already_open(hass: HomeAssistant) -> None:
    _seed(hass)
    entry = await _setup(hass)
    co = hass.data[const.DOMAIN][entry.entry_id]
    co.dawn_enabled = True
    cfg = co._cfg()
    co._dawn_step(cfg, -1.0, 100, 1000.0)                  # prime prev elevation
    # Crosses sunrise but the shutter is already fully open -> no ramp.
    assert co._dawn_step(cfg, 1.0, 100, 1060.0) is None
    assert co._dawn_active is False


async def test_dawn_ramp_disabled_by_default(hass: HomeAssistant) -> None:
    _seed(hass)
    entry = await _setup(hass)
    co = hass.data[const.DOMAIN][entry.entry_id]
    cfg = co._cfg()
    co._dawn_step(cfg, -1.0, 0, 1000.0)
    assert co._dawn_step(cfg, 1.0, 0, 1060.0) is None      # opt-in, off by default


async def test_shutter_config_flow(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        const.DOMAIN, context={"source": "user"})
    assert result["type"] == FlowResultType.MENU

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "shutter"})
    # No shutter exists yet -> skip the copy picker, straight to the entity form.
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "shutter_form"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={const.CONF_NAME: "Salon", const.CONF_COVER: "cover.salon",
                    const.CONF_FACADE_AZIMUTH: 180})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][const.CONF_MODULE] == const.MODULE_SHUTTER


async def test_shutter_create_copies_from_template(hass: HomeAssistant) -> None:
    """Adding a 2nd shutter can copy a sibling: form pre-filled + options cloned."""
    src = MockConfigEntry(
        domain=const.DOMAIN, title="Salón Izquierda",
        data={**SHUTTER, const.CONF_COVER: "cover.salon_izq",
              const.CONF_FACADE_AZIMUTH: 0.0, const.CONF_CLIMATE: "climate.salon"},
        options={"summer_min_open_pct": 35})
    src.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        const.DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "shutter"})
    # A sibling exists -> the copy picker shows first.
    assert result["step_id"] == "shutter"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"copy_from": src.entry_id})
    assert result["step_id"] == "shutter_form"

    # Only the cover (and name) differ; the rest is taken from the template.
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={const.CONF_NAME: "Salón Derecha",
                    const.CONF_COVER: "cover.salon_der",
                    const.CONF_FACADE_AZIMUTH: 0.0, const.CONF_FACADE_SPAN: 180})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][const.CONF_COVER] == "cover.salon_der"
    assert result["options"] == {"summer_min_open_pct": 35}   # tunables cloned


async def test_shutter_clone_into_existing(hass: HomeAssistant) -> None:
    """Options 'clone' copies a sibling's data (except cover) + options onto this one."""
    hass.states.async_set("cover.salon_izq", "open", {"supported_features": 15})
    hass.states.async_set("cover.salon_der", "open", {"supported_features": 15})
    src = MockConfigEntry(
        domain=const.DOMAIN, title="Salón Izquierda",
        data={**SHUTTER, const.CONF_COVER: "cover.salon_izq",
              const.CONF_FACADE_AZIMUTH: 0.0, const.CONF_CLIMATE: "climate.salon"},
        options={"summer_min_open_pct": 35})
    dst = MockConfigEntry(
        domain=const.DOMAIN, title="Salón Derecha",
        data={**SHUTTER, const.CONF_COVER: "cover.salon_der"}, options={})
    src.add_to_hass(hass)
    dst.add_to_hass(hass)
    assert await hass.config_entries.async_setup(dst.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(dst.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "clone"})
    assert result["step_id"] == "clone"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"source": src.entry_id})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()

    # Cover kept; orientation/climate + options taken from the source.
    assert dst.data[const.CONF_COVER] == "cover.salon_der"
    assert dst.data[const.CONF_FACADE_AZIMUTH] == 0.0
    assert dst.data[const.CONF_CLIMATE] == "climate.salon"
    assert dst.options == {"summer_min_open_pct": 35}


async def test_setup_creates_cover(hass: HomeAssistant) -> None:
    async_mock_service(hass, "cover", "set_cover_position")
    _seed(hass)
    entry = await _setup(hass)
    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get("cover.salon") is not None


async def test_bus_solar_shield_clamps_cover(hass: HomeAssistant) -> None:
    """Cross-module demo: a bus solar-shield intent clamps the shutter.

    Asserts on the managed cover's state (current_position), which is the
    end-to-end observable result of the shared SDHB hub driving DS.
    """
    _seed(hass)  # position unknown -> slew inactive, clamp is direct
    entry = await _setup(hass)

    coordinator = hass.data[const.DOMAIN][entry.entry_id]
    hub = hass.data[const.DOMAIN]["_hub"]

    # No intent yet -> cover wants to be fully open (default branch).
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get("cover.salon").attributes["current_position"] == 100

    # Another module (e.g. DC) publishes a solar-shield request to the bus.
    hub.publish(source="dc_zone01", intent="request_solar_shield",
                target="ds", priority=80)
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    # DS consumes it and clamps to the shield max (default 30%).
    assert coordinator.data.pos == 30
    assert coordinator.data.reason == "sdhb_solar_shield"
    managed = hass.states.get("cover.salon")
    assert managed.attributes["current_position"] == 30
    assert managed.attributes["reason"] == "sdhb_solar_shield"


async def test_cover_reports_real_position_not_target(hass: HomeAssistant) -> None:
    """The managed cover must report the REAL physical position, not the target."""
    async_mock_service(hass, "cover", "set_cover_position")  # real cover won't move
    _seed(hass, position=70)   # physical cover sits at 70%
    entry = await _setup(hass)
    co = hass.data[const.DOMAIN][entry.entry_id]

    await co.async_refresh()
    await hass.async_block_till_done()

    # Engine target (slewed from the real 70 toward open) differs from the
    # physical position; the entity must report the hardware, not the target.
    target = co.data.pos
    assert target > 70
    managed = hass.states.get("cover.salon")
    assert managed.attributes["current_position"] == 70        # REAL, not target
    assert managed.attributes["target_position"] == target     # target exposed


async def test_position_sensor_reports_real_with_target_attr(
        hass: HomeAssistant) -> None:
    """A diagnostic sensor re-publishes the cover's real % + target/reason."""
    from homeassistant.helpers import entity_registry as er
    async_mock_service(hass, "cover", "set_cover_position")  # real cover won't move
    _seed(hass, position=25)                                 # physical cover at 25%
    entry = await _setup(hass)
    co = hass.data[const.DOMAIN][entry.entry_id]

    await co.async_refresh()
    await hass.async_block_till_done()

    eid = er.async_get(hass).async_get_entity_id(
        "sensor", const.DOMAIN, f"{entry.entry_id}_position")
    assert eid is not None
    st = hass.states.get(eid)
    assert int(float(st.state)) == 25                        # REAL, not the target
    assert st.attributes["unit_of_measurement"] == "%"
    assert st.attributes["target"] == co.data.pos            # commanded target
    assert st.attributes["reason"] == co.data.reason
    assert st.attributes["target"] != 25                     # target differs (slew)


async def test_position_sensor_unknown_without_feedback(
        hass: HomeAssistant) -> None:
    """No position feedback from the cover -> the sensor reports unknown."""
    from homeassistant.helpers import entity_registry as er
    async_mock_service(hass, "cover", "set_cover_position")
    _seed(hass)                                              # no current_position
    entry = await _setup(hass)
    eid = er.async_get(hass).async_get_entity_id(
        "sensor", const.DOMAIN, f"{entry.entry_id}_position")
    assert hass.states.get(eid).state == "unknown"


async def test_target_and_reason_sensors(hass: HomeAssistant) -> None:
    """Observe-only signals: target position (%) and reason as graphable states."""
    from homeassistant.helpers import entity_registry as er
    async_mock_service(hass, "cover", "set_cover_position")
    _seed(hass, position=25)
    entry = await _setup(hass)
    co = hass.data[const.DOMAIN][entry.entry_id]
    await co.async_refresh()
    await hass.async_block_till_done()

    reg = er.async_get(hass)
    tid = reg.async_get_entity_id("sensor", const.DOMAIN, f"{entry.entry_id}_target")
    rid = reg.async_get_entity_id("sensor", const.DOMAIN, f"{entry.entry_id}_reason")
    assert tid is not None and rid is not None
    # Target = what the cascade wants (even though the real cover sits at 25%).
    assert int(float(hass.states.get(tid).state)) == co.data.pos
    assert hass.states.get(tid).attributes["unit_of_measurement"] == "%"
    # Reason = the winning branch, as a graphable state.
    assert hass.states.get(rid).state == co.data.reason


async def test_in_sun_binary_sensor(hass: HomeAssistant) -> None:
    """'In sun' is on only when direct sun reaches this facade."""
    from homeassistant.helpers import entity_registry as er
    async_mock_service(hass, "cover", "set_cover_position")
    _seed(hass)                                   # sun below horizon
    entry = await _setup(hass)
    co = hass.data[const.DOMAIN][entry.entry_id]
    await co.async_refresh()
    await hass.async_block_till_done()

    eid = er.async_get(hass).async_get_entity_id(
        "binary_sensor", const.DOMAIN, f"{entry.entry_id}_in_sun")
    assert eid is not None
    assert hass.states.get(eid).state == "off"    # night -> not in sun

    # Sun on the south facade (SHUTTER facade_azimuth = 180).
    hass.states.async_set("sun.sun", "above_horizon",
                          {"azimuth": 180, "elevation": 50})
    await co.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(eid).state == "on"
    assert hass.states.get(eid).attributes["impact"] > 0


async def test_privacy_and_lock_switches(hass: HomeAssistant) -> None:
    """Privacy clamps the cover; lock pins it (override) and wins over privacy."""
    _seed(hass)  # sun below horizon, cover.salon_real without position
    entry = await _setup(hass)
    co = hass.data[const.DOMAIN][entry.entry_id]

    # The switch entities wire to the coordinator state.
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": "switch.salon_privacy"}, blocking=True)
    await hass.async_block_till_done()
    assert co.privacy_enabled is True

    # Privacy ON -> cover goes to the privacy position (default 40).
    await co.async_refresh()
    assert co.data.reason == "privacy_time"
    assert co.data.pos == 40

    # Lock wins over privacy -> override pins to the lock position (default 50).
    co.lock_enabled = True
    await co.async_refresh()
    assert co.data.reason == "ov_lock"
    assert co.data.pos == 50


# --- F06: shutter energy (per-move estimate) + sensor wiring ---
async def test_ds_energy_accumulates_on_move(hass: HomeAssistant) -> None:
    from homeassistant.helpers import entity_registry as er
    async_mock_service(hass, "cover", "set_cover_position")
    _seed(hass)                       # sun below horizon, cover open (no position)
    entry = await _setup(hass)
    co = hass.data[const.DOMAIN][entry.entry_id]

    # Baseline established on the first cycle (default night -> fully open).
    assert co.energy_kwh == 0.0

    # Pin the shutter shut: a commanded position change accrues motor energy.
    co.lock_enabled = True
    co.lock_pct = 0
    await co.async_refresh()
    await hass.async_block_till_done()
    assert co.data.pos == 0
    assert co.energy_kwh > 0.0

    eid = er.async_get(hass).async_get_entity_id(
        "sensor", const.DOMAIN, f"{entry.entry_id}_energy")
    assert eid is not None
    assert hass.states.get(eid).attributes["device_class"] == "energy"


# --- F15: geometric shading (opt-in) refines the summer solar branch ---
GEO = {
    **SHUTTER,
    const.CONF_CLIMATE: "climate.salon",
    const.CONF_DS_T_IN: "sensor.salon_in",
    const.CONF_DS_T_OUT: "sensor.salon_out",
}


def _seed_geo(hass: HomeAssistant) -> None:
    hass.states.async_set("cover.salon_real", "open", {"supported_features": 15})
    hass.states.async_set("sun.sun", "above_horizon",
                          {"azimuth": 180, "elevation": 70})   # high south sun
    hass.states.async_set("climate.salon", "cool")
    hass.states.async_set("sensor.salon_in", "24")
    hass.states.async_set("sensor.salon_out", "30")            # hot outside


async def test_geo_shade_switch_refines_solar_branch(hass: HomeAssistant) -> None:
    from homeassistant.helpers import entity_registry as er
    async_mock_service(hass, "cover", "set_cover_position")
    _seed_geo(hass)
    entry = MockConfigEntry(domain=const.DOMAIN, data=GEO, title="Salon")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    co = hass.data[const.DOMAIN][entry.entry_id]

    # Opt-in switch exists and is off by default -> the fixed impact shield runs.
    eid = er.async_get(hass).async_get_entity_id(
        "switch", const.DOMAIN, f"{entry.entry_id}_geo_shade")
    assert eid is not None
    await co.async_refresh()
    await hass.async_block_till_done()
    assert co.data.reason == "summer_solar_shield"

    # Enabling it switches to the geometric solar-penetration model.
    co.geo_shade_enabled = True
    await co.async_refresh()
    await hass.async_block_till_done()
    assert co.data.reason == "summer_solar_geo"
    assert "penetration_m" in co.data.details


async def test_ds_context_sensors_expose_temps_and_climate(
        hass: HomeAssistant) -> None:
    """First-class sensors surface the shutter's indoor/outdoor temps and the
    linked climate's mode/setpoint/current temp, so the 'why' reads at a glance."""
    from homeassistant.helpers import entity_registry as er
    async_mock_service(hass, "cover", "set_cover_position")
    hass.states.async_set("cover.salon_real", "open", {"supported_features": 15})
    hass.states.async_set("sun.sun", "above_horizon",
                          {"azimuth": 180, "elevation": 70})
    hass.states.async_set("climate.salon", "cool",
                          {"temperature": 23.5, "current_temperature": 25.0})
    hass.states.async_set("sensor.salon_in", "24")
    hass.states.async_set("sensor.salon_out", "30")
    entry = MockConfigEntry(domain=const.DOMAIN, data=GEO, title="Salon")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    reg = er.async_get(hass)

    def _state(key: str):
        eid = reg.async_get_entity_id("sensor", const.DOMAIN,
                                      f"{entry.entry_id}_{key}")
        assert eid is not None, key
        return hass.states.get(eid).state

    assert float(_state("ds_indoor_temp")) == 24.0
    assert float(_state("ds_outdoor_temp")) == 30.0
    assert _state("ds_climate_mode") == "cool"
    assert float(_state("ds_climate_setpoint")) == 23.5
    assert float(_state("ds_climate_temp")) == 25.0


async def test_direct_sun_shield_switch(hass: HomeAssistant) -> None:
    """Opt-in: in cooling, close on direct sun even when the outdoor air is cooler."""
    from homeassistant.helpers import entity_registry as er
    async_mock_service(hass, "cover", "set_cover_position")
    hass.states.async_set("cover.salon_real", "open", {"supported_features": 15})
    hass.states.async_set("sun.sun", "above_horizon",
                          {"azimuth": 180, "elevation": 45})   # sun on the facade
    hass.states.async_set("climate.salon", "cool")
    hass.states.async_set("sensor.salon_in", "26")
    hass.states.async_set("sensor.salon_out", "22")            # cooler outside
    entry = MockConfigEntry(domain=const.DOMAIN, data=GEO, title="Salon")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    co = hass.data[const.DOMAIN][entry.entry_id]

    # Switch exists and is off by default -> cooler outside means no shield.
    eid = er.async_get(hass).async_get_entity_id(
        "switch", const.DOMAIN, f"{entry.entry_id}_sun_shield")
    assert eid is not None
    await co.async_refresh()
    await hass.async_block_till_done()
    assert co.data.reason == "default"

    # Enabling it shades on the direct sun alone (solar gain through the glass).
    co.sun_shield_enabled = True
    await co.async_refresh()
    await hass.async_block_till_done()
    assert co.data.reason == "summer_solar_shield"


async def test_ds_auto_alert_from_dynamic_weather(hass: HomeAssistant) -> None:
    """With no per-shutter alert sensor, DS follows the Dynamic Weather alert."""
    async_mock_service(hass, "cover", "set_cover_position")
    _seed(hass)
    entry = await _setup(hass)                  # SHUTTER fixture: no alert sensors
    co = hass.data[const.DOMAIN][entry.entry_id]
    cfg = co._cfg()

    # Nothing published -> no alert.
    assert co._weather_alert(cfg, 1000.0) is None
    # Module alert on -> protect at the generic alert position.
    hass.data[const.DOMAIN][const.DATA_WEATHER] = {"source": "weather.x", "alert": True}
    assert co._weather_alert(cfg, 1000.0) == cfg.alert_pct


async def test_ds_local_alert_overrides_dynamic_weather(hass: HomeAssistant) -> None:
    """A per-shutter alert sensor takes precedence over the module alert."""
    async_mock_service(hass, "cover", "set_cover_position")
    _seed(hass)
    for e in ("binary_sensor.meteo_alert", "binary_sensor.meteo_hail",
              "binary_sensor.meteo_wind"):
        hass.states.async_set(e, "off")
    entry = MockConfigEntry(domain=const.DOMAIN, data=ALERTS, title="Salon")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    co = hass.data[const.DOMAIN][entry.entry_id]
    cfg = co._cfg()

    # Module alert is on, but this shutter has its own (off) sensors -> ignores it.
    hass.data[const.DOMAIN][const.DATA_WEATHER] = {"source": "weather.x", "alert": True}
    assert co._weather_alert(cfg, 1000.0) is None


async def test_manual_override_hold_resume_and_expiry(hass: HomeAssistant) -> None:
    """A hand command pins the position; the resume button and the timeout clear it."""
    from homeassistant.helpers import entity_registry as er
    async_mock_service(hass, "cover", "set_cover_position")
    _seed(hass, position=100)
    entry = await _setup(hass)
    co = hass.data[const.DOMAIN][entry.entry_id]
    reg = er.async_get(hass)

    # Hand command (what the managed cover does on a user move) arms the hold.
    co.arm_manual_override(80)
    await hass.async_block_till_done()
    assert co.manual_pos == 80
    assert co.data.reason == "manual_hold" and co.data.pos == 80

    # "Override restante" sensor shows time left.
    sid = reg.async_get_entity_id(
        "sensor", const.DOMAIN, f"{entry.entry_id}_override_remaining")
    assert sid is not None and float(hass.states.get(sid).state) > 0

    # Resume button -> back to automatic.
    bid = reg.async_get_entity_id(
        "button", const.DOMAIN, f"{entry.entry_id}_resume_auto")
    assert bid is not None
    await hass.services.async_call(
        "button", "press", {"entity_id": bid}, blocking=True)
    await hass.async_block_till_done()
    assert co.manual_pos is None
    await co.async_refresh()
    await hass.async_block_till_done()
    assert co.data.reason != "manual_hold"

    # Timeout: re-arm, backdate the deadline -> next cycle drops the hold.
    co.arm_manual_override(50)
    await hass.async_block_till_done()
    assert co.manual_pos == 50
    co.manual_until = 1.0                       # in the past
    await co.async_refresh()
    await hass.async_block_till_done()
    assert co.manual_pos is None and co.data.reason != "manual_hold"


async def test_ds_context_sensors_absent_without_sources(
        hass: HomeAssistant) -> None:
    """No temp/climate configured -> the context sensors are not created."""
    from homeassistant.helpers import entity_registry as er
    async_mock_service(hass, "cover", "set_cover_position")
    hass.states.async_set("cover.salon_real", "open", {"supported_features": 15})
    entry = await _setup(hass)            # plain SHUTTER (no temps, no climate)

    reg = er.async_get(hass)
    for key in ("ds_indoor_temp", "ds_outdoor_temp", "ds_climate_mode",
                "ds_climate_setpoint", "ds_climate_temp"):
        assert reg.async_get_entity_id(
            "sensor", const.DOMAIN, f"{entry.entry_id}_{key}") is None, key


async def test_heat_shield_holds_closed_when_hot_no_direct_sun(
        hass: HomeAssistant) -> None:
    """Cooling + hotter outside + sun off this facade -> stay shut (opt-in)."""
    from homeassistant.helpers import entity_registry as er
    async_mock_service(hass, "cover", "set_cover_position")
    hass.states.async_set("cover.salon_real", "open", {"supported_features": 15})
    # Low west sun: off the (south) facade -> no direct impact, but it's hot out.
    hass.states.async_set("sun.sun", "above_horizon",
                          {"azimuth": 290, "elevation": 20})
    hass.states.async_set("climate.salon", "cool")
    hass.states.async_set("sensor.salon_in", "24")
    hass.states.async_set("sensor.salon_out", "31")          # hotter outside
    entry = MockConfigEntry(domain=const.DOMAIN, data=GEO, title="Salon")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    co = hass.data[const.DOMAIN][entry.entry_id]

    # Off by default -> opt-in switch exists; the shutter opens until it's on.
    eid = er.async_get(hass).async_get_entity_id(
        "switch", const.DOMAIN, f"{entry.entry_id}_heat_shield")
    assert eid is not None
    await co.async_refresh()
    assert co.data.reason != "summer_heat_shield"

    co.heat_shield_enabled = True
    await co.async_refresh()
    await hass.async_block_till_done()
    assert co.data.reason == "summer_heat_shield"
    assert co.data.pos == 0                                   # default heat shield


async def test_winter_cold_shield_day_no_sun(hass: HomeAssistant) -> None:
    """Heating + daytime + no direct sun + colder outside -> insulate (shut)."""
    async_mock_service(hass, "cover", "set_cover_position")
    hass.states.async_set("cover.salon_real", "open", {"supported_features": 15})
    hass.states.async_set("sun.sun", "above_horizon",
                          {"azimuth": 290, "elevation": 20})   # day, off the facade
    hass.states.async_set("climate.salon", "heat")
    hass.states.async_set("sensor.salon_in", "21")
    hass.states.async_set("sensor.salon_out", "7")             # colder outside
    entry = MockConfigEntry(domain=const.DOMAIN, data=GEO, title="Salon")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    co = hass.data[const.DOMAIN][entry.entry_id]
    co.heat_shield_enabled = True                            # opt-in

    await co.async_refresh()
    await hass.async_block_till_done()
    assert co.data.reason == "winter_cold_shield"
    assert co.data.pos == 0


# --- F03: electrical-peak staging of mass shutter starts ---
async def _two_shutters(hass: HomeAssistant):
    _seed(hass)
    hass.states.async_set("cover.b_real", "open",
                          {"supported_features": 15, "current_position": 100})
    ea = MockConfigEntry(domain=const.DOMAIN, data={**SHUTTER}, title="A")
    eb = MockConfigEntry(domain=const.DOMAIN,
                         data={**SHUTTER, const.CONF_NAME: "B",
                               const.CONF_COVER: "cover.b_real"}, title="B")
    for e in (ea, eb):
        e.add_to_hass(hass)
        assert await hass.config_entries.async_setup(e.entry_id)
    await hass.async_block_till_done()
    return (hass.data[const.DOMAIN][ea.entry_id],
            hass.data[const.DOMAIN][eb.entry_id])


async def test_peak_staggers_shutter_starts(hass: HomeAssistant) -> None:
    from custom_components.dynamic_home.ds_engine import DsConfig, DsDecision
    ca, cb = await _two_shutters(hass)
    ca.peak_enabled = cb.peak_enabled = True
    cfg = DsConfig(peak_max_zones=1, peak_stagger_s=0)
    move = DsDecision(pos=0, reason="x")        # both at 100, both want to close
    da = ca._peak_gate(cfg, move, 100, 1000.0)
    db = cb._peak_gate(cfg, move, 100, 1000.0)
    assert da.pos == 0                          # first start granted
    assert db.pos == 100                        # second deferred (held in place)
    assert db.reason == "peak_stagger"
    assert db.details["peak_deferred_pos"] == 0


async def test_peak_disabled_does_not_defer_shutters(hass: HomeAssistant) -> None:
    from custom_components.dynamic_home.ds_engine import DsConfig, DsDecision
    ca, cb = await _two_shutters(hass)        # peak_enabled stays False
    cfg = DsConfig(peak_max_zones=1, peak_stagger_s=0)
    move = DsDecision(pos=0, reason="x")
    assert ca._peak_gate(cfg, move, 100, 1000.0).pos == 0
    assert cb._peak_gate(cfg, move, 100, 1000.0).pos == 0   # no budget gating
    assert cb.peak_reason == "off"


# --- F37: shutters follow the house changeover (season) for solar strategy ---
async def test_hvac_mode_follows_house_changeover(hass: HomeAssistant) -> None:
    _seed(hass)
    entry = await _setup(hass)            # plain SHUTTER, no per-shutter climate
    co = hass.data[const.DOMAIN][entry.entry_id]

    # No changeover configured -> off (back-compat: engine idles to default).
    assert co._hvac_mode() == "off"
    # House cooling season -> the shutter adopts "cool" (summer shield / free-cool).
    hass.data[const.DOMAIN][const.DATA_CHANGEOVER] = {"state": "cool"}
    assert co._hvac_mode() == "cool"
    # Heating season -> "heat" (winter solar gain / night insulate).
    hass.data[const.DOMAIN][const.DATA_CHANGEOVER] = {"state": "heat"}
    assert co._hvac_mode() == "heat"
    # Off season -> off.
    hass.data[const.DOMAIN][const.DATA_CHANGEOVER] = {"state": "off"}
    assert co._hvac_mode() == "off"


async def test_hvac_mode_climate_entity_wins_then_falls_back(
        hass: HomeAssistant) -> None:
    _seed(hass)
    hass.states.async_set("climate.salon", "heat")
    data = {**SHUTTER, const.CONF_CLIMATE: "climate.salon"}
    entry = MockConfigEntry(domain=const.DOMAIN, data=data, title="Salon")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    co = hass.data[const.DOMAIN][entry.entry_id]
    hass.data[const.DOMAIN][const.DATA_CHANGEOVER] = {"state": "cool"}

    # An actively calling thermostat (heat) wins over the house changeover (cool).
    assert co._hvac_mode() == "heat"
    # Idle/off thermostat -> fall back to the house season.
    hass.states.async_set("climate.salon", "off")
    assert co._hvac_mode() == "cool"
