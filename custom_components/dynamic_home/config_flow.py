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

from . import const, options_spec, presets, zones


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
        vol.Optional(const.CONF_HOOD_V1): _entity("switch"),
        vol.Optional(const.CONF_HOOD_V2): _entity("switch"),
        vol.Optional(const.CONF_HOOD_V3): _entity("switch"),
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
        vol.Optional(const.CONF_DS_ALERT): _entity(["binary_sensor"]),
        vol.Optional(const.CONF_DS_ALERT_HAIL): _entity(["binary_sensor"]),
        vol.Optional(const.CONF_DS_ALERT_WIND): _entity(["binary_sensor"]),
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

STEP_WEATHER_SCHEMA = vol.Schema(
    {
        vol.Required(const.CONF_NAME, default="Meteo"): str,
        vol.Optional(const.CONF_WX_SOURCE_1): _entity("weather"),
        vol.Optional(const.CONF_WX_SOURCE_2): _entity("weather"),
        vol.Optional(const.CONF_WX_SOURCE_3): _entity("weather"),
        vol.Optional(const.CONF_WX_TEMP): _entity("sensor", "temperature"),
        vol.Optional(const.CONF_WX_WIND): _entity("sensor"),
        vol.Optional(const.CONF_WX_PRECIP): _entity("sensor"),
    }
)

STEP_ZONES_SCHEMA = vol.Schema({vol.Required(const.CONF_NAME, default="Zonas"): str})

# Module entries that can be assigned to a zone (everything but the Zones entry).
_ASSIGNABLE = (const.MODULE_VMC, const.MODULE_SHUTTER, const.MODULE_CLIMATE,
               const.MODULE_WEATHER)


class DynamicHomeConfigFlow(ConfigFlow, domain=const.DOMAIN):
    """Handle the initial setup wizard."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Entry point: choose which module to add."""
        return self.async_show_menu(
            step_id="user",
            menu_options=["vmc", "shutter", "climate", "weather", "zones"])

    async def async_step_zones(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            await self.async_set_unique_id("zones_singleton")
            self._abort_if_unique_id_configured()       # one zones entry only
            data = {**user_input, const.CONF_MODULE: const.MODULE_ZONES}
            return self.async_create_entry(
                title=user_input[const.CONF_NAME], data=data)
        return self.async_show_form(step_id="zones", data_schema=STEP_ZONES_SCHEMA)

    async def async_step_vmc(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            await self.async_set_unique_id(f"vmc_{user_input[const.CONF_SW_PWR]}")
            self._abort_if_unique_id_configured()
            data = {**user_input, const.CONF_MODULE: const.MODULE_VMC}
            return self.async_create_entry(
                title=user_input[const.CONF_NAME], data=data)
        return self.async_show_form(step_id="vmc", data_schema=STEP_USER_SCHEMA)

    async def async_step_weather(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            await self.async_set_unique_id(f"wx_{user_input[const.CONF_NAME]}")
            self._abort_if_unique_id_configured()
            data = {**user_input, const.CONF_MODULE: const.MODULE_WEATHER}
            return self.async_create_entry(
                title=user_input[const.CONF_NAME], data=data)
        return self.async_show_form(
            step_id="weather", data_schema=STEP_WEATHER_SCHEMA)

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
        if entry.data.get(const.CONF_MODULE) == const.MODULE_ZONES:
            return ZonesOptionsFlow(entry)
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
        menu.append("mirrors")
        return self.async_show_menu(step_id="init", menu_options=menu)

    async def async_step_mirrors(self, user_input: dict[str, Any] | None = None):
        """Toggle stable per-role hardware mirror sensors (F36)."""
        if user_input is not None:
            return self.async_create_entry(
                title="", data={**self.entry.options, **user_input})
        cur = self.entry.options.get(const.CONF_EXPOSE_MIRRORS, False)
        schema = vol.Schema({
            vol.Optional(const.CONF_EXPOSE_MIRRORS, default=cur): bool,
        })
        return self.async_show_form(step_id="mirrors", data_schema=schema)

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


class ZonesOptionsFlow(OptionsFlow):
    """Tree editor (F24): create zones/groups and assign modules/zones."""

    def __init__(self, entry: ConfigEntry) -> None:
        self.entry = entry
        self._tree = zones.normalize(entry.options.get(const.CONF_ZONES_TREE))
        self._sel: str | None = None   # zone/group being edited

    def _save(self):
        return self.async_create_entry(
            title="", data={const.CONF_ZONES_TREE: self._tree})

    def _module_options(self) -> list[selector.SelectOptionDict]:
        out = []
        for e in self.hass.config_entries.async_entries(const.DOMAIN):
            if e.data.get(const.CONF_MODULE) in _ASSIGNABLE:
                out.append(selector.SelectOptionDict(value=e.entry_id,
                                                     label=e.title))
        return out

    def _select(self, options, multiple=False, default=None):
        return selector.SelectSelector(selector.SelectSelectorConfig(
            options=options, multiple=multiple, mode=selector.SelectSelectorMode.LIST))

    async def async_step_init(self, user_input=None):
        menu = ["zone_add", "group_add"]
        if self._tree["zones"]:
            menu.insert(1, "zone_edit")
        if self._tree["groups"]:
            menu.append("group_edit")
        return self.async_show_menu(step_id="init", menu_options=menu)

    async def async_step_zone_add(self, user_input=None):
        if user_input is not None:
            self._tree = zones.add_zone(self._tree, user_input[const.CONF_NAME])
            return self._save()
        return self.async_show_form(
            step_id="zone_add",
            data_schema=vol.Schema({vol.Required(const.CONF_NAME): str}))

    async def async_step_group_add(self, user_input=None):
        if user_input is not None:
            self._tree = zones.add_group(self._tree, user_input[const.CONF_NAME])
            return self._save()
        return self.async_show_form(
            step_id="group_add",
            data_schema=vol.Schema({vol.Required(const.CONF_NAME): str}))

    async def async_step_zone_edit(self, user_input=None):
        if user_input is not None:
            self._sel = user_input["zone"]
            return await self.async_step_zone_detail()
        opts = [selector.SelectOptionDict(value=z, label=v["name"])
                for z, v in self._tree["zones"].items()]
        return self.async_show_form(
            step_id="zone_edit",
            data_schema=vol.Schema({vol.Required("zone"): self._select(opts)}))

    async def async_step_zone_detail(self, user_input=None):
        z = self._tree["zones"][self._sel]
        if user_input is not None:
            if user_input.get("delete"):
                self._tree = zones.remove_zone(self._tree, self._sel)
            else:
                z["name"] = user_input.get(const.CONF_NAME, z["name"])
                self._tree = zones.assign_modules(
                    self._tree, self._sel, user_input.get("modules", []))
            return self._save()
        schema = vol.Schema({
            vol.Optional(const.CONF_NAME, default=z["name"]): str,
            vol.Optional("modules", default=z["modules"]):
                self._select(self._module_options(), multiple=True),
            vol.Optional("delete", default=False): bool,
        })
        return self.async_show_form(step_id="zone_detail", data_schema=schema)

    async def async_step_group_edit(self, user_input=None):
        if user_input is not None:
            self._sel = user_input["group"]
            return await self.async_step_group_detail()
        opts = [selector.SelectOptionDict(value=g, label=v["name"])
                for g, v in self._tree["groups"].items()]
        return self.async_show_form(
            step_id="group_edit",
            data_schema=vol.Schema({vol.Required("group"): self._select(opts)}))

    async def async_step_group_detail(self, user_input=None):
        g = self._tree["groups"][self._sel]
        if user_input is not None:
            if user_input.get("delete"):
                self._tree = zones.remove_group(self._tree, self._sel)
            else:
                g["name"] = user_input.get(const.CONF_NAME, g["name"])
                self._tree = zones.assign_zones(
                    self._tree, self._sel, user_input.get("zones", []))
            return self._save()
        zopts = [selector.SelectOptionDict(value=z, label=v["name"])
                 for z, v in self._tree["zones"].items()]
        schema = vol.Schema({
            vol.Optional(const.CONF_NAME, default=g["name"]): str,
            vol.Optional("zones", default=g["zones"]):
                self._select(zopts, multiple=True),
            vol.Optional("delete", default=False): bool,
        })
        return self.async_show_form(step_id="group_detail", data_schema=schema)
