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
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "shutter"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={const.CONF_NAME: "Salon", const.CONF_COVER: "cover.salon",
                    const.CONF_FACADE_AZIMUTH: 180})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][const.CONF_MODULE] == const.MODULE_SHUTTER


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
