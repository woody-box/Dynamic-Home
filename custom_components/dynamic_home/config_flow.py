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

from . import const, options_spec, presets


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
        vol.Optional(const.CONF_HRV_SUPPLY): _entity("sensor", "temperature"),
        vol.Optional(const.CONF_HRV_INTAKE): _entity("sensor", "temperature"),
        vol.Optional(const.CONF_HRV_EXTRACT): _entity("sensor", "temperature"),
        vol.Optional(const.CONF_VOC): _entity("sensor"),
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
        vol.Optional(const.CONF_DC_VALVE): _entity(["binary_sensor", "switch", "sensor"]),
        vol.Optional(const.CONF_DC_DEMAND_HEAT): _entity(["binary_sensor", "input_boolean"]),
        vol.Optional(const.CONF_DC_DEMAND_COOL): _entity(["binary_sensor", "input_boolean"]),
        vol.Optional(const.CONF_DC_DEHUMIDIFIER):
            _entity(["switch", "humidifier", "input_boolean"]),
        vol.Optional(const.CONF_DC_ADJ_TEMP): _entity(["sensor"]),
        vol.Optional(const.CONF_DC_ADJ_DOOR): _entity(["binary_sensor"]),
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
    """Tunable parameters, grouped by category and editable after setup.

    The init step is a menu of the categories the module defines; picking one
    opens a form built from :mod:`options_spec`. Saving merges that category's
    values into the existing options (other categories are left untouched).
    """

    def __init__(self, entry: ConfigEntry) -> None:
        self.entry = entry
        self._module = entry.data.get(const.CONF_MODULE)

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        cats = options_spec.categories(self._module, self.show_advanced_options)
        if not cats:
            return self.async_abort(reason="no_options")
        menu = [f"cat_{c}" for c in cats]
        if presets.preset_ids(self._module):
            menu.append("preset")
        return self.async_show_menu(step_id="init", menu_options=menu)

    async def async_step_preset(self, user_input: dict[str, Any] | None = None):
        """Apply a ready-made preset (merges its values into the options)."""
        ids = presets.preset_ids(self._module)
        if user_input is not None:
            values = presets.preset_values(self._module, user_input["preset"])
            return self.async_create_entry(
                title="", data={**self.entry.options, **values})
        lang = getattr(self.hass.config, "language", "en") if self.hass else "en"
        options = [
            selector.SelectOptionDict(
                value=pid, label=presets.preset_label(self._module, pid, lang))
            for pid in ids
        ]
        schema = vol.Schema({
            vol.Required("preset", default=ids[0]): selector.SelectSelector(
                selector.SelectSelectorConfig(options=options)),
        })
        return self.async_show_form(step_id="preset", data_schema=schema)

    def __getattr__(self, name: str):
        """Dispatch async_step_cat_<category> to a generic category handler."""
        if name.startswith("async_step_cat_"):
            cat = name[len("async_step_cat_"):]
            adv = getattr(self, "show_advanced_options", False)
            if cat in options_spec.categories(self.__dict__.get("_module"), adv):
                async def handler(user_input=None, _cat=cat):
                    return await self._async_category(_cat, user_input)
                return handler
        raise AttributeError(name)

    async def _async_category(self, cat: str,
                              user_input: dict[str, Any] | None = None):
        if user_input is not None:
            merged = {**self.entry.options, **user_input}
            return self.async_create_entry(title="", data=merged)
        return self.async_show_form(
            step_id=f"cat_{cat}", data_schema=self._schema(cat))

    def _schema(self, cat: str) -> vol.Schema:
        cfg = options_spec.fresh_config(self._module)
        o = self.entry.options
        out: dict = {}
        for opt in options_spec.fields(self._module, cat, self.show_advanced_options):
            key = options_spec.option_key(opt)
            default = o.get(key, options_spec.current_value(cfg, opt))
            if isinstance(default, bool):
                selector_t: Any = bool
            elif isinstance(default, int):
                selector_t = vol.Coerce(int)
            else:
                selector_t = vol.Coerce(float)
            out[vol.Optional(key, default=default)] = selector_t
        return vol.Schema(out)
