"""Integration tests for the dynamic_home.* services and their lifecycle."""

from homeassistant.components.climate import HVACMode
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from custom_components.dynamic_home import const

CLIMATE = {
    const.CONF_NAME: "Salon",
    const.CONF_MODULE: const.MODULE_CLIMATE,
    const.CONF_DC_T_INT: "sensor.salon_temp",
    const.CONF_DC_TARGET: "ds",
}

VMC = {
    const.CONF_NAME: "VMC",
    const.CONF_SW_PWR: "switch.vmc_pwr",
    const.CONF_SW_V2: "switch.vmc_v2",
    const.CONF_SW_V3: "switch.vmc_v3",
    const.CONF_CO2: "sensor.co2",
    const.CONF_PM25: "sensor.pm25",
}


def _seed(hass: HomeAssistant) -> None:
    hass.states.async_set("sensor.salon_temp", "22")
    hass.states.async_set("sensor.co2", "500")
    hass.states.async_set("sensor.pm25", "5")
    hass.states.async_set("switch.vmc_pwr", "off")
    hass.states.async_set("switch.vmc_v2", "off")
    hass.states.async_set("switch.vmc_v3", "off")
    async_mock_service(hass, "switch", "turn_on")
    async_mock_service(hass, "switch", "turn_off")


async def _add(hass: HomeAssistant, data: dict, title: str) -> MockConfigEntry:
    entry = MockConfigEntry(domain=const.DOMAIN, data=data, options={}, title=title)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_services_registered_after_setup(hass: HomeAssistant) -> None:
    _seed(hass)
    await _add(hass, CLIMATE, "Salon")
    for svc in (const.SERVICE_RESET_LEARNING, const.SERVICE_SET_OBSERVE,
                const.SERVICE_RESET_FILTER, const.SERVICE_RECALIBRATE,
                const.SERVICE_EXPORT_OPTIONS, const.SERVICE_IMPORT_OPTIONS):
        assert hass.services.has_service(const.DOMAIN, svc), svc


async def test_reset_learning_targets_only_dc(hass: HomeAssistant) -> None:
    _seed(hass)
    dc_entry = await _add(hass, CLIMATE, "Salon")
    dv_entry = await _add(hass, VMC, "VMC")
    dc = hass.data[const.DOMAIN][dc_entry.entry_id]
    dv = hass.data[const.DOMAIN][dv_entry.entry_id]

    dc.learn_rate_ema = 1.5
    dc.lead_gain_adaptive = 0.8
    dc.adapt_ok_count = 4

    await hass.services.async_call(
        const.DOMAIN, const.SERVICE_RESET_LEARNING,
        {"entity_id": "climate.salon"}, blocking=True)
    await hass.async_block_till_done()

    assert dc.learn_rate_ema == 0.0
    assert dc.lead_gain_adaptive == 0.0
    assert dc.adapt_ok_count == 0
    # The VMC coordinator has no learning state and must be untouched.
    assert not hasattr(dv, "learn_rate_ema")


async def test_set_observe_toggles_target(hass: HomeAssistant) -> None:
    _seed(hass)
    entry = await _add(hass, CLIMATE, "Salon")
    co = hass.data[const.DOMAIN][entry.entry_id]
    assert co.observe_enabled is False

    await hass.services.async_call(
        const.DOMAIN, const.SERVICE_SET_OBSERVE,
        {"entity_id": "climate.salon", const.ATTR_ENABLED: True}, blocking=True)
    await hass.async_block_till_done()
    assert co.observe_enabled is True

    await hass.services.async_call(
        const.DOMAIN, const.SERVICE_SET_OBSERVE,
        {"entity_id": "climate.salon", const.ATTR_ENABLED: False}, blocking=True)
    await hass.async_block_till_done()
    assert co.observe_enabled is False


async def test_reset_filter_targets_vmc(hass: HomeAssistant) -> None:
    _seed(hass)
    entry = await _add(hass, VMC, "VMC")
    co = hass.data[const.DOMAIN][entry.entry_id]
    co.filter_hours = 42.0

    await hass.services.async_call(
        const.DOMAIN, const.SERVICE_RESET_FILTER,
        {"entity_id": "fan.vmc"}, blocking=True)
    await hass.async_block_till_done()
    assert co.filter_hours == 0.0


async def test_boost_forces_v3_then_reverts(hass: HomeAssistant) -> None:
    _seed(hass)
    entry = await _add(hass, VMC, "VMC")
    co = hass.data[const.DOMAIN][entry.entry_id]

    await hass.services.async_call(
        const.DOMAIN, const.SERVICE_BOOST,
        {"entity_id": "fan.vmc", const.ATTR_MINUTES: 30}, blocking=True)
    await hass.async_block_till_done()
    assert co.boost_until is not None
    assert co.data.speed == 3 and co.data.reason == "boost"

    # Re-triggering with a longer window restarts the countdown (REQ-BST-4).
    first_until = co.boost_until
    await hass.services.async_call(
        const.DOMAIN, const.SERVICE_BOOST,
        {"entity_id": "fan.vmc", const.ATTR_MINUTES: 60}, blocking=True)
    await hass.async_block_till_done()
    assert co.boost_until > first_until

    # Window elapsed -> next refresh auto-reverts (no longer boosting).
    co.boost_until = 1.0          # far in the past
    await co.async_refresh()
    await hass.async_block_till_done()
    assert co.boost_until is None
    assert co.data.reason != "boost"


async def test_recalibrate_refreshes(hass: HomeAssistant) -> None:
    _seed(hass)
    entry = await _add(hass, CLIMATE, "Salon")
    co = hass.data[const.DOMAIN][entry.entry_id]
    # Put the zone into a real mode so a refresh recomputes a decision.
    await hass.services.async_call(
        "climate", "set_hvac_mode",
        {"entity_id": "climate.salon", "hvac_mode": HVACMode.HEAT}, blocking=True)
    await hass.async_block_till_done()

    await hass.services.async_call(
        const.DOMAIN, const.SERVICE_RECALIBRATE,
        {"entity_id": "climate.salon"}, blocking=True)
    await hass.async_block_till_done()
    assert co.data is not None


async def test_services_removed_with_last_entry(hass: HomeAssistant) -> None:
    _seed(hass)
    a = await _add(hass, CLIMATE, "Salon")
    b = await _add(hass, VMC, "VMC")
    # Registered once (a single registry entry, regardless of #entries).
    assert hass.services.has_service(const.DOMAIN, const.SERVICE_RECALIBRATE)

    assert await hass.config_entries.async_unload(a.entry_id)
    await hass.async_block_till_done()
    # Still present while one entry remains.
    assert hass.services.has_service(const.DOMAIN, const.SERVICE_RECALIBRATE)

    assert await hass.config_entries.async_unload(b.entry_id)
    await hass.async_block_till_done()
    # Gone once the last entry unloads.
    assert not hass.services.has_service(const.DOMAIN, const.SERVICE_RECALIBRATE)


async def test_export_then_import_options_round_trip(hass: HomeAssistant) -> None:
    """Export a zone's tuned values and clone them onto another; junk is dropped."""
    _seed(hass)
    hass.states.async_set("sensor.cocina_temp", "21")
    a = await _add(hass, CLIMATE, "Salon")
    b = await _add(hass, {**CLIMATE, const.CONF_NAME: "Cocina",
                          const.CONF_DC_T_INT: "sensor.cocina_temp"}, "Cocina")

    # Tune zone A.
    hass.config_entries.async_update_entry(
        a, options={"base_heat_day": 23.0, "step": 0.2})
    await hass.async_block_till_done()

    # Export A -> response data carries its options.
    resp = await hass.services.async_call(
        const.DOMAIN, const.SERVICE_EXPORT_OPTIONS,
        {"entity_id": "climate.salon"}, blocking=True, return_response=True)
    opts = resp["options"][a.entry_id]
    assert opts["base_heat_day"] == 23.0 and opts["step"] == 0.2

    # Import into B, with junk that must be dropped (unknown key + a data-only key).
    await hass.services.async_call(
        const.DOMAIN, const.SERVICE_IMPORT_OPTIONS,
        {"entity_id": "climate.cocina",
         "values": {**opts, "not_a_real_key": 1, const.CONF_DC_T_INT: "sensor.evil"}},
        blocking=True)
    await hass.async_block_till_done()

    assert b.options["base_heat_day"] == 23.0      # cloned
    assert b.options["step"] == 0.2
    assert "not_a_real_key" not in b.options       # unknown key rejected
    assert const.CONF_DC_T_INT not in b.options    # data key is not an option key
