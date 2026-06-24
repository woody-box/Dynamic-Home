"""Config-entry diagnostics (F): redacted JSON snapshot per module."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dynamic_home import const
from custom_components.dynamic_home.diagnostics import (
    async_get_config_entry_diagnostics,
)

CLIMATE = {
    const.CONF_NAME: "Salon",
    const.CONF_MODULE: const.MODULE_CLIMATE,
    const.CONF_DC_T_INT: "sensor.salon_temp",
    const.CONF_DC_TARGET: "ds",
}
# An individual heat pump -> the F26 profile says compressor/peak True.
OPTIONS = {
    "base_heat_day": 22.0,
    const.CONF_GENERATOR: "heatpump_air_water",
    const.CONF_DISTRIBUTION: "individual",
    const.CONF_EMISSION: "underfloor",
}


async def test_config_entry_diagnostics_dc(hass: HomeAssistant) -> None:
    hass.states.async_set("sensor.salon_temp", "21")
    entry = MockConfigEntry(domain=const.DOMAIN, data=CLIMATE, options=OPTIONS,
                            title="Salon")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    co = hass.data[const.DOMAIN][entry.entry_id]
    await co.async_refresh()
    await hass.async_block_till_done()

    diag = await async_get_config_entry_diagnostics(hass, entry)

    # The entry block carries the module + the tuned option values (the "save").
    assert diag["entry"]["module"] == const.MODULE_CLIMATE
    assert diag["entry"]["options"]["base_heat_day"] == 22.0

    # The coordinator snapshot is JSON-safe and carries live computed state.
    snap = diag["coordinator"]
    assert snap["_module"] == const.MODULE_CLIMATE
    assert "decision" in snap                       # DataUpdateCoordinator.data
    assert snap["install_profile"]["compressor"] is True   # individual heat pump

    # Whole payload must be JSON-serialisable.
    import json
    json.dumps(diag)


async def test_config_entry_diagnostics_before_setup(hass: HomeAssistant) -> None:
    """No coordinator yet (entry not set up) -> snapshot is None, no crash."""
    entry = MockConfigEntry(domain=const.DOMAIN, data=CLIMATE, options={},
                            title="Salon")
    entry.add_to_hass(hass)
    diag = await async_get_config_entry_diagnostics(hass, entry)
    assert diag["coordinator"] is None
    assert diag["entry"]["module"] == const.MODULE_CLIMATE
