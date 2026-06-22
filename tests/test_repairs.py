"""Integration tests for F07 — Repairs issue on a sustained degraded state.

The degraded → event → repair-issue mechanism is transversal (DV/DS/DC): a
required source that is configured but absent or stale (``unavailable``/
``unknown``) degrades the module, fires ``dynamic_home_degraded`` at once, and
raises a (non-fixable) issue once it stays degraded past ``ISSUE_STALE_S``.
"""

from homeassistant.components.climate import HVACMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
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


# --- DV (VMC): required hardware (relays + IAQ sensors) ---
_VMC = {
    const.CONF_NAME: "VMC", const.CONF_MODULE: const.MODULE_VMC,
    const.CONF_SW_PWR: "switch.p", const.CONF_SW_V2: "switch.v2",
    const.CONF_SW_V3: "switch.v3", const.CONF_CO2: "sensor.co2",
    const.CONF_PM25: "sensor.pm",
}


def _seed_vmc(hass: HomeAssistant) -> None:
    for e in ("switch.p", "switch.v2", "switch.v3"):
        hass.states.async_set(e, "off")
    hass.states.async_set("sensor.co2", "650")
    hass.states.async_set("sensor.pm", "5")


async def _add_vmc(hass: HomeAssistant) -> MockConfigEntry:
    _seed_vmc(hass)
    entry = MockConfigEntry(domain=const.DOMAIN, data=_VMC, options={},
                            title="VMC")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_dv_required_source_degrades_and_recovers(
        hass: HomeAssistant) -> None:
    entry = await _add_vmc(hass)
    co = hass.data[const.DOMAIN][entry.entry_id]
    reg = ir.async_get(hass)

    # All five required sources are alive -> healthy, no event, no issue.
    assert co.degraded is False
    # The transversal "Degradado" health sensor exists for a VMC (F07).
    assert er.async_get(hass).async_get_entity_id(
        "binary_sensor", const.DOMAIN, f"{entry.entry_id}_degraded") is not None

    captured = async_capture_events(hass, const.EVENT_DEGRADED)
    hass.states.async_set("sensor.co2", "unavailable")
    await co.async_refresh()
    await hass.async_block_till_done()

    # Degraded at once (event fired), but the issue waits for the stale window.
    assert co.degraded is True
    assert [e for e in captured if e.data["degraded"] is True
            and "CO₂" in e.data["missing"]]
    assert reg.async_get_issue(const.DOMAIN, co._issue_id) is None

    # Sustained past the threshold -> the (module-agnostic) issue is raised.
    co._degraded_since -= const.ISSUE_STALE_S + 1
    await co.async_refresh()
    await hass.async_block_till_done()
    issue = reg.async_get_issue(const.DOMAIN, co._issue_id)
    assert issue is not None
    assert issue.translation_key == const.ISSUE_REQUIRED_SOURCE

    # Sensor recovers -> healthy -> issue removed, cleared event fired.
    captured = async_capture_events(hass, const.EVENT_DEGRADED)
    hass.states.async_set("sensor.co2", "700")
    await co.async_refresh()
    await hass.async_block_till_done()
    assert co.degraded is False
    assert reg.async_get_issue(const.DOMAIN, co._issue_id) is None
    assert [e for e in captured if e.data["degraded"] is False]


async def test_dv_issue_removed_on_unload(hass: HomeAssistant) -> None:
    entry = await _add_vmc(hass)
    co = hass.data[const.DOMAIN][entry.entry_id]
    reg = ir.async_get(hass)

    hass.states.async_set("switch.v3", "unavailable")
    co._degraded_since = 0.0           # force "long degraded"
    await co.async_refresh()
    await hass.async_block_till_done()
    assert reg.async_get_issue(const.DOMAIN, co._issue_id) is not None

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert reg.async_get_issue(const.DOMAIN, co._issue_id) is None


# --- DS (shutter): the required cover ---
_DS = {
    const.CONF_NAME: "Persiana", const.CONF_MODULE: const.MODULE_SHUTTER,
    const.CONF_COVER: "cover.salon", const.CONF_FACADE_AZIMUTH: 180.0,
}


async def _add_ds(hass: HomeAssistant) -> MockConfigEntry:
    hass.states.async_set("cover.salon", "open", {"current_position": 100})
    hass.states.async_set("sun.sun", "below_horizon",
                          {"azimuth": 180, "elevation": -10})
    entry = MockConfigEntry(domain=const.DOMAIN, data=_DS, options={},
                            title="Persiana")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_ds_cover_degrades_and_recovers(hass: HomeAssistant) -> None:
    entry = await _add_ds(hass)
    co = hass.data[const.DOMAIN][entry.entry_id]
    reg = ir.async_get(hass)

    assert co.degraded is False

    hass.states.async_set("cover.salon", "unavailable")
    co._degraded_since = 0.0           # force "long degraded"
    await co.async_refresh()
    await hass.async_block_till_done()
    issue = reg.async_get_issue(const.DOMAIN, co._issue_id)
    assert issue is not None
    assert issue.translation_key == const.ISSUE_REQUIRED_SOURCE

    hass.states.async_set("cover.salon", "open", {"current_position": 100})
    await co.async_refresh()
    await hass.async_block_till_done()
    assert co.degraded is False
    assert reg.async_get_issue(const.DOMAIN, co._issue_id) is None
