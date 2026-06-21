"""Unit tests for the native-event helpers (events.py)."""

from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_capture_events,
)

from custom_components.dynamic_home import const, events


def _entry() -> MockConfigEntry:
    return MockConfigEntry(domain=const.DOMAIN, title="Salon", data={})


async def test_fire_degraded(hass) -> None:
    entry = _entry()
    captured = async_capture_events(hass, const.EVENT_DEGRADED)
    events.fire_degraded(hass, entry, const.MODULE_CLIMATE, True, ["dc_t_int"])
    await hass.async_block_till_done()

    assert len(captured) == 1
    data = captured[0].data
    assert data["entry_id"] == entry.entry_id
    assert data["name"] == "Salon"
    assert data["module"] == const.MODULE_CLIMATE
    assert data["degraded"] is True
    assert data["missing"] == ["dc_t_int"]


async def test_fire_conflict_merges_explain(hass) -> None:
    entry = _entry()
    captured = async_capture_events(hass, const.EVENT_CONFLICT)
    explain = {"winner": "request_solar_shield", "source": "dc_x",
               "priority": 70, "candidates": 2, "reason": "priority"}
    events.fire_conflict(hass, entry, const.MODULE_SHUTTER, explain)
    await hass.async_block_till_done()

    assert len(captured) == 1
    data = captured[0].data
    assert data["module"] == const.MODULE_SHUTTER
    assert data["winner"] == "request_solar_shield"
    assert data["priority"] == 70
    assert data["candidates"] == 2


async def test_fire_filter_due(hass) -> None:
    entry = _entry()
    captured = async_capture_events(hass, const.EVENT_FILTER_DUE)
    events.fire_filter_due(hass, entry, const.MODULE_VMC, 9.37, 3310.2, 3650.0)
    await hass.async_block_till_done()

    assert len(captured) == 1
    data = captured[0].data
    assert data["module"] == const.MODULE_VMC
    assert data["pct"] == 9.4          # rounded to 1 decimal
    assert data["hours"] == 3310.2
    assert data["life"] == 3650.0
