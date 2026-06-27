"""Tests for Dynamic Weather (F33): pure helpers + HA integration."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..",
                                "custom_components", "dynamic_home"))

from homeassistant.core import HomeAssistant  # noqa: E402
from pytest_homeassistant_custom_component.common import (  # noqa: E402
    MockConfigEntry,
)
from weather_engine import (  # noqa: E402
    WxConfig,
    derive_alert,
    is_fresh,
    pick_source,
)

from custom_components.dynamic_home import const  # noqa: E402


# --- pure engine ---
def test_pick_source_first_available():
    assert pick_source([False, True, True]) == 1
    assert pick_source([True, False]) == 0
    assert pick_source([False, False]) is None


def test_is_fresh():
    cfg = WxConfig(stale_after_h=6)
    assert is_fresh(None, cfg) is True
    assert is_fresh(3600, cfg) is True
    assert is_fresh(6 * 3600 + 1, cfg) is False


def test_derive_alert():
    cfg = WxConfig(alert_wind_kmh=60, alert_precip_mm=10)
    assert derive_alert("lightning", 0, 0, cfg) is True
    assert derive_alert("sunny", 70, 0, cfg) is True
    assert derive_alert("sunny", 0, 12, cfg) is True
    assert derive_alert("sunny", 10, 1, cfg) is False
    assert derive_alert(None, None, None, cfg) is False


# --- integration ---
WX = {
    const.CONF_NAME: "Meteo",
    const.CONF_MODULE: const.MODULE_WEATHER,
    const.CONF_WX_SOURCE_1: "weather.primary",
    const.CONF_WX_SOURCE_2: "weather.secondary",
    const.CONF_WX_TEMP: "sensor.wx_temp",
}


def _seed(hass: HomeAssistant) -> None:
    hass.states.async_set("weather.primary", "sunny",
                          {"temperature": 20.0, "humidity": 50, "wind_speed": 10})
    hass.states.async_set("weather.secondary", "cloudy",
                          {"temperature": 19.0, "wind_speed": 8})
    hass.states.async_set("sensor.wx_temp", "18.0")


async def _setup(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(domain=const.DOMAIN, data=WX, title="Meteo")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_weather_entities_and_primary_active(hass: HomeAssistant) -> None:
    from homeassistant.helpers import entity_registry as er
    _seed(hass)
    entry = await _setup(hass)
    co = hass.data[const.DOMAIN][entry.entry_id]
    reg = er.async_get(hass)
    # Proxy weather + alert binary_sensor + active-source diagnostic exist.
    assert reg.async_get_entity_id("weather", const.DOMAIN,
                                   f"{entry.entry_id}_weather") is not None
    assert reg.async_get_entity_id("binary_sensor", const.DOMAIN,
                                   f"{entry.entry_id}_wx_alert") is not None
    assert reg.async_get_entity_id("sensor", const.DOMAIN,
                                   f"{entry.entry_id}_wx_source") is not None
    # Primary source is active and mirrored.
    assert co.active_label == "weather.primary"
    assert co.active_entity == "weather.primary"
    assert co.data.condition == "sunny" and co.data.temperature == 20.0


async def test_weather_falls_back_to_secondary_then_sensors(
        hass: HomeAssistant) -> None:
    _seed(hass)
    entry = await _setup(hass)
    co = hass.data[const.DOMAIN][entry.entry_id]

    # Primary goes down -> secondary serves.
    hass.states.async_set("weather.primary", "unavailable")
    await co.async_refresh()
    await hass.async_block_till_done()
    assert co.active_label == "weather.secondary"
    assert co.data.temperature == 19.0

    # Both weather sources down -> raw-sensor fallback.
    hass.states.async_set("weather.secondary", "unavailable")
    await co.async_refresh()
    await hass.async_block_till_done()
    assert co.active_label == "sensors"
    assert co.active_entity is None
    assert co.data.temperature == 18.0


async def test_weather_alert_from_active_source(hass: HomeAssistant) -> None:
    _seed(hass)
    entry = await _setup(hass)
    co = hass.data[const.DOMAIN][entry.entry_id]
    assert co.alert_active is False

    hass.states.async_set("weather.primary", "lightning-rainy",
                          {"temperature": 18.0})
    await co.async_refresh()
    await hass.async_block_till_done()
    assert co.alert_active is True
    alert = hass.states.get("binary_sensor.meteo_weather_alert")
    assert alert is not None and alert.state == "on"
