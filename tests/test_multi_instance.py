"""Multi-instance integration test: facade-targeted coordination.

One DC zone + two DS shutters on different facades. DC (cooling) publishes a
solar-shield intent to a single facade; only the shutter on that facade clamps.
"""

from homeassistant.core import HomeAssistant
from homeassistant.components.climate import HVACMode
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dynamic_home import const


def _seed(hass: HomeAssistant) -> None:
    hass.states.async_set("sensor.salon_temp", "27")
    hass.states.async_set("sensor.ext_temp", "33")
    # Sun due south, above the horizon -> only the south facade is lit.
    hass.states.async_set("sun.sun", "above_horizon",
                          {"azimuth": 180, "elevation": 30})
    hass.states.async_set("cover.south_real", "open", {"supported_features": 15})
    hass.states.async_set("cover.north_real", "open", {"supported_features": 15})


async def _add(hass: HomeAssistant, data: dict, title: str) -> MockConfigEntry:
    entry = MockConfigEntry(domain=const.DOMAIN, data=data, title=title)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_facade_targeted_multi_instance(hass: HomeAssistant) -> None:
    _seed(hass)

    # DC targets all shutters ("ds"); dynamic sun-aware targeting narrows it to
    # the facade actually lit by the sun.
    dc = await _add(hass, {
        const.CONF_NAME: "Zona",
        const.CONF_MODULE: const.MODULE_CLIMATE,
        const.CONF_DC_T_INT: "sensor.salon_temp",
        const.CONF_DC_T_EXT: "sensor.ext_temp",
        const.CONF_DC_TARGET: "ds",
    }, "Zona")

    south = await _add(hass, {
        const.CONF_NAME: "Sur",
        const.CONF_MODULE: const.MODULE_SHUTTER,
        const.CONF_COVER: "cover.south_real",
        const.CONF_FACADE_AZIMUTH: 180.0,
    }, "Sur")

    north = await _add(hass, {
        const.CONF_NAME: "Norte",
        const.CONF_MODULE: const.MODULE_SHUTTER,
        const.CONF_COVER: "cover.north_real",
        const.CONF_FACADE_AZIMUTH: 0.0,
    }, "Norte")

    dc_co = hass.data[const.DOMAIN][dc.entry_id]
    south_co = hass.data[const.DOMAIN][south.entry_id]
    north_co = hass.data[const.DOMAIN][north.entry_id]

    assert south_co.facade_key == "ds_f180"
    assert north_co.facade_key == "ds_f000"

    # Cool the zone -> DC publishes request_solar_shield to ds_f180.
    await hass.services.async_call(
        "climate", "set_hvac_mode",
        {"entity_id": "climate.zona", "hvac_mode": HVACMode.COOL}, blocking=True)
    await hass.async_block_till_done()
    assert dc_co.data.published_intent == "request_solar_shield"

    await south_co.async_refresh()
    await north_co.async_refresh()
    await hass.async_block_till_done()

    # Only the south shutter (matching facade) clamps; north stays open.
    assert south_co.data.reason == "sdhb_solar_shield"
    assert south_co.data.pos == 30
    assert north_co.data.pos == 100
    assert north_co.data.reason != "sdhb_solar_shield"

    # --- Sun moves to the north-west: DC re-targets dynamically. ---
    hass.states.async_set("sun.sun", "above_horizon",
                          {"azimuth": 300, "elevation": 30})
    await dc_co.async_refresh()
    await south_co.async_refresh()
    await north_co.async_refresh()
    await hass.async_block_till_done()

    # Now the north facade is lit: it clamps and the south one reopens.
    assert north_co.data.reason == "sdhb_solar_shield"
    assert north_co.data.pos == 30
    assert south_co.data.pos == 100
    assert south_co.data.reason != "sdhb_solar_shield"
