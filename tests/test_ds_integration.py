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


async def test_reason_human_sensor(hass: HomeAssistant) -> None:
    """The _human sensor shows the reason as text, with the raw code as attribute."""
    from homeassistant.helpers import entity_registry as er

    from custom_components.dynamic_home import reason_text
    _seed(hass)
    entry = await _setup(hass)
    co = hass.data[const.DOMAIN][entry.entry_id]
    await co.async_refresh()
    await hass.async_block_till_done()

    eid = er.async_get(hass).async_get_entity_id(
        "sensor", const.DOMAIN, f"{entry.entry_id}_reason_human")
    assert eid is not None
    st = hass.states.get(eid)
    assert st.state not in (None, "unknown", "unavailable")
    code = st.attributes["code"]
    assert st.state == reason_text.humanize(const.MODULE_SHUTTER, code)


async def test_external_cover_move_arms_override(hass: HomeAssistant) -> None:
    """A move of the underlying cover DH didn't command -> manual override."""
    async_mock_service(hass, "cover", "set_cover_position")
    _seed(hass, position=50)
    entry = await _setup(hass)
    co = hass.data[const.DOMAIN][entry.entry_id]
    await co.async_refresh()
    await hass.async_block_till_done()

    # DH settled on its own decision; no manual override yet.
    assert co.manual_pos is None
    target = co.data.pos if co.data else 100
    external = 5 if (target or 0) >= 50 else 95   # clearly different from DH's pos

    # Someone moves the physical cover directly (a button/automation/wall switch).
    hass.states.async_set("cover.salon_real", "open",
                          {"current_position": external, "supported_features": 15})
    await hass.async_block_till_done()
    assert co.manual_pos == external             # detected -> timed override armed

    # With the toggle off, a further external move is ignored.
    co.track_external = False
    co.clear_manual_override()
    await hass.async_block_till_done()
    other = 95 if external < 50 else 5
    hass.states.async_set("cover.salon_real", "open",
                          {"current_position": other, "supported_features": 15})
    await hass.async_block_till_done()
    assert co.manual_pos is None                 # not re-armed when tracking is off


async def test_external_move_in_progress_is_not_reversed(
        hass: HomeAssistant) -> None:
    """A wall-button move mid-travel must not be fought by the auto logic.

    While the cover is travelling on an external command (opening/closing that
    DH did not issue), the manual override is not armed yet — it only arms on
    the settled position. A coordinator tick in that window used to command its
    own target, reversing the user's move. The auto path must hold off until
    the cover settles (which then arms the override, as before).
    """
    from custom_components.dynamic_home.ds_engine import DsDecision
    _seed(hass, position=50)
    entry = await _setup(hass)
    # Mock AFTER setup: forwarding the cover platform loads the cover component,
    # which would otherwise re-register the real service over the mock.
    calls = async_mock_service(hass, "cover", "set_cover_position")
    co = hass.data[const.DOMAIN][entry.entry_id]
    # Pin DH's last command to the current position (no travel expected).
    co.async_set_updated_data(DsDecision(pos=50, reason="default"))
    await hass.async_block_till_done()
    n0 = len(calls)

    # Wall button: the physical cover starts travelling up (not DH's doing).
    hass.states.async_set("cover.salon_real", "opening",
                          {"current_position": 60, "supported_features": 15})
    await hass.async_block_till_done()

    # Mid-travel the auto logic wants a different position -> no counter-order.
    co.async_set_updated_data(DsDecision(pos=0, reason="night_insulate"))
    await hass.async_block_till_done()
    assert len(calls) == n0                      # held off, user's move respected

    # The cover settles where the user sent it -> manual override, as before.
    hass.states.async_set("cover.salon_real", "open",
                          {"current_position": 100, "supported_features": 15})
    await hass.async_block_till_done()
    assert co.manual_pos == 100


async def test_own_drive_travel_does_not_gate_auto(hass: HomeAssistant) -> None:
    """DH's own command travelling (opening/closing) must not trip the external
    hold-off: a newer decision mid-travel still re-commands the cover."""
    from custom_components.dynamic_home.ds_engine import DsDecision
    _seed(hass, position=50)
    entry = await _setup(hass)
    # Mock AFTER setup (see test above).
    calls = async_mock_service(hass, "cover", "set_cover_position")
    co = hass.data[const.DOMAIN][entry.entry_id]
    # DH itself commands 0 -> the cover starts closing (this IS our move).
    co.async_set_updated_data(DsDecision(pos=0, reason="night_insulate"))
    await hass.async_block_till_done()
    n0 = len(calls)
    assert n0 >= 1
    hass.states.async_set("cover.salon_real", "closing",
                          {"current_position": 30, "supported_features": 15})
    await hass.async_block_till_done()

    # A newer decision mid own-travel still drives (the gate is external-only).
    co.async_set_updated_data(DsDecision(pos=100, reason="dawn_ramp"))
    await hass.async_block_till_done()
    assert len(calls) == n0 + 1
    # And settling near DH's own target never arms a manual override.
    hass.states.async_set("cover.salon_real", "open",
                          {"current_position": 100, "supported_features": 15})
    await hass.async_block_till_done()
    assert co.manual_pos is None


async def test_dw_probabilities_and_gust_drive_ds(hass: HomeAssistant) -> None:
    """Dynamic Weather gust -> wind cap; storm/rain probability -> alert."""
    _seed(hass)
    entry = await _setup(hass)
    co = hass.data[const.DOMAIN][entry.entry_id]
    cfg = co._cfg()
    dw = const.DATA_WEATHER

    # No DW data -> no anticipatory alert.
    hass.data[const.DOMAIN][dw] = {"alert": False, "values": {}}
    co._alert_hold_until = 0.0
    assert co._weather_alert(cfg, 1000.0) is None

    # High storm probability -> protective close (alert_pct).
    hass.data[const.DOMAIN][dw] = {"alert": False, "values": {"storm_prob": 70}}
    assert co._weather_alert(cfg, 1000.0) == cfg.alert_pct

    # High rain probability -> rain protection position.
    co._alert_hold_until = 0.0
    hass.data[const.DOMAIN][dw] = {"alert": False, "values": {"precip_prob": 90}}
    assert co._weather_alert(cfg, 2000.0) == cfg.rain_close_pct

    # Both below their thresholds -> nothing.
    co._alert_hold_until = 0.0
    hass.data[const.DOMAIN][dw] = {"alert": False,
                                   "values": {"storm_prob": 10, "precip_prob": 10}}
    assert co._weather_alert(cfg, 3000.0) is None

    # A strong gust caps the opening even with no local wind sensor.
    hass.data[const.DOMAIN][dw] = {"alert": False, "values": {"gust": 80}}
    await co.async_refresh()
    await hass.async_block_till_done()
    assert co.data.reason == "meteo_wind_cap"

    # v0.97.1: the MEAN wind from Dynamic Weather also drives the cap (no local
    # sensor, no gust) — the proportional cap works from the provider alone.
    hass.data[const.DOMAIN][dw] = {"alert": False, "values": {"wind": 80}}
    await co.async_refresh()
    await hass.async_block_till_done()
    assert co.data.reason == "meteo_wind_cap"
    # Calm provider wind -> no cap.
    hass.data[const.DOMAIN][dw] = {"alert": False, "values": {"wind": 5}}
    await co.async_refresh()
    await hass.async_block_till_done()
    assert co.data.reason != "meteo_wind_cap"


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


async def test_weather_alert_reads_numeric_and_condition(
        hass: HomeAssistant) -> None:
    # Google Weather has no binary_sensors: the alert slots also take a numeric
    # sensor (gust km/h / probability %) or a condition/weather sensor.
    _seed(hass)
    data = {
        **SHUTTER,
        const.CONF_DS_ALERT_WIND: "sensor.google_gust",       # numeric km/h
        const.CONF_DS_ALERT_HAIL: "weather.google_casa",      # condition string
    }
    hass.states.async_set("sensor.google_gust", "10")
    hass.states.async_set("weather.google_casa", "sunny")
    entry = MockConfigEntry(domain=const.DOMAIN, data=data, title="Salon")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    co = hass.data[const.DOMAIN][entry.entry_id]
    cfg = co._cfg()  # gust threshold 50 km/h, hail pos 0, wind pos 50

    # Calm + clear -> no alert.
    assert co._weather_alert(cfg, 1000.0) is None
    # Gust above threshold -> wind protection position (50).
    hass.states.async_set("sensor.google_gust", "62")
    assert co._weather_alert(cfg, 1000.0) == 50
    # Condition turns to a storm -> hail protection (0) wins (most protective).
    hass.states.async_set("weather.google_casa", "lightning")
    assert co._weather_alert(cfg, 1000.0) == 0


# --- Rain source: binary_sensor on/off (back-compat) ---
async def test_rain_reads_binary_sensor(hass: HomeAssistant) -> None:
    _seed(hass)
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        data={**SHUTTER, const.CONF_RAIN: "binary_sensor.lluvia"},
        title="Salon")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    co = hass.data[const.DOMAIN][entry.entry_id]
    cfg = co._cfg()
    hass.states.async_set("binary_sensor.lluvia", "off")
    assert co._alert_on(const.CONF_RAIN, "rain", cfg) is False
    hass.states.async_set("binary_sensor.lluvia", "on")
    assert co._alert_on(const.CONF_RAIN, "rain", cfg) is True


# --- Rain source: numeric (precip mm) and condition sensors (Google Weather) ---
async def test_rain_reads_numeric_and_condition(hass: HomeAssistant) -> None:
    _seed(hass)
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        data={**SHUTTER, const.CONF_RAIN: "sensor.google_precip"},
        title="Salon")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    co = hass.data[const.DOMAIN][entry.entry_id]
    cfg = co._cfg()                        # rain_mm_min 0.1
    hass.states.async_set("sensor.google_precip", "0.0")
    assert co._alert_on(const.CONF_RAIN, "rain", cfg) is False
    hass.states.async_set("sensor.google_precip", "0.6")   # mm over threshold
    assert co._alert_on(const.CONF_RAIN, "rain", cfg) is True
    # A condition/weather sensor works too.
    hass.states.async_set("sensor.google_precip", "pouring")
    assert co._alert_on(const.CONF_RAIN, "rain", cfg) is True
    hass.states.async_set("sensor.google_precip", "sunny")
    assert co._alert_on(const.CONF_RAIN, "rain", cfg) is False


# --- Presence simulation (Away) ---
async def test_presence_sim_step_gating_and_jitter(hass: HomeAssistant) -> None:
    _seed(hass)
    entry = await _setup(hass)
    co = hass.data[const.DOMAIN][entry.entry_id]
    cfg = co._cfg()                       # sim_open 50, close 0, jitter 30 min

    # No mode published -> inactive.
    assert co._sim_step(cfg, True, 1000.0) is None
    # Not Away (home) -> inactive even with sim on.
    hass.data[const.DOMAIN][const.DATA_MODE] = {
        "house": "home", "zones": {}, "tree": {}, "presence_sim": True}
    assert co._sim_step(cfg, True, 1000.0) is None
    # Away + sim on -> active; first call snaps to the real sun phase (day open).
    hass.data[const.DOMAIN][const.DATA_MODE]["house"] = "away"
    assert co._sim_step(cfg, True, 1000.0) == cfg.sim_open_pct
    # Sun sets -> holds the day position until the jitter window elapses...
    assert co._sim_step(cfg, False, 1000.0) == cfg.sim_open_pct
    # ...then closes once past the max jitter.
    later = 1000.0 + cfg.sim_jitter_min * 60 + 1
    assert co._sim_step(cfg, False, later) == cfg.sim_close_pct
    # Excluded shutter -> inactive.
    co.sim_excluded = True
    assert co._sim_step(cfg, False, later) is None


# --- Global shutter peak config (from the Zones entry) ---
async def test_global_peak_overrides_per_shutter(hass: HomeAssistant) -> None:
    _seed(hass)
    entry = await _setup(hass)
    co = hass.data[const.DOMAIN][entry.entry_id]
    cfg = co._cfg()                       # own: max_zones 2, power 0, stagger 10

    # No global -> the shutter's own values.
    assert co._peak_params(cfg) == (cfg.peak_max_zones, cfg.peak_max_power_w,
                                    cfg.peak_stagger_s)
    # Global config published by Zones -> it wins for every shutter.
    hass.data[const.DOMAIN][const.DATA_MODE] = {
        "ds_peak": {"max_zones": 4, "max_power_w": 0.0, "stagger_s": 3.0}}
    assert co._peak_params(cfg) == (4, 0.0, 3.0)


# --- Master pause (from the Zones entry) ---
async def test_master_pause_gates_actuation(hass: HomeAssistant) -> None:
    _seed(hass)
    entry = await _setup(hass)
    co = hass.data[const.DOMAIN][entry.entry_id]

    assert co.observe_effective is False           # nothing paused
    # Per-module pause for shutters -> stops actuating.
    hass.data[const.DOMAIN][const.DATA_MODE] = {"pause": {"shutter": True}}
    assert co._paused() is True and co.observe_effective is True
    # A pause of another module doesn't touch DS.
    hass.data[const.DOMAIN][const.DATA_MODE] = {"pause": {"vmc": True}}
    assert co._paused() is False and co.observe_effective is False
    # Global pause hits DS too.
    hass.data[const.DOMAIN][const.DATA_MODE] = {"pause": {"all": True}}
    assert co.observe_effective is True


# --- DS reacts to Sleep mode + Eco/Comfort preset ---
async def test_sleep_mode_and_comfort_react_by_scope(hass: HomeAssistant) -> None:
    _seed(hass)
    entry = await _setup(hass)
    co = hass.data[const.DOMAIN][entry.entry_id]

    # No mode published -> no sleep, comfort = balanced (identity).
    assert co._sleep_pos(co._cfg()) is None
    base_floor = co._cfg().summer_min_open_pct

    # House in Sleep -> close to sleep_pct.
    hass.data[const.DOMAIN][const.DATA_MODE] = {
        "house": "sleep", "zones": {}, "tree": {}}
    assert co._sleep_pos(co._cfg()) == co._cfg().sleep_pct

    # Eco comfort -> shades harder (summer floor drops vs balanced).
    hass.data[const.DOMAIN][const.DATA_MODE] = {
        "house": "home", "zones": {}, "tree": {}, "comfort": "eco"}
    assert co._sleep_pos(co._cfg()) is None
    assert co._cfg().summer_min_open_pct < base_floor


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
    await hass.async_block_till_done()   # let the auto-created Común entry settle


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
    await hass.async_block_till_done()   # let the auto-created Común entry settle


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
    # Clean object_id is preserved; the short module code is a display-only suffix
    # so the managed cover is told apart from the physical one in dashboards.
    cover = hass.states.get("cover.salon")
    assert cover is not None
    assert cover.attributes["friendly_name"] == "Salon · DS"


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


async def test_ds_power_and_energy_window_sensors(hass: HomeAssistant) -> None:
    """Instantaneous power (W) + rolling 24 h / 30 d energy windows."""
    from homeassistant.helpers import entity_registry as er
    async_mock_service(hass, "cover", "set_cover_position")
    _seed(hass)
    entry = await _setup(hass)
    co = hass.data[const.DOMAIN][entry.entry_id]
    reg = er.async_get(hass)

    def eid(key):
        return reg.async_get_entity_id("sensor", const.DOMAIN,
                                       f"{entry.entry_id}_{key}")

    # All three entities exist, each with its own translation key (distinct
    # names, not all "Energy") and the right units/classes.
    for key in ("power", "energy_24h", "energy_30d"):
        assert eid(key) is not None, key
    for key in ("energy_24h", "energy_30d"):
        assert reg.async_get(eid(key)).translation_key == key, key
    p = hass.states.get(eid("power"))
    assert p.attributes["device_class"] == "power"
    e24 = hass.states.get(eid("energy_24h"))
    assert e24.attributes["unit_of_measurement"] == "kWh"

    # Idle: no move this cycle -> instantaneous power is 0.
    assert float(p.state) == 0.0

    # A commanded move accrues energy; the 24 h window reflects the consumption.
    co.lock_enabled = True
    co.lock_pct = 0
    await co.async_refresh()
    await hass.async_block_till_done()
    assert co.energy_kwh > 0.0
    assert float(hass.states.get(eid("energy_24h")).state) == round(
        co.energy_kwh, 3)
    assert float(hass.states.get(eid("energy_30d")).state) == round(
        co.energy_kwh, 3)


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
    assert float(_state("ds_temp_diff")) == -6.0          # 24 − 30
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

    # Nothing published -> no alert, and the source reads "none" (observability).
    assert co._weather_alert(cfg, 1000.0) is None
    assert co.alert_source == "none"
    # Module alert on -> protect at the generic alert position, source visible.
    hass.data[const.DOMAIN][const.DATA_WEATHER] = {"source": "weather.x", "alert": True}
    assert co._weather_alert(cfg, 1000.0) == cfg.alert_pct
    assert co.alert_source == "dynamic_weather"


async def test_ds_weather_protect_off_exempts_shutter(hass: HomeAssistant) -> None:
    """A covered-terrace shutter can opt out of all weather protection."""
    async_mock_service(hass, "cover", "set_cover_position")
    _seed(hass)
    entry = await _setup(hass)
    co = hass.data[const.DOMAIN][entry.entry_id]
    cfg = co._cfg()
    hass.data[const.DOMAIN][const.DATA_WEATHER] = {"source": "weather.x", "alert": True}

    # Default ON -> follows the module alert.
    assert co._weather_alert(cfg, 1000.0) == cfg.alert_pct
    # Switch off -> exempt (no alert, source reads "off").
    co.weather_protect = False
    assert co._weather_alert(cfg, 1000.0) is None
    assert co.alert_source == "off"


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
    assert co.alert_source == "local"


async def test_manual_override_hold_resume_and_expiry(hass: HomeAssistant) -> None:
    """A hand command pins the position; the resume button and the timeout clear it."""
    from homeassistant.helpers import entity_registry as er
    async_mock_service(hass, "cover", "set_cover_position")
    _seed(hass, position=100)
    entry = await _setup(hass)
    co = hass.data[const.DOMAIN][entry.entry_id]
    reg = er.async_get(hass)

    # Control-mode sensor starts in automatic.
    mid = reg.async_get_entity_id(
        "sensor", const.DOMAIN, f"{entry.entry_id}_ds_control_mode")
    assert mid is not None and hass.states.get(mid).state == "auto"

    # Hand command (what the managed cover does on a user move) arms the hold.
    co.arm_manual_override(80)
    await hass.async_block_till_done()
    assert co.manual_pos == 80
    assert co.data.reason == "manual_hold" and co.data.pos == 80
    # ...and the control-mode sensor flips to manual.
    assert hass.states.get(mid).state == "manual"

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
    assert hass.states.get(mid).state == "auto"        # back to automatic

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
    for key in ("ds_indoor_temp", "ds_outdoor_temp", "ds_temp_diff",
                "ds_climate_mode", "ds_climate_setpoint", "ds_climate_temp"):
        assert reg.async_get_entity_id(
            "sensor", const.DOMAIN, f"{entry.entry_id}_{key}") is None, key
    # The control-mode sensor, on the other hand, always exists (override applies
    # to any shutter).
    assert reg.async_get_entity_id(
        "sensor", const.DOMAIN, f"{entry.entry_id}_ds_control_mode") is not None


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


async def test_peak_never_defers_protected_moves(hass: HomeAssistant) -> None:
    # v0.94.2: the inrush budget must never defer — nor snap back to a mid-travel
    # snapshot — a manual hold, a lock or a weather protection (the third
    # instance of the trap pattern found in the audit).
    from custom_components.dynamic_home.ds_engine import DsConfig, DsDecision
    ca, cb = await _two_shutters(hass)
    ca.peak_enabled = cb.peak_enabled = True
    cfg = DsConfig(peak_max_zones=1, peak_stagger_s=0)
    assert ca._peak_gate(cfg, DsDecision(pos=0, reason="x"), 100, 1000.0).pos == 0
    # Budget is now full. A hand-opened shutter caught mid-travel (pos 10) must
    # keep driving to 100 — not get "held" back at 10.
    manual = DsDecision(pos=100, reason="manual_hold")
    db = cb._peak_gate(cfg, manual, 10, 1000.0)
    assert db.pos == 100 and db.reason == "manual_hold"
    assert cb.peak_reason == "protected"
    # A rain/hail closing is a protection: never deferred either.
    rain = DsDecision(pos=0, reason="meteo_rain")
    db = cb._peak_gate(cfg, rain, 100, 1000.0)
    assert db.pos == 0 and db.reason == "meteo_rain"


async def test_manual_hold_survives_restart(hass: HomeAssistant) -> None:
    # v0.94.2: a HA restart mid-hold must NOT hand the shutter back to the
    # automation — the hold is restored from the control-mode sensor's state.
    from homeassistant.core import State
    from homeassistant.helpers import entity_registry as er
    from homeassistant.util import dt as dt_util
    from pytest_homeassistant_custom_component.common import mock_restore_cache

    _seed(hass, position=50)
    entry = await _setup(hass)
    eid = er.async_get(hass).async_get_entity_id(
        "sensor", const.DOMAIN, f"{entry.entry_id}_ds_control_mode")
    assert eid is not None
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    until = dt_util.utcnow().timestamp() + 3600.0
    mock_restore_cache(hass, (State(eid, "manual",
                                    {"held_position": 100,
                                     "hold_until_ts": until}),))
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    co = hass.data[const.DOMAIN][entry.entry_id]
    assert co.manual_pos == 100
    assert co.manual_until == until

    # An already-expired hold is NOT restored (auto resumes normally).
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    mock_restore_cache(hass, (State(eid, "manual",
                                    {"held_position": 100,
                                     "hold_until_ts": until - 7200.0}),))
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    co = hass.data[const.DOMAIN][entry.entry_id]
    assert co.manual_pos is None


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


# --- House-wide shutter counts (open / closed / ajar), DS-managed covers only ---
def _common(hass: HomeAssistant):
    """The auto-created 'Dynamic Shutter · Común' coordinator, or None."""
    from custom_components.dynamic_home.coordinator import ShutterCommonCoordinator
    return next((co for co in hass.data.get(const.DOMAIN, {}).values()
                 if isinstance(co, ShutterCommonCoordinator)), None)


async def test_house_shutter_counts(hass: HomeAssistant) -> None:
    """Three shared sensors count DS-managed covers by position, not raw covers.

    The counts live on the auto-created 'Común' device now, not nested under a
    shutter.
    """
    from homeassistant.helpers import entity_registry as er
    async_mock_service(hass, "cover", "set_cover_position")
    hass.states.async_set("sun.sun", "below_horizon",
                          {"azimuth": 180, "elevation": -10})
    # Three managed shutters at 100 / 0 / 40 (open / closed / ajar).
    positions = {"cover.a": 100, "cover.b": 0, "cover.c": 40}
    for eid, pos in positions.items():
        hass.states.async_set(eid, "open",
                              {"supported_features": 15, "current_position": pos})
    for i, cover in enumerate(positions):
        data = {**SHUTTER, const.CONF_COVER: cover, const.CONF_NAME: f"P{i}"}
        e = MockConfigEntry(domain=const.DOMAIN, data=data, title=f"P{i}")
        e.add_to_hass(hass)
        assert await hass.config_entries.async_setup(e.entry_id)
    await hass.async_block_till_done()
    # The Común entry auto-created; re-tick it so the counts re-arm over all covers.
    common = _common(hass)
    assert common is not None
    await common.async_refresh()
    await hass.async_block_till_done()

    reg = er.async_get(hass)

    def count(key):
        eid = reg.async_get_entity_id("sensor", const.DOMAIN,
                                      f"{const.DOMAIN}_{key}")
        assert eid is not None, key
        return int(hass.states.get(eid).state)

    # One set only (on the Común device), counting the three managed covers.
    assert count("covers_open") == 1
    assert count("covers_closed") == 1
    assert count("covers_ajar") == 1

    # Move one open -> closed: the count sensor's own cover listener follows.
    hass.states.async_set("cover.a", "closed",
                          {"supported_features": 15, "current_position": 0})
    await hass.async_block_till_done()
    assert count("covers_open") == 0
    assert count("covers_closed") == 2


# --- Readable per-shutter sun sensor (day/night + elevation/azimuth + sun/shade)
async def test_ds_sun_sensor(hass: HomeAssistant) -> None:
    from homeassistant.helpers import entity_registry as er
    async_mock_service(hass, "cover", "set_cover_position")
    hass.states.async_set("cover.salon_real", "open", {"supported_features": 15})
    # Sun on the (south, 180°) facade: elevation 24.4, azimuth 180 -> in sun.
    hass.states.async_set("sun.sun", "above_horizon",
                          {"azimuth": 180.0, "elevation": 24.4})
    entry = await _setup(hass)
    reg = er.async_get(hass)
    eid = reg.async_get_entity_id("sensor", const.DOMAIN,
                                  f"{entry.entry_id}_ds_sun")
    assert eid is not None
    st = hass.states.get(eid)
    assert st.state == "Persiana al Sol"          # sun on the facade
    assert st.attributes["in_sun"] is True

    # Sun off the facade -> in the shade.
    hass.states.async_set("sun.sun", "above_horizon",
                          {"azimuth": 10.0, "elevation": 24.4})  # far from south
    co = hass.data[const.DOMAIN][entry.entry_id]
    await co.async_refresh()
    await hass.async_block_till_done()
    st = hass.states.get(eid)
    assert st.state == "Persiana a la Sombra" and st.attributes["in_sun"] is False


async def test_shared_sun_sensors(hass: HomeAssistant) -> None:
    """Day/night, elevation, azimuth and the sunrise/sunset windows live once on
    the shared 'Persianas' device."""
    from homeassistant.helpers import entity_registry as er
    from homeassistant.util import dt as dt_util
    async_mock_service(hass, "cover", "set_cover_position")
    hass.states.async_set("cover.salon_real", "open", {"supported_features": 15})
    hass.states.async_set("sun.sun", "above_horizon", {
        "azimuth": 180.0, "elevation": 60.2,
        "next_dawn": "2026-07-02T03:55:00+00:00",
        "next_rising": "2026-07-02T04:31:00+00:00",
        "next_setting": "2026-07-01T19:44:00+00:00",
        "next_dusk": "2026-07-01T20:19:00+00:00"})
    await _setup(hass)
    reg = er.async_get(hass)

    def state(key):
        eid = reg.async_get_entity_id("sensor", const.DOMAIN,
                                      f"{const.DOMAIN}_{key}")
        assert eid is not None, key
        return hass.states.get(eid)

    assert state("sun_day_night").state == "day"
    assert float(state("sun_elevation").state) == 60.2
    assert float(state("sun_azimuth").state) == 180.0
    # Windows shown as "De HH:MM a HH:MM" in local time (compute the expected
    # edges with the same converter, so it holds under any test timezone).
    def rng(a, b):
        la = dt_util.as_local(dt_util.parse_datetime(a))
        lb = dt_util.as_local(dt_util.parse_datetime(b))
        return f"De {la:%H:%M} a {lb:%H:%M}"

    assert state("sunrise").state == rng(
        "2026-07-02T03:55:00+00:00", "2026-07-02T04:31:00+00:00")
    assert state("sunset").state == rng(
        "2026-07-01T19:44:00+00:00", "2026-07-01T20:19:00+00:00")
    assert state("sunrise").attributes["start"] is not None


# --- Curated tunables as CONFIG numbers (in sync with the options menu) ---
async def test_config_number_entities(hass: HomeAssistant) -> None:
    from homeassistant.helpers import entity_registry as er
    async_mock_service(hass, "cover", "set_cover_position")
    _seed(hass)
    entry = await _setup(hass)
    reg = er.async_get(hass)

    def ent(key):
        eid = reg.async_get_entity_id("number", const.DOMAIN,
                                      f"{entry.entry_id}_{key}")
        assert eid is not None, key
        return eid

    # The curated numbers exist, in the "config" entity category.
    for key in ("wind_limit_kmh", "hot_delta", "weather_max_open_pct",
                "override_hours", "lock_pct"):
        assert reg.async_get(ent(key)).entity_category == er.EntityCategory.CONFIG

    # Default values (from DsConfig): wind 40, hot ΔT 0.8, weather max 30.
    assert float(hass.states.get(ent("wind_limit_kmh")).state) == 40.0
    assert float(hass.states.get(ent("hot_delta")).state) == 0.8
    assert float(hass.states.get(ent("weather_max_open_pct")).state) == 30.0
    # Override shown in minutes (stored 4 h -> 240 min).
    assert float(hass.states.get(ent("override_hours")).state) == 240.0

    # Setting a number writes the same option the menu edits (in sync).
    await hass.services.async_call(
        "number", "set_value",
        {"entity_id": ent("wind_limit_kmh"), "value": 55}, blocking=True)
    await hass.async_block_till_done()
    assert entry.options["wind_limit_kmh"] == 55
    # Override set in minutes -> stored back in hours.
    await hass.services.async_call(
        "number", "set_value",
        {"entity_id": ent("override_hours"), "value": 120}, blocking=True)
    await hass.async_block_till_done()
    assert entry.options["override_hours"] == 2.0


# --- v0.95.0: the coordinator feeds `night` -> the free-cool branch lives ---
async def test_freecool_night_opens_on_cool_summer_nights(
        hass: HomeAssistant) -> None:
    # Cool summer night (26 in / 22 out), cooling season, sun below the horizon:
    # the shutter opens to vent the thermal mass (freecool_night). This branch
    # was dead code before v0.95.0 (DsInputs.night was never filled in).
    async_mock_service(hass, "cover", "set_cover_position")
    _seed(hass)                                     # sun below horizon
    hass.states.async_set("climate.salon", "cool")
    hass.states.async_set("sensor.salon_in", "26")
    hass.states.async_set("sensor.salon_out", "22")
    entry = MockConfigEntry(domain=const.DOMAIN,
                            data={**SHUTTER,
                                  const.CONF_CLIMATE: "climate.salon",
                                  const.CONF_DS_T_IN: "sensor.salon_in",
                                  const.CONF_DS_T_OUT: "sensor.salon_out"},
                            title="Salon")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    co = hass.data[const.DOMAIN][entry.entry_id]
    await co.async_refresh()
    await hass.async_block_till_done()
    assert co.data.reason == "freecool_night"
    assert co.data.pos == co._cfg().freecool_max_open_pct


async def test_night_purge_latch_no_flapping(hass: HomeAssistant) -> None:
    # v0.95.0: the F16 purge has a latch (freecool_delta entry band): sensor
    # noise around t_in must not cycle the bedroom shutter up/down all night.
    _seed(hass)
    entry = await _setup(hass)
    co = hass.data[const.DOMAIN][entry.entry_id]
    co.night_iso_enabled = True
    cfg = co._cfg()                                  # freecool_delta = 0.8
    opened, closed = cfg.night_iso_open_pct, cfg.night_iso_close_pct
    assert co._night_iso(cfg, "cool", -10.0, 26.0, 25.0) == opened   # cooler
    assert co._night_iso(cfg, "cool", -10.0, 26.0, 25.9) == opened   # holds
    assert co._night_iso(cfg, "cool", -10.0, 26.0, 26.2) == closed   # warmer
    assert co._night_iso(cfg, "cool", -10.0, 26.0, 25.9) == closed   # holds


async def test_wind_cap_survives_anemometer_dropout(hass: HomeAssistant) -> None:
    # v0.96.0: the wind sensor flapping to unavailable mid-storm must not drop
    # the cap instantly — the last reading holds for a TTL, then lets go.
    _seed(hass)
    hass.states.async_set("sensor.wind", "55")
    entry = MockConfigEntry(domain=const.DOMAIN,
                            data={**SHUTTER, const.CONF_WIND: "sensor.wind"},
                            title="Salon")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    co = hass.data[const.DOMAIN][entry.entry_id]

    assert co._wind_with_ttl(1000.0) == 55.0               # live reading
    hass.states.async_set("sensor.wind", "unavailable")
    assert co._wind_with_ttl(1300.0) == 55.0               # dropout: held (5 min)
    assert co._wind_with_ttl(1000.0 + 700.0) is None       # TTL expired: let go


async def test_common_entry_autocreated_and_removed_with_last_shutter(
        hass: HomeAssistant) -> None:
    # v0.98.0: the shared "Común" entry auto-creates with the first shutter and
    # is removed with the last (no per-shutter owner / adoption dance anymore).
    from homeassistant.helpers import entity_registry as er
    ca, cb = await _two_shutters(hass)
    assert _common(hass) is not None
    reg = er.async_get(hass)
    assert reg.async_get_entity_id(
        "sensor", const.DOMAIN, f"{const.DOMAIN}_covers_open") is not None

    # Remove one shutter -> the Común stays (another shutter remains).
    await hass.config_entries.async_remove(ca.entry.entry_id)
    await hass.async_block_till_done()
    assert _common(hass) is not None

    # Remove the LAST shutter -> the Común is removed too.
    await hass.config_entries.async_remove(cb.entry.entry_id)
    await hass.async_block_till_done()
    assert _common(hass) is None
    assert not [e for e in hass.config_entries.async_entries(const.DOMAIN)
                if e.data.get(const.CONF_MODULE) == const.MODULE_SHUTTER_COMMON]


async def test_common_device_rehomed_off_shutter_on_upgrade(
        hass: HomeAssistant) -> None:
    # v0.98.1: after upgrading, the shared shutter device (counts + sun) keeps a
    # stale link to the first shutter in its config_entries, so it stays nested
    # under that shutter instead of standing alone. The shared entities already
    # belong to the Común entry (v0.98.0); only the device link is stale. A
    # reload of the Común entry must strip it without churning any entity.
    from homeassistant.helpers import device_registry as dr
    from homeassistant.helpers import entity_registry as er
    _seed(hass)
    ea = MockConfigEntry(domain=const.DOMAIN, data={**SHUTTER}, title="A")
    ea.add_to_hass(hass)
    # Pre-create the Común as a normal (reloadable) entry so the shutter's
    # auto-create step finds it and we exercise the real setup path on reload.
    common = MockConfigEntry(
        domain=const.DOMAIN, title="Dynamic Shutter · Común",
        unique_id="shutter_common_singleton",
        data={const.CONF_NAME: "Común",
              const.CONF_MODULE: const.MODULE_SHUTTER_COMMON})
    common.add_to_hass(hass)
    assert await hass.config_entries.async_setup(ea.entry_id)
    await hass.async_block_till_done()
    if common.state is not ConfigEntryState.LOADED:
        assert await hass.config_entries.async_setup(common.entry_id)
        await hass.async_block_till_done()
    dev_reg = dr.async_get(hass)
    reg = er.async_get(hass)
    device = dev_reg.async_get_device(
        identifiers={(const.DOMAIN, const.SHUTTERS_DEVICE_ID)})
    eid = reg.async_get_entity_id(
        "sensor", const.DOMAIN, f"{const.DOMAIN}_covers_open")

    # Simulate the leftover pre-0.98 link: the shutter still pinned to the device.
    dev_reg.async_update_device(device.id, add_config_entry_id=ea.entry_id)
    assert ea.entry_id in dev_reg.async_get(device.id).config_entries

    # Reload the Común entry -> its setup strips the stale shutter link.
    assert await hass.config_entries.async_reload(common.entry_id)
    await hass.async_block_till_done()

    device = dev_reg.async_get_device(
        identifiers={(const.DOMAIN, const.SHUTTERS_DEVICE_ID)})
    assert device.config_entries == {common.entry_id}   # only the Común owns it
    # The shared entity was untouched: same entity_id, still on the Común entry.
    assert reg.async_get_entity_id(
        "sensor", const.DOMAIN, f"{const.DOMAIN}_covers_open") == eid
    assert reg.async_get(eid).config_entry_id == common.entry_id


# --- v0.98.0: the "Común" screen + global switches ---
async def test_global_switch_fans_out_to_all_shutters(hass: HomeAssistant) -> None:
    from homeassistant.helpers import entity_registry as er
    ca, cb = await _two_shutters(hass)
    assert _common(hass) is not None
    reg = er.async_get(hass)
    eid = reg.async_get_entity_id(
        "switch", const.DOMAIN, f"{const.DOMAIN}_global_observe")
    assert eid is not None

    # Blunt master: ON puts EVERY shutter in observe (house-wide manual).
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": eid}, blocking=True)
    await hass.async_block_till_done()
    assert ca.observe_enabled is True and cb.observe_enabled is True
    assert hass.states.get(eid).state == "on"

    # OFF turns it off on all (house-wide automatic).
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": eid}, blocking=True)
    await hass.async_block_till_done()
    assert ca.observe_enabled is False and cb.observe_enabled is False

    # Master reads "on" only when ALL shutters have it on (blunt semantics).
    ca.observe_enabled = True                      # only one on
    async_dispatcher_send_test(hass)
    await hass.async_block_till_done()
    assert hass.states.get(eid).state == "off"


def async_dispatcher_send_test(hass):
    from homeassistant.helpers.dispatcher import async_dispatcher_send
    async_dispatcher_send(hass, const.SIGNAL_DS_TOGGLES)


async def test_global_resume_auto_clears_every_hold(hass: HomeAssistant) -> None:
    from homeassistant.helpers import entity_registry as er
    ca, cb = await _two_shutters(hass)
    ca.arm_manual_override(80)
    cb.arm_manual_override(20)
    assert ca.manual_pos == 80 and cb.manual_pos == 20
    reg = er.async_get(hass)
    eid = reg.async_get_entity_id(
        "button", const.DOMAIN, f"{const.DOMAIN}_global_resume_auto")
    assert eid is not None
    await hass.services.async_call(
        "button", "press", {"entity_id": eid}, blocking=True)
    await hass.async_block_till_done()
    assert ca.manual_pos is None and cb.manual_pos is None
