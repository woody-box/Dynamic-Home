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
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input=HW)
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "VMC"
    assert result["data"][const.CONF_CO2] == "sensor.co2"


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
    on_calls = async_mock_service(hass, "switch", "turn_on")
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
    # The driver should have switched a relay on (V3).
    assert any(c.data.get("entity_id") == "switch.vmc_v3" for c in on_calls)
