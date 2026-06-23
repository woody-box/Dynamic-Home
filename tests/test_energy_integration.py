"""Integration tests for the Dynamic Energy module (F34)."""

from types import SimpleNamespace

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


async def test_house_energy_aggregates_modules(hass: HomeAssistant) -> None:
    hass.states.async_set("sensor.price", "0.25")
    entry = _energy_entry(hass, {const.CONF_ENERGY_PRICE: "sensor.price"})
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    co = hass.data[const.DOMAIN][entry.entry_id]

    # Two module coordinators (F06 keeps energy_kwh); a "_" hub is ignored.
    hass.data[const.DOMAIN]["dc1"] = SimpleNamespace(energy_kwh=3.0)
    hass.data[const.DOMAIN]["dv1"] = SimpleNamespace(energy_kwh=1.5)
    hass.data[const.DOMAIN]["_anticycle"] = SimpleNamespace(energy_kwh=99.0)
    await co.async_request_refresh()
    await hass.async_block_till_done()

    assert co.house_kwh == 4.5                             # 3.0 + 1.5 (hub skipped)
    ctx = hass.data[const.DOMAIN][const.DATA_ENERGY]
    assert ctx["house_kwh"] == 4.5

    reg = er.async_get(hass)
    assert reg.async_get_entity_id(
        "sensor", const.DOMAIN, f"{entry.entry_id}_house_kwh") is not None
    assert reg.async_get_entity_id(
        "sensor", const.DOMAIN, f"{entry.entry_id}_house_cost") is not None


async def test_house_cost_accumulates_with_price(hass: HomeAssistant) -> None:
    hass.states.async_set("sensor.price", "0.20")
    # Module present before setup -> its restored kWh seed the baseline, no jump.
    dc = SimpleNamespace(energy_kwh=10.0)
    hass.data.setdefault(const.DOMAIN, {})["dc1"] = dc
    entry = _energy_entry(hass, {const.CONF_ENERGY_PRICE: "sensor.price"})
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    co = hass.data[const.DOMAIN][entry.entry_id]
    assert co.house_cost == 0.0                            # no jump from restore

    dc.energy_kwh = 14.0                                   # +4 kWh consumed
    await co.async_request_refresh()
    await hass.async_block_till_done()
    assert co.house_cost == 0.8                            # 4 kWh * 0.20 €/kWh


async def test_house_power_aggregates_modules(hass: HomeAssistant) -> None:
    entry = _energy_entry(hass, {})
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    co = hass.data[const.DOMAIN][entry.entry_id]

    # Instantaneous W summed live across modules; a "_" hub is ignored.
    hass.data[const.DOMAIN]["dc1"] = SimpleNamespace(energy_kwh=0.0, power_w=1000.0)
    hass.data[const.DOMAIN]["dv1"] = SimpleNamespace(energy_kwh=0.0, power_w=30.0)
    hass.data[const.DOMAIN]["_anticycle"] = SimpleNamespace(power_w=999.0)
    await co.async_request_refresh()
    await hass.async_block_till_done()

    assert co.house_power_w == 1030.0                      # 1000 + 30 (hub skipped)
    assert hass.data[const.DOMAIN][const.DATA_ENERGY]["house_power_w"] == 1030.0
    assert er.async_get(hass).async_get_entity_id(
        "sensor", const.DOMAIN, f"{entry.entry_id}_house_power") is not None


async def test_no_cost_sensor_without_price(hass: HomeAssistant) -> None:
    entry = _energy_entry(hass, {})                        # no price sensor
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    reg = er.async_get(hass)
    assert reg.async_get_entity_id(
        "sensor", const.DOMAIN, f"{entry.entry_id}_house_kwh") is not None
    assert reg.async_get_entity_id(
        "sensor", const.DOMAIN, f"{entry.entry_id}_house_cost") is None
