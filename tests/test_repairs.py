"""Integration tests for F07 — Repairs issue on a sustained DC degraded state."""

from homeassistant.components.climate import HVACMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_capture_events,
)

from custom_components.dynamic_home import const

# Note: no indoor-temp sensor is seeded, so the zone is degraded once it cools/heats.
CLIMATE = {
    const.CONF_NAME: "Salon",
    const.CONF_MODULE: const.MODULE_CLIMATE,
    const.CONF_DC_T_INT: "sensor.salon_temp",
    const.CONF_DC_TARGET: "ds",
}


async def _add(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(domain=const.DOMAIN, data=CLIMATE, options={},
                            title="Salon")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _heat(hass: HomeAssistant) -> None:
    await hass.services.async_call(
        "climate", "set_hvac_mode",
        {"entity_id": "climate.salon", "hvac_mode": HVACMode.HEAT}, blocking=True)
    await hass.async_block_till_done()


async def test_degraded_event_and_delayed_issue(hass: HomeAssistant) -> None:
    entry = await _add(hass)
    co = hass.data[const.DOMAIN][entry.entry_id]
    reg = ir.async_get(hass)
    captured = async_capture_events(hass, const.EVENT_DEGRADED)

    await _heat(hass)
    await co.async_refresh()
    await hass.async_block_till_done()

    # Degraded immediately (no indoor temp) and the event fired once...
    assert co.degraded is True
    assert [e for e in captured if e.data["degraded"] is True]
    # ...but the repair issue waits for the stale window.
    assert reg.async_get_issue(const.DOMAIN, co._issue_id) is None

    # Backdate the degraded start past the stale threshold -> issue is raised.
    co._degraded_since -= const.ISSUE_STALE_S + 1
    await co.async_refresh()
    await hass.async_block_till_done()
    issue = reg.async_get_issue(const.DOMAIN, co._issue_id)
    assert issue is not None
    assert issue.translation_key == const.ISSUE_REQUIRED_SOURCE


async def test_issue_cleared_on_recovery(hass: HomeAssistant) -> None:
    entry = await _add(hass)
    co = hass.data[const.DOMAIN][entry.entry_id]
    reg = ir.async_get(hass)

    await _heat(hass)
    co._degraded_since = 0.0           # force "long degraded"
    await co.async_refresh()
    await hass.async_block_till_done()
    assert reg.async_get_issue(const.DOMAIN, co._issue_id) is not None

    # Indoor sensor appears -> healthy -> issue removed, event fires (cleared).
    captured = async_capture_events(hass, const.EVENT_DEGRADED)
    hass.states.async_set("sensor.salon_temp", "21")
    await co.async_refresh()
    await hass.async_block_till_done()
    assert co.degraded is False
    assert reg.async_get_issue(const.DOMAIN, co._issue_id) is None
    assert [e for e in captured if e.data["degraded"] is False]


async def test_issue_removed_on_unload(hass: HomeAssistant) -> None:
    entry = await _add(hass)
    co = hass.data[const.DOMAIN][entry.entry_id]
    reg = ir.async_get(hass)

    await _heat(hass)
    co._degraded_since = 0.0
    await co.async_refresh()
    await hass.async_block_till_done()
    assert reg.async_get_issue(const.DOMAIN, co._issue_id) is not None

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert reg.async_get_issue(const.DOMAIN, co._issue_id) is None
