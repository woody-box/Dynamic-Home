"""Integration tests for F08 — filter-life sensor and the filter-due event."""

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_capture_events,
    async_mock_service,
)

from custom_components.dynamic_home import const

HW = {
    const.CONF_NAME: "VMC",
    const.CONF_SW_PWR: "switch.vmc_pwr",
    const.CONF_SW_V2: "switch.vmc_v2",
    const.CONF_SW_V3: "switch.vmc_v3",
    const.CONF_CO2: "sensor.co2",
    const.CONF_PM25: "sensor.pm25",
}


def _seed(hass: HomeAssistant) -> None:
    async_mock_service(hass, "switch", "turn_on")
    async_mock_service(hass, "switch", "turn_off")
    hass.states.async_set("switch.vmc_pwr", "off")
    hass.states.async_set("switch.vmc_v2", "off")
    hass.states.async_set("switch.vmc_v3", "off")
    hass.states.async_set("sensor.co2", "500")
    hass.states.async_set("sensor.pm25", "5")


async def _setup(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(domain=const.DOMAIN, data=HW, options={}, title="VMC")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_filter_life_sensor_value(hass: HomeAssistant) -> None:
    _seed(hass)
    entry = await _setup(hass)
    co = hass.data[const.DOMAIN][entry.entry_id]

    co.filter_hours = 1825.0          # half of the 3650 h default
    await co.async_refresh()
    await hass.async_block_till_done()

    # A refresh accrues a sliver of running hours, so allow a small tolerance.
    assert co.filter_life_pct == pytest.approx(50.0, abs=0.1)
    # Resolve the entity_id from the registry (robust to slug/timing) rather than
    # hard-coding "sensor.vmc_filter_life".
    eid = er.async_get(hass).async_get_entity_id(
        "sensor", const.DOMAIN, f"{entry.entry_id}_filter_life")
    assert eid is not None
    state = hass.states.get(eid)
    assert state is not None
    assert float(state.state) == pytest.approx(50.0, abs=0.1)


async def test_filter_due_fires_once(hass: HomeAssistant) -> None:
    _seed(hass)
    entry = await _setup(hass)
    co = hass.data[const.DOMAIN][entry.entry_id]
    captured = async_capture_events(hass, const.EVENT_FILTER_DUE)

    # Drop below the 10 % due threshold (3400/3650 -> ~6.8 %).
    co.filter_hours = 3400.0
    await co.async_refresh()
    await hass.async_block_till_done()
    assert len(captured) == 1
    assert captured[0].data["module"] == const.MODULE_VMC
    assert captured[0].data["pct"] <= const.FILTER_DUE_PCT

    # A second cycle still below threshold must NOT fire again (disarmed).
    co.filter_hours = 3450.0
    await co.async_refresh()
    await hass.async_block_till_done()
    assert len(captured) == 1


async def test_reset_rearms_and_restores(hass: HomeAssistant) -> None:
    _seed(hass)
    entry = await _setup(hass)
    co = hass.data[const.DOMAIN][entry.entry_id]
    captured = async_capture_events(hass, const.EVENT_FILTER_DUE)

    co.filter_hours = 3600.0
    await co.async_refresh()
    await hass.async_block_till_done()
    assert len(captured) == 1
    assert co._filter_due_armed is False

    # Reset re-arms and restores the sensor to 100 %.
    co.reset_filter_hours()
    assert co._filter_due_armed is True
    await co.async_refresh()
    await hass.async_block_till_done()
    assert co.filter_life_pct == pytest.approx(100.0, abs=0.1)

    # Crossing the threshold again fires a fresh event.
    co.filter_hours = 3600.0
    await co.async_refresh()
    await hass.async_block_till_done()
    assert len(captured) == 2


async def test_filter_due_raises_and_clears_repair_issue(
        hass: HomeAssistant) -> None:
    _seed(hass)
    entry = await _setup(hass)
    co = hass.data[const.DOMAIN][entry.entry_id]
    reg = ir.async_get(hass)
    assert reg.async_get_issue(const.DOMAIN, co._filter_issue_id) is None

    # Crossing the due threshold raises the Repairs issue (F08).
    co.filter_hours = 3600.0
    await co.async_refresh()
    await hass.async_block_till_done()
    issue = reg.async_get_issue(const.DOMAIN, co._filter_issue_id)
    assert issue is not None
    assert issue.translation_key == const.ISSUE_FILTER_DUE

    # Resetting the filter clears the issue immediately (no refresh needed).
    co.reset_filter_hours()
    assert reg.async_get_issue(const.DOMAIN, co._filter_issue_id) is None


async def test_filter_issue_removed_on_unload(hass: HomeAssistant) -> None:
    _seed(hass)
    entry = await _setup(hass)
    co = hass.data[const.DOMAIN][entry.entry_id]
    reg = ir.async_get(hass)

    co.filter_hours = 3600.0
    await co.async_refresh()
    await hass.async_block_till_done()
    assert reg.async_get_issue(const.DOMAIN, co._filter_issue_id) is not None

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert reg.async_get_issue(const.DOMAIN, co._filter_issue_id) is None
