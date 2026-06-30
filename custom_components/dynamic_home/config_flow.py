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

from . import (
    const,
    install,
    modes,
    options_spec,
    presets,
    schedule,
    zones,
)
from . import (
    emitters as emitters_mod,
)
from . import (
    presence as presence_mod,
)

# Weekday labels for the scheduler editor (Mon..Sun = 0..6, datetime.weekday()).
_WEEKDAYS = {
    "es": ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado",
           "Domingo"],
    "en": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday",
           "Sunday"],
}


def _entity(domain: str | list[str] | None = None,
            device_class: str | None = None,
            multiple: bool = False) -> selector.EntitySelector:
    cfg: dict[str, Any] = {}
    if domain:
        cfg["domain"] = domain
    if device_class:
        cfg["device_class"] = device_class
    if multiple:
        cfg["multiple"] = True
    return selector.EntitySelector(selector.EntitySelectorConfig(**cfg))


def _hhmm_to_min(value, default: int) -> int:
    """Parse a 'HH:MM[:SS]' time string into minutes from midnight."""
    try:
        h, m = str(value).split(":")[:2]
        return int(h) * 60 + int(m)
    except (TypeError, ValueError, AttributeError):
        return default


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
        vol.Optional(const.CONF_HRV_EXHAUST): _entity("sensor", "temperature"),
        vol.Optional(const.CONF_VOC): _entity("sensor"),
        vol.Optional(const.CONF_NOX): _entity("sensor"),
        vol.Optional(const.CONF_HOOD_V1): _entity("switch"),
        vol.Optional(const.CONF_HOOD_V2): _entity("switch"),
        vol.Optional(const.CONF_HOOD_V3): _entity("switch"),
        vol.Optional(const.CONF_POWER_METER): _entity("sensor", "power"),
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
        vol.Optional(const.CONF_RAIN): _entity(["binary_sensor"]),
        vol.Optional(const.CONF_DS_ALERT): _entity(["binary_sensor"]),
        vol.Optional(const.CONF_DS_ALERT_HAIL): _entity(["binary_sensor"]),
        vol.Optional(const.CONF_DS_ALERT_WIND): _entity(["binary_sensor"]),
        vol.Optional(const.CONF_POWER_METER): _entity("sensor", "power"),
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
        vol.Optional(const.CONF_DC_WATER_TEMP): _entity("sensor", "temperature"),
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
        vol.Optional(const.CONF_POWER_METER): _entity("sensor", "power"),
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

STEP_ENERGY_SCHEMA = vol.Schema(
    {
        vol.Required(const.CONF_NAME, default="Energía"): str,
        vol.Required(const.CONF_ENERGY_CONTRACTED, default=5750): vol.All(
            vol.Coerce(float), vol.Range(min=1000, max=43600)),
        vol.Optional(const.CONF_ENERGY_GRID): _entity("sensor", "power"),
        vol.Optional(const.CONF_ENERGY_PRICE): _entity("sensor"),
        vol.Optional(const.CONF_ENERGY_TOTAL): _entity("sensor", "power"),
        vol.Optional(const.CONF_ENERGY_PV): _entity("sensor", "power"),
        vol.Optional(const.CONF_ENERGY_BATT_SOC): _entity("sensor", "battery"),
    }
)

# Module entries that can be assigned to a zone (everything but the Zones entry).
_ASSIGNABLE = (const.MODULE_VMC, const.MODULE_SHUTTER, const.MODULE_CLIMATE,
               const.MODULE_WEATHER)

# The entity/hardware schema per module, reused by the options "Edit entities"
# step so the chosen sensors/relays can be changed after setup (no delete + re-add).
_HARDWARE_SCHEMA = {
    const.MODULE_VMC: STEP_USER_SCHEMA,
    const.MODULE_SHUTTER: STEP_SHUTTER_SCHEMA,
    const.MODULE_CLIMATE: STEP_CLIMATE_SCHEMA,
    const.MODULE_WEATHER: STEP_WEATHER_SCHEMA,
    const.MODULE_ENERGY: STEP_ENERGY_SCHEMA,
}


def _ds_entries(hass) -> list:
    """Existing shutter (DS) config entries — used as copy/clone templates."""
    return [e for e in hass.config_entries.async_entries(const.DOMAIN)
            if e.data.get(const.CONF_MODULE) == const.MODULE_SHUTTER]


class DynamicHomeConfigFlow(ConfigFlow, domain=const.DOMAIN):
    """Handle the initial setup wizard."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Entry point: choose which module to add."""
        return self.async_show_menu(
            step_id="user",
            menu_options=["vmc", "shutter", "climate", "weather", "zones",
                          "energy"])

    async def async_step_energy(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            await self.async_set_unique_id("energy_singleton")
            self._abort_if_unique_id_configured()       # one energy entry only
            data = {**user_input, const.CONF_MODULE: const.MODULE_ENERGY}
            return self.async_create_entry(
                title=user_input[const.CONF_NAME], data=data)
        return self.async_show_form(
            step_id="energy", data_schema=STEP_ENERGY_SCHEMA)

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
        """Optionally pick an existing shutter as a template, then show the form.

        Near-identical windows (e.g. three in one room) only differ in the cover
        entity. Copying a sibling pre-fills the form with everything but the cover
        and clones its options/tunables, so you just pick the new cover and adjust.
        """
        others = _ds_entries(self.hass)
        if not others:                       # first shutter: straight to the form
            return await self.async_step_shutter_form()
        if user_input is not None:
            self._ds_copy_from = user_input.get("copy_from") or None
            return await self.async_step_shutter_form()
        opts = [selector.SelectOptionDict(value="", label="—")]
        opts += [selector.SelectOptionDict(value=e.entry_id, label=e.title)
                 for e in others]
        schema = vol.Schema({
            vol.Optional("copy_from", default=""): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=opts, mode=selector.SelectSelectorMode.DROPDOWN))})
        return self.async_show_form(step_id="shutter", data_schema=schema)

    async def async_step_shutter_form(self,
                                      user_input: dict[str, Any] | None = None):
        """The shutter entity form; pre-filled from a template when chosen."""
        src_id = getattr(self, "_ds_copy_from", None)
        src = (self.hass.config_entries.async_get_entry(src_id)
               if src_id else None)
        if user_input is not None:
            await self.async_set_unique_id(f"ds_{user_input[const.CONF_COVER]}")
            self._abort_if_unique_id_configured()
            data = {**user_input, const.CONF_MODULE: const.MODULE_SHUTTER}
            return self.async_create_entry(
                title=user_input[const.CONF_NAME], data=data,
                options=dict(src.options) if src else {})   # clone the tunables
        schema = STEP_SHUTTER_SCHEMA
        if src:
            suggested = {k: v for k, v in src.data.items()
                         if k not in (const.CONF_COVER, const.CONF_MODULE)}
            schema = self.add_suggested_values_to_schema(
                STEP_SHUTTER_SCHEMA, suggested)
        return self.async_show_form(step_id="shutter_form", data_schema=schema)

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
        self._sched_day = 0             # weekday being edited (F21)
        self._install_gen = ""          # generator being declared (F26)
        self._install_dist = "individual"
        self._emitter_sel: str | None = None   # emitter being edited (F25)

    def _lang(self) -> str:
        return getattr(self.hass.config, "language", "en") if self.hass else "en"

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        # Show every category (no HA "advanced mode" needed); advanced/expert
        # ones are labelled and sorted last by options_spec.categories().
        cats = options_spec.categories(self._module)
        menu = [f"cat_{c}" for c in cats]
        # Edit the chosen entities/relays after setup (add/change/remove), so a
        # forgotten sensor or the hood relays don't force a delete + re-add.
        if self._module in _HARDWARE_SCHEMA:
            menu.insert(0, "hardware")
        if not menu:
            return self.async_abort(reason="no_options")
        if presets.preset_ids(self._module):
            menu.append("preset")
        # Weekly scheduler (F21): VMC (speed) and climate (base setpoint) only.
        if self._module in (const.MODULE_VMC, const.MODULE_CLIMATE):
            menu.append("schedule")
        # Bathrooms for the shower boost (F13): VMC only.
        if self._module == const.MODULE_VMC:
            menu.append("bathrooms")
        # Clone settings from a sibling shutter (only if there is one to copy).
        if self._module == const.MODULE_SHUTTER and any(
                e.entry_id != self.entry.entry_id for e in _ds_entries(self.hass)):
            menu.append("clone")
        # Installation type (F26) + emitters editor (F25): climate zones only.
        if self._module == const.MODULE_CLIMATE:
            menu.append("install")
            menu.append("emitters")
        menu.append("mirrors")
        return self.async_show_menu(step_id="init", menu_options=menu)

    # --- F26 installation wizard: generator -> [distribution] -> emission ---
    def _catalog_select(self, key: str, catalog: dict, default: str):
        opts = [selector.SelectOptionDict(
                    value=k, label=install.label(catalog, k, self._lang()))
                for k in catalog]
        return vol.Schema({vol.Required(key, default=default):
                           selector.SelectSelector(selector.SelectSelectorConfig(
                               options=opts,
                               mode=selector.SelectSelectorMode.LIST))})

    async def async_step_install(self, user_input: dict[str, Any] | None = None):
        """Pick the heat generator (step 1: generator -> distribution -> emitter)."""
        if user_input is not None:
            self._install_gen = user_input["generator"]
            if install.forced_individual(self._install_gen):
                self._install_dist = "individual"   # electric/air-air: no choice
                return await self.async_step_install_emission()
            return await self.async_step_install_dist()
        cur = (self.entry.options.get(const.CONF_GENERATOR)
               or next(iter(install.GENERATORS)))
        return self.async_show_form(
            step_id="install",
            data_schema=self._catalog_select(
                "generator", install.GENERATORS, cur))

    async def async_step_install_dist(self,
                                      user_input: dict[str, Any] | None = None):
        """Pick the distribution (only when not forced individual)."""
        if user_input is not None:
            self._install_dist = user_input["distribution"]
            return await self.async_step_install_emission()
        cur = self.entry.options.get(const.CONF_DISTRIBUTION) or "individual"
        return self.async_show_form(
            step_id="install_dist",
            data_schema=self._catalog_select(
                "distribution", install.DISTRIBUTIONS, cur))

    async def async_step_install_emission(self,
                                          user_input: dict[str, Any] | None = None):
        """Pick the emitter, then store the triple + pre-load inertia defaults."""
        if user_input is not None:
            gen, dist = self._install_gen, self._install_dist
            emission = user_input["emission"]
            merged = {
                **self.entry.options,
                const.CONF_GENERATOR: gen,
                const.CONF_DISTRIBUTION: dist,
                const.CONF_EMISSION: emission,
                **install.defaults(gen, dist, emission),
            }
            return self.async_create_entry(title="", data=merged)
        cur = (self.entry.options.get(const.CONF_EMISSION)
               or next(iter(install.EMISSIONS)))
        return self.async_show_form(
            step_id="install_emission",
            data_schema=self._catalog_select(
                "emission", install.EMISSIONS, cur))

    # --- F25 emitters editor (1..N emitters per zone; mirrors the zones editor) ---
    def _emitters(self) -> list[dict]:
        return emitters_mod.normalize(self.entry.options.get("emitters"))

    def _save_emitters(self, lst: list[dict]):
        return self.async_create_entry(
            title="", data={**self.entry.options,
                            "emitters": emitters_mod.normalize(lst)})

    def _emitter_schema(self, cur: dict) -> vol.Schema:
        lang = self._lang()
        es = lang.startswith("es")

        def cat(catalog, default):
            opts = [selector.SelectOptionDict(
                        value=k, label=install.label(catalog, k, lang))
                    for k in catalog]
            return (vol.Required(default[0], default=default[1]),
                    selector.SelectSelector(selector.SelectSelectorConfig(
                        options=opts)))

        def listsel(values, labels, default):
            opts = [selector.SelectOptionDict(value=v, label=labels[v])
                    for v in values]
            return selector.SelectSelector(selector.SelectSelectorConfig(
                options=opts, mode=selector.SelectSelectorMode.LIST))

        scope_labels = {
            "zone": "Zona (split)" if es else "Zone (split)",
            "group_unzoned": ("Conductos compartidos" if es
                              else "Shared ducts (un-zoned)"),
            "group_grilles": ("Conductos + rejillas" if es
                              else "Ducts + motorized grilles")}
        policy_labels = {
            "weighted": "Ponderada" if es else "Weighted",
            "mean": "Media" if es else "Mean",
            "priority": "Prioridad" if es else "Priority",
            "worst_stuck": "Peor parada" if es else "Worst-stuck"}
        gk, gsel = cat(install.GENERATORS,
                       ("generator", cur.get("generator")
                        or next(iter(install.GENERATORS))))
        dk, dsel = cat(install.DISTRIBUTIONS,
                       ("distribution", cur.get("distribution") or "individual"))
        ek, esel = cat(install.EMISSIONS,
                       ("emission", cur.get("emission")
                        or next(iter(install.EMISSIONS))))
        return vol.Schema({
            vol.Required("name", default=cur.get("name", "")): str,
            gk: gsel, dk: dsel, ek: esel,
            vol.Optional("climate", description={
                "suggested_value": cur.get("climate")}): _entity("climate"),
            vol.Optional("switch", description={
                "suggested_value": cur.get("switch")}): _entity(
                    ["switch", "input_boolean"]),
            vol.Optional("primary_heat",
                         default=cur.get("primary_heat", False)): bool,
            vol.Optional("primary_cool",
                         default=cur.get("primary_cool", False)): bool,
            vol.Required("scope", default=cur.get("scope", "zone")):
                listsel(emitters_mod._SCOPES, scope_labels, None),
            vol.Optional("shared_emitter_id", description={
                "suggested_value": cur.get("shared_emitter_id")}): str,
            vol.Optional("owner", default=cur.get("owner", False)): bool,
            vol.Required("policy", default=cur.get("policy", "weighted")):
                listsel(emitters_mod.POLICIES, policy_labels, None),
            vol.Optional("compressor_id", description={
                "suggested_value": cur.get("compressor_id")}): str,
        })

    def _form_to_emitter(self, ui: dict[str, Any]) -> dict:
        return {k: ui.get(k) for k in (
            "name", "generator", "distribution", "emission", "climate", "switch",
            "primary_heat", "primary_cool", "scope", "shared_emitter_id",
            "owner", "policy", "compressor_id")}

    async def async_step_emitters(self, user_input: dict[str, Any] | None = None):
        menu = ["emitter_add"]
        if self._emitters():
            menu.append("emitter_edit")
        return self.async_show_menu(step_id="emitters", menu_options=menu)

    async def async_step_emitter_add(self,
                                     user_input: dict[str, Any] | None = None):
        if user_input is not None:
            lst = self._emitters()
            lst.append(self._form_to_emitter(user_input))
            return self._save_emitters(lst)
        return self.async_show_form(
            step_id="emitter_add", data_schema=self._emitter_schema({}))

    async def async_step_emitter_edit(self,
                                      user_input: dict[str, Any] | None = None):
        lst = self._emitters()
        if user_input is not None:
            self._emitter_sel = user_input["emitter"]
            return await self.async_step_emitter_detail()
        opts = [selector.SelectOptionDict(value=e["id"], label=e["name"])
                for e in lst]
        schema = vol.Schema({vol.Required("emitter"): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=opts, mode=selector.SelectSelectorMode.LIST))})
        return self.async_show_form(step_id="emitter_edit", data_schema=schema)

    async def async_step_emitter_detail(self,
                                        user_input: dict[str, Any] | None = None):
        lst = self._emitters()
        cur = next((e for e in lst if e["id"] == self._emitter_sel), None)
        if cur is None:
            return await self.async_step_emitters()
        if user_input is not None:
            if user_input.get("delete"):
                lst = [e for e in lst if e["id"] != self._emitter_sel]
            else:
                new = self._form_to_emitter(user_input)
                new["id"] = cur["id"]                     # keep the stable id
                lst = [new if e["id"] == self._emitter_sel else e for e in lst]
            return self._save_emitters(lst)
        schema = self._emitter_schema(cur).extend(
            {vol.Optional("delete", default=False): bool})
        return self.async_show_form(step_id="emitter_detail", data_schema=schema)

    # --- F21 weekly scheduler editor (shared format; one profile per entry) ---
    def _weekday_names(self) -> list[str]:
        lang = getattr(self.hass.config, "language", "en") if self.hass else "en"
        return _WEEKDAYS.get(lang, _WEEKDAYS["en"])

    def _slot_label(self, slot: dict) -> str:
        v = slot["value"]
        if self._module == const.MODULE_VMC:
            return f"{slot['start']}→{'Off' if int(v) == 0 else f'V{int(v)}'}"
        return f"{slot['start']}→{v}°"

    async def async_step_schedule(self, user_input: dict[str, Any] | None = None):
        """Pick the weekday to edit (each shows a one-line summary)."""
        if user_input is not None:
            self._sched_day = int(user_input["day"])
            return await self.async_step_schedule_day()
        sched = schedule.normalize(self.entry.options.get(const.CONF_SCHEDULE))
        names = self._weekday_names()
        opts = []
        for d in range(7):
            slots = sched.get(str(d), [])
            summary = ", ".join(self._slot_label(s) for s in slots) or "—"
            opts.append(selector.SelectOptionDict(
                value=str(d), label=f"{names[d]}: {summary}"))
        schema = vol.Schema({vol.Required("day"): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=opts, mode=selector.SelectSelectorMode.LIST))})
        return self.async_show_form(step_id="schedule", data_schema=schema)

    async def async_step_schedule_day(self,
                                      user_input: dict[str, Any] | None = None):
        """Edit one weekday's up to 4 slots (start + value), with copy/clear."""
        d = self._sched_day
        sched = schedule.normalize(self.entry.options.get(const.CONF_SCHEDULE))
        is_vmc = self._module == const.MODULE_VMC
        if user_input is not None:
            if user_input.get("clear"):
                sched = schedule.clear_day(sched, d)
            else:
                slots = []
                for i in range(1, schedule.MAX_SLOTS + 1):
                    start = user_input.get(f"start_{i}")
                    val = user_input.get(f"value_{i}")
                    if start and val not in (None, ""):
                        slots.append({"start": start,
                                      "value": int(val) if is_vmc else float(val)})
                sched = schedule.set_day(sched, d, slots)
                copy_to = user_input.get("copy_to") or []
                if copy_to:
                    sched = schedule.copy_day(sched, d, [int(x) for x in copy_to])
            return self.async_create_entry(
                title="", data={**self.entry.options, const.CONF_SCHEDULE: sched})
        day_slots = sched.get(str(d), [])
        out: dict = {}
        for i in range(1, schedule.MAX_SLOTS + 1):
            cur = day_slots[i - 1] if i - 1 < len(day_slots) else None
            t_key = vol.Optional(
                f"start_{i}", description={"suggested_value":
                                           f"{cur['start']}:00" if cur else None})
            out[t_key] = selector.TimeSelector()
            v_key = vol.Optional(
                f"value_{i}", description={"suggested_value":
                                           cur["value"] if cur else None})
            out[v_key] = self._value_selector(is_vmc)
        names = self._weekday_names()
        out[vol.Optional("copy_to", default=[])] = selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[selector.SelectOptionDict(value=str(x), label=names[x])
                         for x in range(7)],
                multiple=True, mode=selector.SelectSelectorMode.LIST))
        out[vol.Optional("clear", default=False)] = bool
        return self.async_show_form(
            step_id="schedule_day", data_schema=vol.Schema(out),
            description_placeholders={"day": names[d]})

    def _value_selector(self, is_vmc: bool):
        if is_vmc:
            return selector.SelectSelector(selector.SelectSelectorConfig(
                options=[selector.SelectOptionDict(value="0", label="Off"),
                         selector.SelectOptionDict(value="1", label="V1"),
                         selector.SelectOptionDict(value="2", label="V2"),
                         selector.SelectOptionDict(value="3", label="V3")]))
        return selector.NumberSelector(selector.NumberSelectorConfig(
            min=5, max=35, step=0.1, unit_of_measurement="°C",
            mode=selector.NumberSelectorMode.BOX))

    async def async_step_hardware(self, user_input: dict[str, Any] | None = None):
        """Edit the module's chosen entities/relays after setup (reconfigure).

        Re-shows the same entity form used at creation, pre-filled with what is
        configured. Saving updates the entry data and reloads the module so new or
        removed entities (e.g. the extractor-hood relays) take effect — without
        deleting and re-adding the entry, keeping its options and history.
        """
        schema = _HARDWARE_SCHEMA.get(self._module)
        if schema is None:
            return self.async_abort(reason="no_options")
        if user_input is not None:
            keys = {m.schema for m in schema.schema}
            # Keep non-schema data (module id, etc.); cleared optional fields drop
            # out of user_input, so they are correctly removed.
            data = {k: v for k, v in self.entry.data.items() if k not in keys}
            data.update(user_input)
            title = user_input.get(const.CONF_NAME) or self.entry.title
            self.hass.config_entries.async_update_entry(
                self.entry, data=data, title=title)
            self.hass.async_create_task(
                self.hass.config_entries.async_reload(self.entry.entry_id))
            return self.async_create_entry(title="", data=dict(self.entry.options))
        return self.async_show_form(
            step_id="hardware",
            data_schema=self.add_suggested_values_to_schema(
                schema, dict(self.entry.data)))

    async def async_step_clone(self, user_input: dict[str, Any] | None = None):
        """Copy another shutter's data (except its cover) + options onto this one.

        For near-identical windows: configure one fully, then clone it into the
        siblings and only fine-tune what differs. Keeps this entry's own cover and
        name; reloads so the copied entities take effect.
        """
        others = [e for e in _ds_entries(self.hass)
                  if e.entry_id != self.entry.entry_id]
        if not others:
            return self.async_abort(reason="no_options")
        if user_input is not None:
            src = self.hass.config_entries.async_get_entry(user_input["source"])
            data = {**src.data,
                    const.CONF_COVER: self.entry.data.get(const.CONF_COVER),
                    const.CONF_NAME: self.entry.data.get(const.CONF_NAME,
                                                         self.entry.title),
                    const.CONF_MODULE: const.MODULE_SHUTTER}
            self.hass.config_entries.async_update_entry(self.entry, data=data)
            self.hass.async_create_task(
                self.hass.config_entries.async_reload(self.entry.entry_id))
            return self.async_create_entry(title="", data=dict(src.options))
        opts = [selector.SelectOptionDict(value=e.entry_id, label=e.title)
                for e in others]
        schema = vol.Schema({
            vol.Required("source"): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=opts, mode=selector.SelectSelectorMode.DROPDOWN))})
        return self.async_show_form(step_id="clone", data_schema=schema)

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

    async def async_step_bathrooms(self, user_input: dict[str, Any] | None = None):
        """Configure up to ``BATHROOM_MAX`` bathrooms (name + humidity) for F13.

        Each filled row adds a bathroom the shower boost watches; the engine takes
        the largest RH rise across them. Cleared rows are removed from the options.
        """
        if user_input is not None:
            merged = {**self.entry.options}
            for i in range(1, const.BATHROOM_MAX + 1):
                for base in (const.CONF_BATH_NAME, const.CONF_BATH_HUM):
                    key = f"{base}_{i}"
                    if user_input.get(key):
                        merged[key] = user_input[key]
                    else:
                        merged.pop(key, None)
            return self.async_create_entry(title="", data=merged)
        o = self.entry.options
        fields: dict = {}
        for i in range(1, const.BATHROOM_MAX + 1):
            name_key = f"{const.CONF_BATH_NAME}_{i}"
            hum_key = f"{const.CONF_BATH_HUM}_{i}"
            fields[vol.Optional(name_key, description={
                "suggested_value": o.get(name_key)})] = str
            fields[vol.Optional(hum_key, description={
                "suggested_value": o.get(hum_key)})] = _entity("sensor", "humidity")
        return self.async_show_form(
            step_id="bathrooms", data_schema=vol.Schema(fields))

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
            if cat in options_spec.categories(self.__dict__.get("_module")):
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
        for opt in options_spec.fields(self._module, cat):   # all fields visible
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
        self._presence_zid: str | None = None   # zone whose sources are edited (F32)

    def _save(self):
        # Preserve the other options (modes caps, presence) — only the tree changed.
        return self.async_create_entry(
            title="", data={**self.entry.options, const.CONF_ZONES_TREE: self._tree})

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
        menu.append("mode_caps")
        menu.append("ds_peak")
        menu.append("presence")
        menu.append("changeover")
        return self.async_show_menu(step_id="init", menu_options=menu)

    async def async_step_ds_peak(self, user_input=None):
        """Global shutter peak limit: all participating shutters read this."""
        if user_input is not None:
            peak = {"max_zones": int(user_input["max_zones"]),
                    "max_power_w": float(user_input["max_power_w"]),
                    "stagger_s": float(user_input["stagger_s"])}
            return self.async_create_entry(
                title="", data={**self.entry.options, const.CONF_DS_PEAK: peak})
        cur = self.entry.options.get(const.CONF_DS_PEAK) or {}
        schema = vol.Schema({
            vol.Required("max_zones", default=cur.get("max_zones", 2)):
                vol.All(vol.Coerce(int), vol.Range(min=1, max=20)),
            vol.Required("max_power_w", default=cur.get("max_power_w", 0.0)):
                vol.All(vol.Coerce(float), vol.Range(min=0, max=10000)),
            vol.Required("stagger_s", default=cur.get("stagger_s", 10.0)):
                vol.All(vol.Coerce(float), vol.Range(min=0, max=120)),
        })
        return self.async_show_form(step_id="ds_peak", data_schema=schema)

    # --- F37 community changeover (supply-water sensor + thresholds) ---
    async def async_step_changeover(self, user_input=None):
        o = self.entry.options
        if user_input is not None:
            tune = {"heat_above_c": float(user_input["heat_above_c"]),
                    "cool_below_c": float(user_input["cool_below_c"]),
                    "hysteresis_c": float(user_input["hysteresis_c"])}
            data = {**o, const.CONF_CHANGEOVER_TUNE: tune}
            sensor = user_input.get("changeover_sensor")
            if sensor:
                data[const.CONF_CHANGEOVER_SENSOR] = sensor
            else:
                data.pop(const.CONF_CHANGEOVER_SENSOR, None)
            return self.async_create_entry(title="", data=data)
        tune = o.get(const.CONF_CHANGEOVER_TUNE) or {}
        num = vol.All(vol.Coerce(float), vol.Range(min=-10, max=90))
        schema = vol.Schema({
            vol.Optional("changeover_sensor", description={
                "suggested_value": o.get(const.CONF_CHANGEOVER_SENSOR)}):
                _entity("sensor", "temperature"),
            vol.Required("heat_above_c",
                         default=tune.get("heat_above_c", 28.0)): num,
            vol.Required("cool_below_c",
                         default=tune.get("cool_below_c", 20.0)): num,
            vol.Required("hysteresis_c",
                         default=tune.get("hysteresis_c", 2.0)): vol.All(
                vol.Coerce(float), vol.Range(min=0, max=15)),
        })
        return self.async_show_form(step_id="changeover", data_schema=schema)

    # --- F32 presence editor (house settings + per-zone sources) ---
    async def async_step_presence(self, user_input=None):
        menu = ["presence_house"]
        if self._tree["zones"]:
            menu.append("presence_zone")
        return self.async_show_menu(step_id="presence", menu_options=menu)

    async def async_step_presence_house(self, user_input=None):
        o = self.entry.options
        if user_input is not None:
            tune = dict(o.get(const.CONF_PRESENCE_TUNE) or {})
            tune["sleep_start_min"] = _hhmm_to_min(
                user_input.get("sleep_start"), 23 * 60)
            tune["sleep_end_min"] = _hhmm_to_min(
                user_input.get("sleep_end"), 7 * 60)
            return self.async_create_entry(title="", data={
                **o,
                const.CONF_PRESENCE_PHONES: user_input.get("phones") or [],
                const.CONF_PRESENCE_AUTO: user_input.get("auto", False),
                const.CONF_PRESENCE_TUNE: tune})
        tune = o.get(const.CONF_PRESENCE_TUNE) or {}

        def _min_to_hhmm(minutes: int) -> str:
            return f"{minutes // 60:02d}:{minutes % 60:02d}:00"
        schema = vol.Schema({
            vol.Optional("phones",
                         default=o.get(const.CONF_PRESENCE_PHONES) or []):
                _entity(["device_tracker", "person"], multiple=True),
            vol.Optional("auto", default=o.get(const.CONF_PRESENCE_AUTO, False)): bool,
            vol.Optional("sleep_start", description={"suggested_value":
                         _min_to_hhmm(tune.get("sleep_start_min", 23 * 60))}):
                selector.TimeSelector(),
            vol.Optional("sleep_end", description={"suggested_value":
                         _min_to_hhmm(tune.get("sleep_end_min", 7 * 60))}):
                selector.TimeSelector(),
        })
        return self.async_show_form(step_id="presence_house", data_schema=schema)

    async def async_step_presence_zone(self, user_input=None):
        if user_input is not None:
            self._presence_zid = user_input["zone"]
            return await self.async_step_presence_zone_detail()
        opts = [selector.SelectOptionDict(value=z, label=v["name"])
                for z, v in self._tree["zones"].items()]
        return self.async_show_form(
            step_id="presence_zone",
            data_schema=vol.Schema({vol.Required("zone"): self._select(opts)}))

    async def async_step_presence_zone_detail(self, user_input=None):
        zid = self._presence_zid
        sources = dict(self.entry.options.get(const.CONF_PRESENCE_SOURCES) or {})
        cur = sources.get(zid, {})
        if user_input is not None:
            sources[zid] = {k: user_input.get(k) or []
                            for k in (presence_mod.PIR, presence_mod.MMWAVE,
                                      presence_mod.DOOR)}
            return self.async_create_entry(
                title="", data={**self.entry.options,
                                const.CONF_PRESENCE_SOURCES: sources})
        schema = vol.Schema({
            vol.Optional(presence_mod.PIR, default=cur.get("pir", [])):
                _entity(["binary_sensor"], multiple=True),
            vol.Optional(presence_mod.MMWAVE, default=cur.get("mmwave", [])):
                _entity(["binary_sensor"], multiple=True),
            vol.Optional(presence_mod.DOOR, default=cur.get("door", [])):
                _entity(["binary_sensor"], multiple=True),
        })
        return self.async_show_form(
            step_id="presence_zone_detail", data_schema=schema,
            description_placeholders={"zone": self._tree["zones"][zid]["name"]})

    async def async_step_mode_caps(self, user_input=None):
        """F01: per-mode VMC speed cap (0..3; for eco/sleep/away)."""
        if user_input is not None:
            caps = {k: int(v) for k, v in user_input.items()}
            return self.async_create_entry(
                title="", data={**self.entry.options, const.CONF_MODE_CAPS: caps})
        cur = self.entry.options.get(const.CONF_MODE_CAPS) or {}
        defaults = {**modes.DEFAULT_CAPS, **cur}
        num = vol.All(vol.Coerce(int), vol.Range(min=0, max=3))
        schema = vol.Schema({
            vol.Required(m, default=defaults.get(m) if defaults.get(m) is not None
                         else 3): num
            for m in ("eco", "sleep", "away")
        })
        return self.async_show_form(step_id="mode_caps", data_schema=schema)

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
