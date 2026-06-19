"""Home Assistant integration tests (config flow + fan platform).

Run inside the harness:  python -m pytest integration/tests/test_integration.py -q
These exercise the real HA wrappers (config_flow, coordinator, fan), unlike
test_engine.py which tests the pure logic.
"""

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntryState
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
