"""Home Assistant integration tests (config flow + fan platform).

Run inside the harness:  python -m pytest integration/tests/test_integration.py -q
These exercise the real HA wrappers (config_flow, coordinator, fan), unlike
test_dv_engine.py which tests the pure logic.
"""

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from custom_components.dynamic_home import const

HW = {
    const.CONF_NAME: "VMC",
    const.CONF_SW_PWR: "switch.vmc_pwr",
    const.CONF_SW_V2: "switch.vmc_v2",
    const.CONF_SW_V3: "switch.vmc_v3",
    const.CONF_CO2: "sensor.co2",
    const.CONF_PM25: "sensor.pm25",
}


def _seed_states(hass: HomeAssistant, co2="500", pm="5") -> None:
    hass.states.async_set("switch.vmc_pwr", "off")
    hass.states.async_set("switch.vmc_v2", "off")
    hass.states.async_set("switch.vmc_v3", "off")
    hass.states.async_set("sensor.co2", co2)
    hass.states.async_set("sensor.pm25", pm)


async def _setup_entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(domain=const.DOMAIN, data=HW, options={},
                            title="VMC")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_config_flow_creates_entry(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        const.DOMAIN, context={"source": "user"})
    assert result["type"] == FlowResultType.MENU

    # pick the VMC module from the menu
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "vmc"})
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "vmc"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input=HW)
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "VMC"
    assert result["data"][const.CONF_CO2] == "sensor.co2"
    assert result["data"][const.CONF_MODULE] == const.MODULE_VMC


async def test_setup_creates_fan_and_numbers(hass: HomeAssistant) -> None:
    async_mock_service(hass, "switch", "turn_on")
    async_mock_service(hass, "switch", "turn_off")
    _seed_states(hass)

    entry = await _setup_entry(hass)
    assert entry.state is ConfigEntryState.LOADED

    fan = hass.states.get("fan.vmc")
    assert fan is not None
    # Four IAQ threshold numbers created.
    numbers = [s for s in hass.states.async_all("number")
               if s.entity_id.startswith("number.")]
    assert len(numbers) >= 4


async def test_observe_mode_computes_but_does_not_touch_relays(
        hass: HomeAssistant) -> None:
    """Dry-run: the decision is still computed, but no relay service is called."""
    on_calls = async_mock_service(hass, "switch", "turn_on")
    off_calls = async_mock_service(hass, "switch", "turn_off")
    _seed_states(hass, co2="500", pm="5")

    entry = await _setup_entry(hass)
    co = hass.data[const.DOMAIN][entry.entry_id]
    co.observe_enabled = True            # enter observe (dry-run) mode
    co.state_data.co2_ema = 0
    co.state_data.pm_ema = 0
    n_on, n_off = len(on_calls), len(off_calls)

    hass.states.async_set("sensor.co2", "1500")
    await hass.async_block_till_done()
    await co.async_request_refresh()
    await hass.async_block_till_done()

    # Decision still reaches V3 (and current_speed tracks it)...
    assert co.data.speed == 3
    assert co.current_speed == 3
    # ...but no new relay calls were issued while observing.
    assert len(on_calls) == n_on
    assert len(off_calls) == n_off


async def test_auto_raises_speed_on_high_co2(hass: HomeAssistant) -> None:
    async_mock_service(hass, "switch", "turn_on")
    async_mock_service(hass, "switch", "turn_off")
    _seed_states(hass, co2="500", pm="5")

    entry = await _setup_entry(hass)
    coordinator = hass.data[const.DOMAIN][entry.entry_id]
    # Disable EMA so the test is deterministic on a single reading.
    coordinator.state_data.co2_ema = 0
    coordinator.state_data.pm_ema = 0

    # CO2 spikes -> IAQ-triggered refresh should push to V3.
    hass.states.async_set("sensor.co2", "1500")
    await hass.async_block_till_done()
    await coordinator.async_request_refresh()
    await hass.async_block_till_done()

    assert coordinator.data.speed == 3
    # The fan applied V3 to the hardware (current_speed tracks the driver).
    assert coordinator.current_speed == 3


async def test_vmc_telemetry_entities(hass: HomeAssistant) -> None:
    async_mock_service(hass, "switch", "turn_on")
    async_mock_service(hass, "switch", "turn_off")
    _seed_states(hass)
    entry = await _setup_entry(hass)
    co = hass.data[const.DOMAIN][entry.entry_id]

    # Telemetry sensors exist.
    for eid in ("sensor.vmc_machine_hours", "sensor.vmc_hours_v1",
                "sensor.vmc_filter_hours", "sensor.vmc_speed"):
        assert hass.states.get(eid) is not None, eid

    # Filter reset button zeroes the counter.
    co.filter_hours = 12.0
    await hass.services.async_call(
        "button", "press",
        {"entity_id": "button.vmc_reset_filter_hours"}, blocking=True)
    await hass.async_block_till_done()
    assert co.filter_hours == 0.0


async def test_adaptive_thresholds_produced_from_history(hass: HomeAssistant) -> None:
    async_mock_service(hass, "switch", "turn_on")
    async_mock_service(hass, "switch", "turn_off")
    _seed_states(hass)
    entry = await _setup_entry(hass)
    co = hass.data[const.DOMAIN][entry.entry_id]

    co.adaptive_enabled = True
    cfg = co._cfg()
    # Not enough samples yet -> None.
    assert co._update_adaptive(cfg, 600, 5)[0] is None
    # Feed >100 varied readings -> percentiles become available.
    for i in range(150):
        co._update_adaptive(cfg, 500 + (i % 200), 3 + (i % 10))
    co2_v2, co2_v3, pm_v2, pm_v3 = co._update_adaptive(cfg, 600, 5)
    assert co2_v2 is not None and co2_v3 is not None
    assert co2_v3 >= co2_v2          # p95 >= p90
    assert pm_v2 is not None and pm_v3 >= pm_v2


async def test_dry_mode_anticondensation(hass: HomeAssistant) -> None:
    """Dry mode ventilates when indoor air is near its dew point."""
    async_mock_service(hass, "switch", "turn_on")
    async_mock_service(hass, "switch", "turn_off")
    _seed_states(hass)
    hass.states.async_set("sensor.t_in", "22")
    hass.states.async_set("sensor.t_ext", "10")
    hass.states.async_set("sensor.rh_in", "95")   # humid indoor -> dew risk
    hass.states.async_set("sensor.rh_ext", "50")  # drier outside

    entry = MockConfigEntry(domain=const.DOMAIN, title="VMC", options={}, data={
        **HW,
        const.CONF_T_IN: "sensor.t_in", const.CONF_T_EXT: "sensor.t_ext",
        const.CONF_HUM_IN: "sensor.rh_in", const.CONF_HUM_EXT: "sensor.rh_ext",
    })
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    co = hass.data[const.DOMAIN][entry.entry_id]

    co.dry_mode_enabled = True
    await co.async_refresh()
    await hass.async_block_till_done()
    # Stage-3 dry mode active -> ventilates (drier outside air).
    assert co.data.reason == "dry_mode"
    assert co.data.speed >= 2


async def test_freecool_suppressed_by_house_heating_changeover(
        hass: HomeAssistant) -> None:
    """F37: the house heating season blocks DV free-cooling (don't vent heat)."""
    async_mock_service(hass, "switch", "turn_on")
    async_mock_service(hass, "switch", "turn_off")
    _seed_states(hass)
    hass.states.async_set("sensor.t_in", "24")           # warm inside
    hass.states.async_set("sensor.t_ext", "15")          # cooler outside -> free-cool
    entry = MockConfigEntry(domain=const.DOMAIN, title="VMC", options={}, data={
        **HW,
        const.CONF_T_IN: "sensor.t_in", const.CONF_T_EXT: "sensor.t_ext",
    })
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    co = hass.data[const.DOMAIN][entry.entry_id]

    await co.async_refresh()
    await hass.async_block_till_done()
    assert co.state_data.freecool_active is True          # no changeover -> free-cools

    # House heating season -> free-cooling suppressed (mild winter day).
    hass.data[const.DOMAIN][const.DATA_CHANGEOVER] = {"state": "heat"}
    await co.async_refresh()
    await hass.async_block_till_done()
    assert co.state_data.freecool_active is False


async def test_freecool_no_changeover_advisory_repair(hass: HomeAssistant) -> None:
    """F37/F07: warn when free-cooling + a heating zone + no changeover coexist."""
    from types import SimpleNamespace

    from homeassistant.helpers import issue_registry as ir
    async_mock_service(hass, "switch", "turn_on")
    async_mock_service(hass, "switch", "turn_off")
    _seed_states(hass)
    hass.states.async_set("sensor.t_in", "22")
    hass.states.async_set("sensor.t_ext", "12")          # free-cooling enabled
    entry = MockConfigEntry(domain=const.DOMAIN, title="VMC", options={}, data={
        **HW,
        const.CONF_T_IN: "sensor.t_in", const.CONF_T_EXT: "sensor.t_ext",
    })
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    co = hass.data[const.DOMAIN][entry.entry_id]
    reg = ir.async_get(hass)
    issue_id = f"freecool_no_changeover_{entry.entry_id}"

    # A heating zone exists and no changeover is configured -> advisory raised.
    hass.data[const.DOMAIN]["dc1"] = SimpleNamespace(hvac_mode="heat")
    await co.async_refresh()
    await hass.async_block_till_done()
    issue = reg.async_get_issue(const.DOMAIN, issue_id)
    assert issue is not None
    assert issue.translation_key == const.ISSUE_FREECOOL_NO_CHANGEOVER

    # Configure a changeover -> the season is known -> cleared.
    hass.data[const.DOMAIN][const.DATA_CHANGEOVER] = {"state": "heat"}
    await co.async_refresh()
    await hass.async_block_till_done()
    assert reg.async_get_issue(const.DOMAIN, issue_id) is None

    # No changeover, but the only zone is cooling (not heating) -> no advisory.
    del hass.data[const.DOMAIN][const.DATA_CHANGEOVER]
    hass.data[const.DOMAIN]["dc1"].hvac_mode = "cool"
    await co.async_refresh()
    await hass.async_block_till_done()
    assert reg.async_get_issue(const.DOMAIN, issue_id) is None


async def test_anticipatory_switch_wires_to_cfg(hass: HomeAssistant) -> None:
    """F11: the anticipatory switch exists and its gate reaches the engine cfg."""
    from homeassistant.helpers import entity_registry as er
    async_mock_service(hass, "switch", "turn_on")
    async_mock_service(hass, "switch", "turn_off")
    _seed_states(hass)
    entry = await _setup_entry(hass)
    co = hass.data[const.DOMAIN][entry.entry_id]

    reg = er.async_get(hass)
    assert reg.async_get_entity_id(
        "switch", const.DOMAIN, f"{entry.entry_id}_anticipatory") is not None
    # Default off; flipping the coordinator gate reaches the engine config.
    assert co.anticip_enabled is False
    assert co._cfg().anticip_enabled is False
    co.anticip_enabled = True
    assert co._cfg().anticip_enabled is True


async def test_hrv_efficiency_sensor_present_with_probes(hass: HomeAssistant) -> None:
    """F28: with the 3 HRV probes, the efficiency sensor appears and computes η."""
    from homeassistant.helpers import entity_registry as er
    async_mock_service(hass, "switch", "turn_on")
    async_mock_service(hass, "switch", "turn_off")
    _seed_states(hass)
    # Winter recovery: intake 0 °C, extract 22 °C return, supply 18 °C.
    hass.states.async_set("sensor.hrv_supply", "18")
    hass.states.async_set("sensor.hrv_intake", "0")
    hass.states.async_set("sensor.hrv_extract", "22")

    entry = MockConfigEntry(domain=const.DOMAIN, title="VMC", options={}, data={
        **HW,
        const.CONF_HRV_SUPPLY: "sensor.hrv_supply",
        const.CONF_HRV_INTAKE: "sensor.hrv_intake",
        const.CONF_HRV_EXTRACT: "sensor.hrv_extract",
    })
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    co = hass.data[const.DOMAIN][entry.entry_id]

    assert co.has_hrv() is True
    assert abs(co.hrv_efficiency_pct - 81.8) < 0.5
    assert co.hrv_state == "recovering"

    eid = er.async_get(hass).async_get_entity_id(
        "sensor", const.DOMAIN, f"{entry.entry_id}_hrv_efficiency")
    assert eid is not None
    assert hass.states.get(eid).attributes["state"] == "recovering"


async def test_hrv_efficiency_sensor_absent_without_probes(hass: HomeAssistant) -> None:
    from homeassistant.helpers import entity_registry as er
    async_mock_service(hass, "switch", "turn_on")
    async_mock_service(hass, "switch", "turn_off")
    _seed_states(hass)
    entry = await _setup_entry(hass)
    co = hass.data[const.DOMAIN][entry.entry_id]

    assert co.has_hrv() is False
    eid = er.async_get(hass).async_get_entity_id(
        "sensor", const.DOMAIN, f"{entry.entry_id}_hrv_efficiency")
    assert eid is None


async def test_voc_sensor_present_and_observation_only(hass: HomeAssistant) -> None:
    """F30: VOC is exposed but never actuates — only CO₂/PM2.5 raise the speed."""
    from homeassistant.helpers import entity_registry as er
    async_mock_service(hass, "switch", "turn_on")
    async_mock_service(hass, "switch", "turn_off")
    _seed_states(hass, co2="500", pm="5")
    hass.states.async_set("sensor.voc", "900")     # high VOC

    entry = MockConfigEntry(domain=const.DOMAIN, title="VMC", options={},
                            data={**HW, const.CONF_VOC: "sensor.voc"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    co = hass.data[const.DOMAIN][entry.entry_id]

    # VOC sensor exists and mirrors the reading.
    assert co.has_voc() is True
    eid = er.async_get(hass).async_get_entity_id(
        "sensor", const.DOMAIN, f"{entry.entry_id}_voc")
    assert eid is not None
    assert float(hass.states.get(eid).state) == 900.0

    # High VOC with clean CO₂/PM does NOT raise the speed (observation only).
    assert co.data.speed == 1

    # CO₂ rising DOES raise it (the actuators are CO₂/PM2.5).
    co.state_data.co2_ema = 0            # reset EMA so the next reading bootstraps
    hass.states.async_set("sensor.co2", "1400")
    await co.async_refresh()
    await hass.async_block_till_done()
    assert co.data.speed == 3


async def test_voc_sensor_absent_without_probe(hass: HomeAssistant) -> None:
    from homeassistant.helpers import entity_registry as er
    async_mock_service(hass, "switch", "turn_on")
    async_mock_service(hass, "switch", "turn_off")
    _seed_states(hass)
    entry = await _setup_entry(hass)
    co = hass.data[const.DOMAIN][entry.entry_id]

    assert co.has_voc() is False
    eid = er.async_get(hass).async_get_entity_id(
        "sensor", const.DOMAIN, f"{entry.entry_id}_voc")
    assert eid is None


async def test_quiet_hours_entities_wire_to_cfg(hass: HomeAssistant) -> None:
    """F12: quiet-hours switch/number/time exist and reach the engine cfg."""
    from datetime import time as dtime

    from homeassistant.helpers import entity_registry as er
    async_mock_service(hass, "switch", "turn_on")
    async_mock_service(hass, "switch", "turn_off")
    _seed_states(hass)
    entry = await _setup_entry(hass)
    co = hass.data[const.DOMAIN][entry.entry_id]

    reg = er.async_get(hass)
    for platform, key in (("switch", "quiet_hours"), ("number", "quiet_max_level"),
                          ("time", "quiet_start"), ("time", "quiet_end")):
        assert reg.async_get_entity_id(
            platform, const.DOMAIN, f"{entry.entry_id}_{key}") is not None, key

    co.quiet_enabled = True
    co.quiet_max_level = 2
    co.quiet_start = dtime(22, 30)
    cfg = co._cfg()
    assert cfg.quiet_enabled is True and cfg.quiet_max_level == 2
    assert cfg.quiet_start_min == 22 * 60 + 30


async def test_dry_mode_blocked_when_outdoor_humid(hass: HomeAssistant) -> None:
    """F13: with the outdoor air as humid as indoors, drying must NOT ventilate."""
    async_mock_service(hass, "switch", "turn_on")
    async_mock_service(hass, "switch", "turn_off")
    _seed_states(hass)
    # Same temp + RH inside and out -> dp_diff ~ 0 (no dew-point advantage),
    # while indoor is still near its dew point (dew_risk holds).
    hass.states.async_set("sensor.t_in", "22")
    hass.states.async_set("sensor.t_ext", "22")
    hass.states.async_set("sensor.rh_in", "95")
    hass.states.async_set("sensor.rh_ext", "95")

    entry = MockConfigEntry(domain=const.DOMAIN, title="VMC", options={}, data={
        **HW,
        const.CONF_T_IN: "sensor.t_in", const.CONF_T_EXT: "sensor.t_ext",
        const.CONF_HUM_IN: "sensor.rh_in", const.CONF_HUM_EXT: "sensor.rh_ext",
    })
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    co = hass.data[const.DOMAIN][entry.entry_id]

    co.dry_mode_enabled = True
    await co.async_refresh()
    await hass.async_block_till_done()
    # Gate closed -> falls through to the IAQ/auto path (clean air seeded).
    assert co.data.reason != "dry_mode"


async def test_weekly_schedule_builds_cfg(hass: HomeAssistant) -> None:
    from datetime import time as dtime
    async_mock_service(hass, "switch", "turn_on")
    async_mock_service(hass, "switch", "turn_off")
    _seed_states(hass)
    entry = await _setup_entry(hass)
    co = hass.data[const.DOMAIN][entry.entry_id]

    # Disabled -> engine schedule off.
    assert co._cfg().schedule_enabled is False
    # Enable with an 08:00-22:00 window -> applied to all 7 days.
    co.schedule_enabled = True
    co.schedule_on = dtime(8, 0)
    co.schedule_off = dtime(22, 0)
    cfg = co._cfg()
    assert cfg.schedule_enabled is True
    assert len(cfg.schedule) == 7
    assert cfg.schedule[0] == (8 * 60, 22 * 60)


# --- F35: coordinated extractor hood (3 relays, one per speed) ---
HW_HOOD = {
    **HW,
    const.CONF_HOOD_V1: "switch.hood_v1",
    const.CONF_HOOD_V2: "switch.hood_v2",
    const.CONF_HOOD_V3: "switch.hood_v3",
}


async def _setup_hood(hass: HomeAssistant) -> MockConfigEntry:
    for e in ("switch.hood_v1", "switch.hood_v2", "switch.hood_v3"):
        hass.states.async_set(e, "off")
    entry = MockConfigEntry(domain=const.DOMAIN, data=HW_HOOD, options={},
                            title="VMC")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_hood_created_and_auto_speed(hass: HomeAssistant) -> None:
    from homeassistant.helpers import entity_registry as er
    async_mock_service(hass, "switch", "turn_on")
    async_mock_service(hass, "switch", "turn_off")
    _seed_states(hass, pm="5")
    entry = await _setup_hood(hass)
    co = hass.data[const.DOMAIN][entry.entry_id]
    assert co.has_hood() is True
    assert er.async_get(hass).async_get_entity_id(
        "fan", const.DOMAIN, f"{entry.entry_id}_hood") is not None
    assert co.hood_speed_auto == 0                  # low PM -> off
    hass.states.async_set("sensor.pm25", "60")      # cooking plume
    await co.async_refresh()
    await hass.async_block_till_done()
    assert co.hood_speed_auto == 2


async def test_hood_absent_without_relays(hass: HomeAssistant) -> None:
    from homeassistant.helpers import entity_registry as er
    async_mock_service(hass, "switch", "turn_on")
    async_mock_service(hass, "switch", "turn_off")
    _seed_states(hass)
    entry = await _setup_entry(hass)                # plain VMC, no hood
    co = hass.data[const.DOMAIN][entry.entry_id]
    assert co.has_hood() is False
    assert er.async_get(hass).async_get_entity_id(
        "fan", const.DOMAIN, f"{entry.entry_id}_hood") is None


def _hood_entity(hass: HomeAssistant, entry: MockConfigEntry):
    """The HoodFan instance (state-only relays aren't real switch entities, so we
    drive the entity directly and spy its relay calls)."""
    from homeassistant.helpers import entity_registry as er
    hood_id = er.async_get(hass).async_get_entity_id(
        "fan", const.DOMAIN, f"{entry.entry_id}_hood")
    comp = hass.data.get("entity_components", {}).get("fan") or hass.data["fan"]
    return comp.get_entity(hood_id)


async def test_hood_break_before_make(hass: HomeAssistant) -> None:
    _seed_states(hass)
    entry = await _setup_hood(hass)
    hood = _hood_entity(hass, entry)
    calls: list[tuple] = []

    async def _spy(ent, on):
        calls.append((ent, on))
    hood._switch = _spy

    await hood._apply_hood(2)
    # The two non-target relays are dropped *before* the target is energised.
    assert ("switch.hood_v1", False) in calls
    assert ("switch.hood_v3", False) in calls
    assert calls[-1] == ("switch.hood_v2", True)     # target closed last
    assert ("switch.hood_v2", False) not in calls    # target never opened here
    assert hood.coordinator.hood_current == 2


async def test_hood_interlock_corrects_double_on(hass: HomeAssistant) -> None:
    _seed_states(hass, pm="5")                        # auto speed 0
    entry = await _setup_hood(hass)
    hood = _hood_entity(hass, entry)
    calls: list[tuple] = []

    async def _spy(ent, on):
        calls.append((ent, on))
    hood._switch = _spy

    # Illegal: two speed relays energised at once -> interlock re-asserts (off all,
    # since the auto speed is 0).
    hass.states.async_set("switch.hood_v2", "on")
    hass.states.async_set("switch.hood_v3", "on")
    await hass.async_block_till_done()
    assert ("switch.hood_v2", False) in calls
    assert ("switch.hood_v3", False) in calls
    assert all(on is False for _, on in calls)       # nothing was energised


# --- F06: energy (kWh) sensor — estimate and real-meter paths ---
async def test_energy_sensor_estimate(hass: HomeAssistant) -> None:
    from homeassistant.helpers import entity_registry as er
    _seed_states(hass)
    entry = await _setup_entry(hass)
    co = hass.data[const.DOMAIN][entry.entry_id]

    # No power meter -> per-speed estimate: V2 (30 W) for one hour = 0.03 kWh.
    co.current_speed = 2
    co._accum_ts = 1000.0
    co._accumulate(1000.0 + 3600.0, co._cfg())
    assert abs(co.energy_kwh - 0.03) < 1e-9

    # The sensor exists and is wired for the Energy dashboard.
    eid = er.async_get(hass).async_get_entity_id(
        "sensor", const.DOMAIN, f"{entry.entry_id}_energy")
    assert eid is not None
    st = hass.states.get(eid)
    assert st.attributes["device_class"] == "energy"
    assert st.attributes["state_class"] == "total_increasing"


async def test_energy_sensor_uses_real_meter(hass: HomeAssistant) -> None:
    _seed_states(hass)
    hass.states.async_set("sensor.vmc_power", "500")       # W
    entry = MockConfigEntry(
        domain=const.DOMAIN, title="VMC",
        data={**HW, const.CONF_POWER_METER: "sensor.vmc_power"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    co = hass.data[const.DOMAIN][entry.entry_id]

    # Real meter integrated regardless of the logical speed: 500 W * 1 h = 0.5 kWh.
    co.current_speed = 1
    co._accum_ts = 1000.0
    co._accumulate(1000.0 + 3600.0, co._cfg())
    assert abs(co.energy_kwh - 0.5) < 1e-9


# --- F21: weekly scheduler — base speed floor / off window / editor ---
def _allday(value):
    return {str(d): [{"start": "00:00", "value": value}] for d in range(7)}


async def _setup_with_schedule(hass: HomeAssistant, value) -> MockConfigEntry:
    entry = MockConfigEntry(domain=const.DOMAIN, data=HW,
                            options={const.CONF_SCHEDULE: _allday(value)},
                            title="VMC")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_dv_schedule_floor_raises_speed(hass: HomeAssistant) -> None:
    from homeassistant.helpers import entity_registry as er
    _seed_states(hass, co2="500", pm="5")        # clean air -> IAQ base low
    entry = await _setup_with_schedule(hass, 2)   # slot floor = V2
    co = hass.data[const.DOMAIN][entry.entry_id]
    co.schedule_enabled = True
    co.state_data.co2_ema = 0
    hass.states.async_set("sensor.co2", "500")
    await hass.async_block_till_done()
    await co.async_request_refresh()
    await hass.async_block_till_done()
    assert co.data.speed == 2                      # floored up to the slot speed

    eid = er.async_get(hass).async_get_entity_id(
        "sensor", const.DOMAIN, f"{entry.entry_id}_schedule")
    assert eid is not None


async def test_dv_schedule_zero_turns_off(hass: HomeAssistant) -> None:
    _seed_states(hass, co2="500", pm="5")
    entry = await _setup_with_schedule(hass, 0)    # slot 0 -> off window
    co = hass.data[const.DOMAIN][entry.entry_id]
    co.schedule_enabled = True
    await co.async_request_refresh()
    await hass.async_block_till_done()
    assert co.data.speed == 0 and co.data.reason == "not_permitted"


async def test_dv_schedule_editor_persists(hass: HomeAssistant) -> None:
    _seed_states(hass)
    # The options flow keys off CONF_MODULE, so the entry must carry it.
    entry = MockConfigEntry(domain=const.DOMAIN, title="VMC",
                            data={**HW, const.CONF_MODULE: const.MODULE_VMC})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    flow = await hass.config_entries.options.async_configure(
        flow["flow_id"], {"next_step_id": "schedule"})
    flow = await hass.config_entries.options.async_configure(
        flow["flow_id"], {"day": "5"})
    flow = await hass.config_entries.options.async_configure(
        flow["flow_id"], {"start_1": "08:00:00", "value_1": "2"})
    await hass.async_block_till_done()
    assert entry.options[const.CONF_SCHEDULE]["5"] == [
        {"start": "08:00", "value": 2}]


# --- F13: multiple bathrooms for the shower boost ---
async def test_multi_bathroom_rh_delta_takes_max_and_names_it(
        hass: HomeAssistant) -> None:
    _seed_states(hass)
    hass.states.async_set("sensor.rh_ext", "40", {"device_class": "humidity"})
    hass.states.async_set("sensor.rh_pasillo", "55", {"device_class": "humidity"})
    hass.states.async_set("sensor.rh_dorm", "70", {"device_class": "humidity"})
    entry = MockConfigEntry(domain=const.DOMAIN, title="VMC",
                            data={**HW, const.CONF_MODULE: const.MODULE_VMC,
                                  const.CONF_HUM_EXT: "sensor.rh_ext"},
                            options={
                                "bath_name_1": "Baño pasillo",
                                "bath_hum_1": "sensor.rh_pasillo",
                                "bath_name_2": "Baño dormitorio",
                                "bath_hum_2": "sensor.rh_dorm"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    co = hass.data[const.DOMAIN][entry.entry_id]

    # Largest rise wins (dorm: 70-40=30 > pasillo: 55-40=15) and is named.
    assert co._rh_delta() == 30.0
    assert co.shower_bathroom == "Baño dormitorio"
    assert co._cfg().shower_enabled is True


async def test_single_legacy_hum_bath_still_works(hass: HomeAssistant) -> None:
    _seed_states(hass)
    hass.states.async_set("sensor.rh_ext", "40", {"device_class": "humidity"})
    hass.states.async_set("sensor.rh_bath", "62", {"device_class": "humidity"})
    entry = MockConfigEntry(domain=const.DOMAIN, title="VMC", data={
        **HW, const.CONF_MODULE: const.MODULE_VMC,
        const.CONF_HUM_BATH: "sensor.rh_bath",
        const.CONF_HUM_EXT: "sensor.rh_ext"}, options={})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    co = hass.data[const.DOMAIN][entry.entry_id]

    assert co._rh_delta() == 22.0           # 62 - 40, back-compat single sensor
    assert co.shower_bathroom is None        # legacy sensor is unnamed
    assert co._cfg().shower_enabled is True


async def test_bathrooms_options_step_saves_and_clears(hass: HomeAssistant) -> None:
    from homeassistant.data_entry_flow import FlowResultType
    _seed_states(hass)
    hass.states.async_set("sensor.rh1", "50", {"device_class": "humidity"})
    entry = MockConfigEntry(domain=const.DOMAIN, title="VMC",
                            data={**HW, const.CONF_MODULE: const.MODULE_VMC},
                            options={"bath_name_2": "viejo", "bath_hum_2": "sensor.x"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "bathrooms"})
    assert result["step_id"] == "bathrooms"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"bath_name_1": "Baño pasillo", "bath_hum_1": "sensor.rh1"})
    assert result["type"] == FlowResultType.CREATE_ENTRY

    assert entry.options["bath_name_1"] == "Baño pasillo"
    assert entry.options["bath_hum_1"] == "sensor.rh1"
    # An empty row clears a previously-set bathroom.
    assert "bath_hum_2" not in entry.options


async def test_adaptive_thresholds_exposed_on_fan(hass: HomeAssistant) -> None:
    """The learned CO2/PM thresholds + sample count surface as fan attributes."""
    async_mock_service(hass, "switch", "turn_on")
    async_mock_service(hass, "switch", "turn_off")
    _seed_states(hass)
    entry = await _setup_entry(hass)
    co = hass.data[const.DOMAIN][entry.entry_id]
    co.adaptive_enabled = True

    # Feed enough varied history for the percentiles to be available.
    cfg = co._cfg()
    for i in range(150):
        co._update_adaptive(cfg, 500 + (i % 200), 3 + (i % 10))
    await co.async_refresh()
    await hass.async_block_till_done()

    assert co.adaptive_samples >= 100
    assert co.adaptive_co2_v2 is not None and co.adaptive_co2_v3 is not None

    attrs = hass.states.get("fan.vmc").attributes
    assert attrs["adaptive_co2_v2"] == co.adaptive_co2_v2
    assert attrs["adaptive_co2_v3"] == co.adaptive_co2_v3
    assert attrs["adaptive_samples"] == co.adaptive_samples


async def test_hrv_efficiency_exposes_all_four_temperatures(
        hass: HomeAssistant) -> None:
    """The recuperator-efficiency sensor exposes all configured HRV temps."""
    from homeassistant.helpers import entity_registry as er
    async_mock_service(hass, "switch", "turn_on")
    async_mock_service(hass, "switch", "turn_off")
    _seed_states(hass)
    for e, v in [("sensor.hrv_sup", "21"), ("sensor.hrv_int", "8"),
                 ("sensor.hrv_ext", "22"), ("sensor.hrv_exh", "11")]:
        hass.states.async_set(e, v, {"device_class": "temperature"})
    entry = MockConfigEntry(domain=const.DOMAIN, title="VMC", options={}, data={
        **HW, const.CONF_MODULE: const.MODULE_VMC,
        const.CONF_HRV_SUPPLY: "sensor.hrv_sup",
        const.CONF_HRV_INTAKE: "sensor.hrv_int",
        const.CONF_HRV_EXTRACT: "sensor.hrv_ext",
        const.CONF_HRV_EXHAUST: "sensor.hrv_exh"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    co = hass.data[const.DOMAIN][entry.entry_id]
    await co.async_refresh()
    await hass.async_block_till_done()

    eid = er.async_get(hass).async_get_entity_id(
        "sensor", const.DOMAIN, f"{entry.entry_id}_hrv_efficiency")
    assert eid is not None
    a = hass.states.get(eid).attributes
    assert a["supply"] == 21 and a["intake"] == 8
    assert a["extract"] == 22 and a["exhaust"] == 11   # the new 4th temp
    # η = (21-8)/(22-8) = 92.9%
    assert float(hass.states.get(eid).state) > 90
