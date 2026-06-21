"""Integration tests for the bus-conflict explainer (F02): sensors + events."""

from homeassistant.components.climate import HVACMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_capture_events,
)

from custom_components.dynamic_home import const

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
    entry = MockConfigEntry(domain=const.DOMAIN, data=data, options={}, title=title)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_bus_sensor_reports_solar_shield(hass: HomeAssistant) -> None:
    """DC cooling -> DS bus sensor shows the consumed solar-shield intent + why."""
    _seed(hass)
    await _add(hass, CLIMATE, "Salon")
    ds_entry = await _add(hass, SHUTTER, "Persiana")
    ds = hass.data[const.DOMAIN][ds_entry.entry_id]

    await hass.services.async_call(
        "climate", "set_hvac_mode",
        {"entity_id": "climate.salon", "hvac_mode": HVACMode.COOL}, blocking=True)
    await hass.async_block_till_done()
    await ds.async_refresh()
    await hass.async_block_till_done()

    assert ds.bus_explain["winner"] == "request_solar_shield"
    assert ds.bus_explain["source"] is not None
    assert ds.bus_explain["priority"] == 70

    state = hass.states.get("sensor.dynamic_home_bus_persiana")
    assert state is not None
    assert state.state == "request_solar_shield"
    assert state.attributes["priority"] == 70
    assert state.attributes["candidates"] >= 1


async def test_bus_sensors_share_one_device(hass: HomeAssistant) -> None:
    _seed(hass)
    dc_entry = await _add(hass, CLIMATE, "Salon")
    ds_entry = await _add(hass, SHUTTER, "Persiana")

    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)
    bus_device = dev_reg.async_get_device(
        identifiers={(const.DOMAIN, const.BUS_DEVICE_ID)})
    assert bus_device is not None

    for entry in (dc_entry, ds_entry):
        ent = ent_reg.async_get_entity_id(
            "sensor", const.DOMAIN, f"{entry.entry_id}_bus")
        assert ent is not None
        assert ent_reg.async_get(ent).device_id == bus_device.id


async def test_conflict_event_fired_on_winner_change(hass: HomeAssistant) -> None:
    _seed(hass)
    await _add(hass, CLIMATE, "Salon")
    ds_entry = await _add(hass, SHUTTER, "Persiana")
    ds = hass.data[const.DOMAIN][ds_entry.entry_id]

    captured = async_capture_events(hass, const.EVENT_CONFLICT)
    await hass.services.async_call(
        "climate", "set_hvac_mode",
        {"entity_id": "climate.salon", "hvac_mode": HVACMode.COOL}, blocking=True)
    await hass.async_block_till_done()
    await ds.async_refresh()
    await hass.async_block_till_done()

    shield = [e for e in captured
              if e.data.get("winner") == "request_solar_shield"]
    assert shield, "expected a conflict event when DS started consuming the shield"
    assert shield[0].data["module"] == const.MODULE_SHUTTER
