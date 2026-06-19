"""Config + options flow for Dynamic Home (DV).

Replaces the YAML ``REPLACE_*`` hw_map placeholders with a UI wizard: the user
picks their actual entities and the integration creates the device + entities.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import selector

from . import const


def _entity(domain: str | list[str] | None = None,
            device_class: str | None = None) -> selector.EntitySelector:
    cfg: dict[str, Any] = {}
    if domain:
        cfg["domain"] = domain
    if device_class:
        cfg["device_class"] = device_class
    return selector.EntitySelector(selector.EntitySelectorConfig(**cfg))


STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(const.CONF_NAME, default="VMC"): str,
        vol.Required(const.CONF_SW_PWR): _entity("switch"),
        vol.Required(const.CONF_SW_V2): _entity("switch"),
        vol.Required(const.CONF_SW_V3): _entity("switch"),
        vol.Required(const.CONF_CO2): _entity("sensor", "carbon_dioxide"),
        vol.Required(const.CONF_PM25): _entity("sensor", "pm25"),
        vol.Optional(const.CONF_T_IN): _entity("sensor", "temperature"),
        vol.Optional(const.CONF_T_EXT): _entity("sensor", "temperature"),
        vol.Optional(const.CONF_AQI): _entity("sensor"),
        vol.Optional(const.CONF_HUM_BATH): _entity("sensor", "humidity"),
        vol.Optional(const.CONF_HUM_EXT): _entity("sensor", "humidity"),
        vol.Optional(const.CONF_HUM_IN): _entity("sensor", "humidity"),
    }
)

STEP_SHUTTER_SCHEMA = vol.Schema(
    {
        vol.Required(const.CONF_NAME, default="Persiana"): str,
        vol.Required(const.CONF_COVER): _entity("cover"),
        vol.Required(const.CONF_FACADE_AZIMUTH, default=180): vol.All(
            vol.Coerce(float), vol.Range(min=0, max=359)),
        vol.Required(const.CONF_FACADE_SPAN, default=180): vol.All(
            vol.Coerce(float), vol.Range(min=10, max=360)),
        vol.Optional(const.CONF_CLIMATE): _entity("climate"),
        vol.Optional(const.CONF_DS_T_IN): _entity("sensor", "temperature"),
        vol.Optional(const.CONF_DS_T_OUT): _entity("sensor", "temperature"),
        vol.Optional(const.CONF_WIND): _entity("sensor"),
        vol.Optional(const.CONF_RAIN): _entity(["binary_sensor", "sensor"]),
    }
)

STEP_CLIMATE_SCHEMA = vol.Schema(
    {
        vol.Required(const.CONF_NAME, default="Zona"): str,
        vol.Required(const.CONF_DC_T_INT): _entity("sensor", "temperature"),
        vol.Optional(const.CONF_DC_T_EXT): _entity("sensor", "temperature"),
        vol.Optional(const.CONF_DC_CLIMATE): _entity("climate"),
        vol.Optional(const.CONF_DC_VMC): _entity(["fan", "sensor"]),
        vol.Optional(const.CONF_DC_HUMIDITY): _entity("sensor", "humidity"),
        vol.Optional(const.CONF_DC_WEATHER): _entity("weather"),
        vol.Optional(const.CONF_DC_WIND): _entity("sensor"),
        vol.Optional(const.CONF_DC_WINDOW): _entity(["binary_sensor", "input_boolean"]),
        vol.Optional(const.CONF_DC_TARGET, default="ds"): str,
    }
)


class DynamicHomeConfigFlow(ConfigFlow, domain=const.DOMAIN):
    """Handle the initial setup wizard."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Entry point: choose which module to add."""
        return self.async_show_menu(
            step_id="user", menu_options=["vmc", "shutter", "climate"])

    async def async_step_vmc(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            await self.async_set_unique_id(f"vmc_{user_input[const.CONF_SW_PWR]}")
            self._abort_if_unique_id_configured()
            data = {**user_input, const.CONF_MODULE: const.MODULE_VMC}
            return self.async_create_entry(
                title=user_input[const.CONF_NAME], data=data)
        return self.async_show_form(step_id="vmc", data_schema=STEP_USER_SCHEMA)

    async def async_step_shutter(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            await self.async_set_unique_id(f"ds_{user_input[const.CONF_COVER]}")
            self._abort_if_unique_id_configured()
            data = {**user_input, const.CONF_MODULE: const.MODULE_SHUTTER}
            return self.async_create_entry(
                title=user_input[const.CONF_NAME], data=data)
        return self.async_show_form(
            step_id="shutter", data_schema=STEP_SHUTTER_SCHEMA)

    async def async_step_climate(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            await self.async_set_unique_id(
                f"dc_{user_input[const.CONF_DC_T_INT]}")
            self._abort_if_unique_id_configured()
            data = {**user_input, const.CONF_MODULE: const.MODULE_CLIMATE}
            return self.async_create_entry(
                title=user_input[const.CONF_NAME], data=data)
        return self.async_show_form(
            step_id="climate", data_schema=STEP_CLIMATE_SCHEMA)

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> OptionsFlow:
        return DynamicHomeOptionsFlow(entry)


class DynamicHomeOptionsFlow(OptionsFlow):
    """Tunable thresholds, editable after setup."""

    def __init__(self, entry: ConfigEntry) -> None:
        self.entry = entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        # Only the VMC module exposes tunable options (IAQ thresholds).
        if self.entry.data.get(const.CONF_MODULE) != const.MODULE_VMC:
            return self.async_abort(reason="no_options")

        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        o = self.entry.options
        schema = vol.Schema(
            {
                vol.Optional(const.OPT_CO2_V2,
                             default=o.get(const.OPT_CO2_V2, 900)): vol.Coerce(float),
                vol.Optional(const.OPT_CO2_V3,
                             default=o.get(const.OPT_CO2_V3, 1300)): vol.Coerce(float),
                vol.Optional(const.OPT_PM_V2,
                             default=o.get(const.OPT_PM_V2, 15)): vol.Coerce(float),
                vol.Optional(const.OPT_PM_V3,
                             default=o.get(const.OPT_PM_V3, 40)): vol.Coerce(float),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
