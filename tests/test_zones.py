"""Tests for the zone/group hierarchy (F24): pure helpers + HA integration."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..",
                                "custom_components", "dynamic_home"))

import zones  # noqa: E402
from homeassistant.core import HomeAssistant  # noqa: E402
from pytest_homeassistant_custom_component.common import (  # noqa: E402
    MockConfigEntry,
)

from custom_components.dynamic_home import const  # noqa: E402


# --- pure helpers ---
def test_assign_modules_evicts_from_other_zones():
    t = zones.add_zone(zones.add_zone({}, "Salon"), "Cocina")
    t = zones.assign_modules(t, "salon", ["m1", "m2"])
    t = zones.assign_modules(t, "cocina", ["m2"])     # m2 moves to cocina
    assert t["zones"]["salon"]["modules"] == ["m1"]
    assert t["zones"]["cocina"]["modules"] == ["m2"]


def test_assign_zones_one_group_max():
    t = zones.add_group(zones.add_group(zones.add_zone({}, "Salon"), "P0"), "P1")
    t = zones.assign_zones(t, "p0", ["salon"])
    t = zones.assign_zones(t, "p1", ["salon"])        # salon moves to p1
    assert t["groups"]["p0"]["zones"] == []
    assert t["groups"]["p1"]["zones"] == ["salon"]


def test_scope_for_module_and_counts():
    t = zones.add_group(zones.add_zone({}, "Salon"), "Planta0")
    t = zones.assign_modules(t, "salon", ["dc1"])
    t = zones.assign_zones(t, "planta0", ["salon"])
    assert zones.scope_for_module(t, "dc1") == {"zone": "salon", "group": "planta0"}
    assert zones.scope_for_module(t, "ghost") == {"zone": None, "group": None}
    assert zones.counts(t) == (1, 1, 1)


def test_remove_zone_drops_from_group():
    t = zones.add_group(zones.add_zone({}, "Salon"), "P0")
    t = zones.assign_zones(t, "p0", ["salon"])
    t = zones.remove_zone(t, "salon")
    assert "salon" not in t["zones"]
    assert t["groups"]["p0"]["zones"] == []


# --- integration ---
async def test_zones_entry_singleton_and_persists(hass: HomeAssistant) -> None:
    from homeassistant.helpers import entity_registry as er
    entry = MockConfigEntry(
        domain=const.DOMAIN, title="Zonas", unique_id="zones_singleton",
        data={const.CONF_NAME: "Zonas", const.CONF_MODULE: const.MODULE_ZONES},
        options={const.CONF_ZONES_TREE: zones.add_zone({}, "Salon")})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # Diagnostic sensor exists and the tree is published for consumers.
    assert er.async_get(hass).async_get_entity_id(
        "sensor", const.DOMAIN, f"{entry.entry_id}_zones") is not None
    assert "salon" in hass.data[const.DOMAIN][const.DATA_ZONES]["zones"]

    # Adding a second zones entry aborts (singleton).
    result = await hass.config_entries.flow.async_init(
        const.DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "zones"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={const.CONF_NAME: "Otra"})
    assert result["type"] == "abort"


async def test_zones_options_tree_edit_persists(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=const.DOMAIN, title="Zonas",
        data={const.CONF_NAME: "Zonas", const.CONF_MODULE: const.MODULE_ZONES},
        options={const.CONF_ZONES_TREE: {"zones": {}, "groups": {}}})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    flow = await hass.config_entries.options.async_init(entry.entry_id)
    flow = await hass.config_entries.options.async_configure(
        flow["flow_id"], {"next_step_id": "zone_add"})
    flow = await hass.config_entries.options.async_configure(
        flow["flow_id"], {const.CONF_NAME: "Dormitorio"})
    await hass.async_block_till_done()

    # Persisted in options (survives restarts) and re-published after reload.
    assert "dormitorio" in entry.options[const.CONF_ZONES_TREE]["zones"]
    assert "dormitorio" in hass.data[const.DOMAIN][const.DATA_ZONES]["zones"]
