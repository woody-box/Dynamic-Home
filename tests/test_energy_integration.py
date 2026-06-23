"""Integration tests for the Dynamic Energy module (F34)."""

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dynamic_home import const


def _energy_entry(hass: HomeAssistant, data: dict) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=const.DOMAIN, title="Energía", unique_id="energy_singleton",
        data={const.CONF_NAME: "Energía", const.CONF_MODULE: const.MODULE_ENERGY,
              const.CONF_ENERGY_CONTRACTED: 5750.0, **data})
    entry.add_to_hass(hass)
    return entry


async def test_energy_publishes_context_grid_and_price(
        hass: HomeAssistant) -> None:
    hass.states.async_set("sensor.grid", "2000")
    hass.states.async_set("sensor.price", "0.30")          # peak
    entry = _energy_entry(hass, {const.CONF_ENERGY_GRID: "sensor.grid",
                                 const.CONF_ENERGY_PRICE: "sensor.price"})
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    ctx = hass.data[const.DOMAIN][const.DATA_ENERGY]
    assert ctx["import_headroom_w"] == 3750.0
    assert ctx["tariff_state"] == "peak"
    assert ctx["scarcity"] is True
    assert "surplus_w" not in ctx                          # no PV -> absent

    reg = er.async_get(hass)
    for uid in ("headroom", "tariff", "scarcity"):
        kind = "binary_sensor" if uid == "scarcity" else "sensor"
        assert reg.async_get_entity_id(
            kind, const.DOMAIN, f"{entry.entry_id}_{uid}") is not None
    # The PV surplus sensor is gated off (no PV entity).
    assert reg.async_get_entity_id(
        "sensor", const.DOMAIN, f"{entry.entry_id}_surplus") is None


async def test_energy_fixed_tariff_without_price(hass: HomeAssistant) -> None:
    hass.states.async_set("sensor.grid", "1000")
    entry = _energy_entry(hass, {const.CONF_ENERGY_GRID: "sensor.grid"})
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    ctx = hass.data[const.DOMAIN][const.DATA_ENERGY]
    assert ctx["tariff_state"] == "normal"                 # deterministic default
    assert ctx["import_headroom_w"] == 4750.0


async def test_energy_no_grid_meter_headroom_none(hass: HomeAssistant) -> None:
    entry = _energy_entry(hass, {})                        # no grid, no price
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    ctx = hass.data[const.DOMAIN][const.DATA_ENERGY]
    assert ctx["import_headroom_w"] is None                # degrades, no crash
