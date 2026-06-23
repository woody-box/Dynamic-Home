"""Integration tests for presence fusion (F32) on the Zones entry."""

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dynamic_home import const, zones


def _zones_entry(hass: HomeAssistant, options: dict) -> MockConfigEntry:
    tree = zones.add_zone({}, "Salon")
    entry = MockConfigEntry(
        domain=const.DOMAIN, title="Zonas", unique_id="zones_singleton",
        data={const.CONF_NAME: "Zonas", const.CONF_MODULE: const.MODULE_ZONES},
        options={const.CONF_ZONES_TREE: tree, **options})
    entry.add_to_hass(hass)
    return entry


async def test_presence_occupied_publishes_and_exposes_entities(
        hass: HomeAssistant) -> None:
    hass.states.async_set("binary_sensor.salon_mmwave", "on")
    entry = _zones_entry(hass, {
        const.CONF_PRESENCE_SOURCES: {
            "salon": {"mmwave": ["binary_sensor.salon_mmwave"],
                      "door": ["binary_sensor.salon_door"]}},
        const.CONF_PRESENCE_AUTO: True,
        # Disable the sleep window so this test is independent of the wall clock.
        const.CONF_PRESENCE_TUNE: {"sleep_start_min": 0, "sleep_end_min": 0}})
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    pres = hass.data[const.DOMAIN][const.DATA_PRESENCE]
    assert pres["house"] == "occupied"
    assert pres["zones"]["salon"] is True
    assert pres["reasons"]["salon"] == "mmwave_hold"

    reg = er.async_get(hass)
    occ = reg.async_get_entity_id(
        "binary_sensor", const.DOMAIN, f"{entry.entry_id}_occupancy_salon")
    house = reg.async_get_entity_id(
        "binary_sensor", const.DOMAIN, f"{entry.entry_id}_house_presence")
    assert occ is not None and hass.states.get(occ).state == "on"
    assert house is not None and hass.states.get(house).state == "on"


async def test_presence_away_auto_drives_house_mode(hass: HomeAssistant) -> None:
    # No interior presence + phones not_home -> Away; auto-drive sets the mode.
    hass.states.async_set("binary_sensor.salon_mmwave", "off")
    hass.states.async_set("device_tracker.phone", "not_home")
    entry = _zones_entry(hass, {
        const.CONF_PRESENCE_SOURCES: {
            "salon": {"mmwave": ["binary_sensor.salon_mmwave"]}},
        const.CONF_PRESENCE_PHONES: ["device_tracker.phone"],
        const.CONF_PRESENCE_AUTO: True})
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert hass.data[const.DOMAIN][const.DATA_PRESENCE]["house"] == "away"
    # Auto-drive folded it into the F01 house mode.
    assert hass.data[const.DOMAIN][const.DATA_MODE]["house"] == "away"
    reg = er.async_get(hass)
    house = reg.async_get_entity_id(
        "binary_sensor", const.DOMAIN, f"{entry.entry_id}_house_presence")
    assert hass.states.get(house).state == "off"     # away -> not occupied


async def test_presence_auto_does_not_stomp_manual_boost(
        hass: HomeAssistant) -> None:
    hass.states.async_set("binary_sensor.salon_mmwave", "off")
    hass.states.async_set("device_tracker.phone", "not_home")
    entry = _zones_entry(hass, {
        const.CONF_PRESENCE_SOURCES: {
            "salon": {"mmwave": ["binary_sensor.salon_mmwave"]}},
        const.CONF_PRESENCE_PHONES: ["device_tracker.phone"],
        const.CONF_PRESENCE_AUTO: True})
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    co = hass.data[const.DOMAIN][entry.entry_id]

    # User picks Boost manually -> presence must not override it.
    co.house_mode = "boost"
    co.publish_presence(notify=False)
    assert co.house_mode == "boost"


async def test_changeover_auto_from_supply_water(hass: HomeAssistant) -> None:
    from homeassistant.helpers import entity_registry as er
    hass.states.async_set("sensor.supply", "12")        # cold water -> cooling
    entry = _zones_entry(hass, {const.CONF_CHANGEOVER_SENSOR: "sensor.supply"})
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert hass.data[const.DOMAIN][const.DATA_CHANGEOVER]["state"] == "cool"
    reg = er.async_get(hass)
    sensor = reg.async_get_entity_id(
        "sensor", const.DOMAIN, f"{entry.entry_id}_changeover_state")
    select = reg.async_get_entity_id(
        "select", const.DOMAIN, f"{entry.entry_id}_changeover")
    assert sensor is not None and hass.states.get(sensor).state == "cool"
    assert select is not None and hass.states.get(select).state == "auto"

    # Hot water -> heating.
    hass.states.async_set("sensor.supply", "33")
    co = hass.data[const.DOMAIN][entry.entry_id]
    await co.async_refresh()
    await hass.async_block_till_done()
    assert hass.data[const.DOMAIN][const.DATA_CHANGEOVER]["state"] == "heat"


async def test_changeover_manual_override(hass: HomeAssistant) -> None:
    hass.states.async_set("sensor.supply", "12")        # would be cooling in auto
    entry = _zones_entry(hass, {const.CONF_CHANGEOVER_SENSOR: "sensor.supply"})
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    co = hass.data[const.DOMAIN][entry.entry_id]
    co.changeover_manual = "heat"                        # force heating
    co.publish_changeover(notify=False)
    assert hass.data[const.DOMAIN][const.DATA_CHANGEOVER]["state"] == "heat"


async def test_presence_absent_keeps_zones_config_time(
        hass: HomeAssistant) -> None:
    # No presence configured -> no presence entities, no DATA_PRESENCE.
    entry = _zones_entry(hass, {})
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert const.DATA_PRESENCE not in hass.data[const.DOMAIN]
    reg = er.async_get(hass)
    assert reg.async_get_entity_id(
        "binary_sensor", const.DOMAIN, f"{entry.entry_id}_house_presence") is None
