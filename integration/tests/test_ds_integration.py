"""Home Assistant integration tests for the DS (shutter) module.

Covers the config flow (menu -> shutter), entity creation, and — crucially —
the cross-module coordination: another module publishing ``request_solar_shield``
to the shared SDHB hub makes the cover clamp.
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
