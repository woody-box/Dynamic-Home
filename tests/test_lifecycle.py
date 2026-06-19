"""Lifecycle / regression tests for the audit fixes.

- Removing a climate zone clears its bus intents (no ghost solar-shield).
- The options flow only applies to the VMC module.
"""

from homeassistant.core import HomeAssistant
from homeassistant.components.climate import HVACMode
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dynamic_home import const


async def _add(hass: HomeAssistant, data: dict, title: str) -> MockConfigEntry:
    entry = MockConfigEntry(domain=const.DOMAIN, data=data, title=title)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_unload_climate_clears_bus(hass: HomeAssistant) -> None:
    hass.states.async_set("sensor.t", "27")
    hass.states.async_set("sun.sun", "above_horizon",
                          {"azimuth": 180, "elevation": 30})
    hass.states.async_set("cover.real", "open", {"supported_features": 15})

    dc = await _add(hass, {
        const.CONF_NAME: "Zona", const.CONF_MODULE: const.MODULE_CLIMATE,
        const.CONF_DC_T_INT: "sensor.t", const.CONF_DC_TARGET: "ds",
    }, "Zona")
    await _add(hass, {
        const.CONF_NAME: "Sur", const.CONF_MODULE: const.MODULE_SHUTTER,
        const.CONF_COVER: "cover.real", const.CONF_FACADE_AZIMUTH: 180.0,
    }, "Sur")

    hub = hass.data[const.DOMAIN]["_hub"]

    await hass.services.async_call(
        "climate", "set_hvac_mode",
        {"entity_id": "climate.zona", "hvac_mode": HVACMode.COOL}, blocking=True)
    await hass.async_block_till_done()
    assert hub.winner({"ds", "ds_f180"}) == "request_solar_shield"

    # Remove the climate zone -> its intent must disappear from the bus.
    assert await hass.config_entries.async_unload(dc.entry_id)
    await hass.async_block_till_done()
    assert hub.winner({"ds", "ds_f180"}) == "none"


async def test_options_flow_aborts_for_shutter(hass: HomeAssistant) -> None:
    hass.states.async_set("cover.real", "open", {"supported_features": 15})
    entry = await _add(hass, {
        const.CONF_NAME: "Sur", const.CONF_MODULE: const.MODULE_SHUTTER,
        const.CONF_COVER: "cover.real", const.CONF_FACADE_AZIMUTH: 180.0,
    }, "Sur")

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "no_options"
