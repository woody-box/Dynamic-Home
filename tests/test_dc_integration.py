"""Home Assistant integration tests for the DC (climate) module.

Covers the config flow (menu -> climate), entity creation, and the full
multi-module triangle: DC in cool mode publishes ``request_solar_shield`` to the
shared SDHB hub, and a DS shutter sharing that hub clamps its cover.
"""

from homeassistant.components.climate import HVACMode
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_TEMPERATURE
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dynamic_home import const

CLIMATE = {
    const.CONF_NAME: "Salon",
    const.CONF_MODULE: const.MODULE_CLIMATE,
    const.CONF_DC_T_INT: "sensor.salon_temp",
    const.CONF_DC_T_EXT: "sensor.ext_temp",
    const.CONF_DC_TARGET: "ds",
}

SHUTTER = {
    const.CONF_NAME: "Persiana",
    const.CONF_MODULE: const.MODULE_SHUTTER,
    const.CONF_COVER: "cover.salon_real",
    const.CONF_FACADE_AZIMUTH: 180.0,
}


def _seed(hass: HomeAssistant) -> None:
    hass.states.async_set("sensor.salon_temp", "27")
    hass.states.async_set("sensor.ext_temp", "33")
    hass.states.async_set("sun.sun", "above_horizon",
                          {"azimuth": 180, "elevation": 30})
    hass.states.async_set("cover.salon_real", "open", {"supported_features": 15})


async def _add(hass: HomeAssistant, data: dict, title: str) -> MockConfigEntry:
    entry = MockConfigEntry(domain=const.DOMAIN, data=data, title=title)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_climate_config_flow(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        const.DOMAIN, context={"source": "user"})
    assert result["type"] == FlowResultType.MENU

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "climate"})
    assert result["step_id"] == "climate"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={const.CONF_NAME: "Salon",
                    const.CONF_DC_T_INT: "sensor.salon_temp",
                    const.CONF_DC_TARGET: "ds"})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][const.CONF_MODULE] == const.MODULE_CLIMATE


async def test_setup_creates_climate(hass: HomeAssistant) -> None:
    _seed(hass)
    entry = await _add(hass, CLIMATE, "Salon")
    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get("climate.salon") is not None


async def test_full_triangle_dc_drives_ds(hass: HomeAssistant) -> None:
    """DC (cool) -> bus request_solar_shield -> DS cover clamps to 30%."""
    _seed(hass)
    dc_entry = await _add(hass, CLIMATE, "Salon")
    ds_entry = await _add(hass, SHUTTER, "Persiana")

    dc = hass.data[const.DOMAIN][dc_entry.entry_id]
    ds = hass.data[const.DOMAIN][ds_entry.entry_id]

    # Put the climate zone into cooling.
    await hass.services.async_call(
        "climate", "set_hvac_mode",
        {"entity_id": "climate.salon", "hvac_mode": HVACMode.COOL},
        blocking=True)
    await hass.async_block_till_done()

    # DC published a solar-shield intent to the bus...
    assert dc.data.published_intent == "request_solar_shield"

    # ...which DS consumes on its next evaluation, clamping the cover.
    await ds.async_refresh()
    await hass.async_block_till_done()
    assert ds.data.reason == "sdhb_solar_shield"
    assert ds.data.pos == 30
    assert hass.states.get("cover.persiana").attributes["current_position"] == 30


async def test_climate_manual_setpoint_is_override(hass: HomeAssistant) -> None:
    _seed(hass)
    await _add(hass, CLIMATE, "Salon")
    await hass.services.async_call(
        "climate", "set_temperature",
        {"entity_id": "climate.salon", ATTR_TEMPERATURE: 21.0}, blocking=True)
    await hass.async_block_till_done()
    state = hass.states.get("climate.salon")
    assert state.attributes["temperature"] == 21.0
    assert state.attributes["reason"] == "override"


async def test_window_lockout_and_vacation(hass: HomeAssistant) -> None:
    """An open window forces OFF; vacation switch feeds the engine."""
    _seed(hass)
    hass.states.async_set("binary_sensor.ventana", "off")
    entry = await _add(hass, {
        const.CONF_NAME: "Salon", const.CONF_MODULE: const.MODULE_CLIMATE,
        const.CONF_DC_T_INT: "sensor.salon_temp",
        const.CONF_DC_WINDOW: "binary_sensor.ventana",
        const.CONF_DC_TARGET: "ds",
    }, "Salon")
    co = hass.data[const.DOMAIN][entry.entry_id]

    await hass.services.async_call(
        "climate", "set_hvac_mode",
        {"entity_id": "climate.salon", "hvac_mode": HVACMode.HEAT}, blocking=True)
    await co.async_refresh()
    await hass.async_block_till_done()
    assert co.data.action == "heat"

    # Open the window -> lockout -> OFF.
    hass.states.async_set("binary_sensor.ventana", "on")
    await co.async_refresh()
    await hass.async_block_till_done()
    assert co.data.action == "off" and co.data.reason == "off_window"

    # Vacation switch is registered and feeds the engine.
    from homeassistant.helpers import entity_registry as er
    assert er.async_get(hass).async_get_entity_id(
        "switch", const.DOMAIN, f"{entry.entry_id}_vacation") is not None
    co.vacation_enabled = True
    hass.states.async_set("binary_sensor.ventana", "off")
    await co.async_refresh()
    await hass.async_block_till_done()
    assert co.data.action == "heat"  # vacation uses the vacation base setpoint


async def test_observability_sensors(hass: HomeAssistant) -> None:
    """DC exposes pipeline values as diagnostic sensors for dashboards."""
    from homeassistant.helpers import entity_registry as er
    _seed(hass)
    entry = await _add(hass, {
        const.CONF_NAME: "Salon", const.CONF_MODULE: const.MODULE_CLIMATE,
        const.CONF_DC_T_INT: "sensor.salon_temp",
        const.CONF_DC_T_EXT: "sensor.ext_temp", const.CONF_DC_TARGET: "ds",
    }, "Salon")
    co = hass.data[const.DOMAIN][entry.entry_id]

    reg = er.async_get(hass)
    for key in ("target", "base", "target_raw", "dew_point", "reason",
                "bias_exterior", "bias_vmc", "bias_trend", "bias_brake",
                "bias_forecast", "bias_facade", "sdhb_bias", "mods_total"):
        assert reg.async_get_entity_id(
            "sensor", const.DOMAIN, f"{entry.entry_id}_{key}") is not None, key
    assert reg.async_get_entity_id(
        "binary_sensor", const.DOMAIN, f"{entry.entry_id}_dew_risk") is not None

    # In heat the pipeline breakdown is populated.
    await hass.services.async_call(
        "climate", "set_hvac_mode",
        {"entity_id": "climate.salon", "hvac_mode": HVACMode.HEAT}, blocking=True)
    await co.async_refresh()
    assert "bias_exterior" in co.data.details
    assert co.data.details["base"] is not None
