"""Number platform — IAQ thresholds as first-class tunable entities.

These replace a handful of the YAML ``input_number`` helpers. Editing them
updates the config entry options, which reloads the coordinator.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import const
from .coordinator import DsCoordinator, DvCoordinator
from .ds_engine import DsConfig


@dataclass(frozen=True)
class ThresholdDesc:
    key: str
    name: str
    default: float
    min_v: float
    max_v: float
    step: float
    unit: str


THRESHOLDS: tuple[ThresholdDesc, ...] = (
    ThresholdDesc(const.OPT_CO2_V2, "CO₂ V2 threshold", 900, 700, 1200, 25, "ppm"),
    ThresholdDesc(const.OPT_CO2_V3, "CO₂ V3 threshold", 1300, 1000, 1600, 25, "ppm"),
    ThresholdDesc(const.OPT_PM_V2, "PM2.5 V2 threshold", 15, 5, 25, 1, "µg/m³"),
    ThresholdDesc(const.OPT_PM_V3, "PM2.5 V3 threshold", 40, 20, 60, 5, "µg/m³"),
    ThresholdDesc(const.OPT_FILTER_LIFE_HOURS, "Filter life",
                  const.FILTER_LIFE_DEFAULT, 500, 8760, 50, "h"),
)


@dataclass(frozen=True)
class CoordNumberDesc:
    key: str
    name: str
    default: float
    min_v: float
    max_v: float
    step: float
    icon: str
    getter: Callable[[DsCoordinator], float]
    setter: Callable[[DsCoordinator, float], None]
    unit: str = "%"
    category: EntityCategory | None = None


_SHUTTER_NUMBERS: tuple[CoordNumberDesc, ...] = (
    CoordNumberDesc(
        "privacy_pct", "Privacy position", 40, 0, 100, 5, "mdi:blinds-horizontal",
        lambda c: c.privacy_pct, lambda c, v: setattr(c, "privacy_pct", v),
        category=EntityCategory.CONFIG),
    CoordNumberDesc(
        "lock_pct", "Lock position", 50, 0, 100, 5, "mdi:lock",
        lambda c: c.lock_pct, lambda c, v: setattr(c, "lock_pct", v),
        category=EntityCategory.CONFIG),
)


# Curated tunables promoted to first-class "Configuración" numbers on the device
# page + dashboard. Backed by the config-entry options (same store the options
# menu edits) -> no duplicate source of truth; both stay in sync. The deep/expert
# tunables stay in the options flow only. ``scale``: displayed = stored*scale
# (override is stored in hours, shown in minutes).
@dataclass(frozen=True)
class OptionNumberDesc:
    key: str            # options key == DsConfig field == translation key
    icon: str
    min_v: float
    max_v: float
    step: float
    unit: str
    scale: float = 1.0
    precision: int | None = None


_DS_DEFAULTS = DsConfig()

_DS_OPTION_NUMBERS: tuple[OptionNumberDesc, ...] = (
    # Thresholds
    OptionNumberDesc("override_hours", "mdi:timer-cog-outline", 0, 720, 5, "min",
                     scale=60.0),
    OptionNumberDesc("wind_limit_kmh", "mdi:weather-windy", 0, 120, 1, "km/h"),
    OptionNumberDesc("hot_delta", "mdi:thermometer-chevron-up", 0, 5, 0.1, "°C",
                     precision=1),
    OptionNumberDesc("cold_delta", "mdi:thermometer-chevron-down", 0, 5, 0.1, "°C",
                     precision=1),
    OptionNumberDesc("freecool_delta", "mdi:snowflake-thermometer", 0, 5, 0.1,
                     "°C", precision=1),
    # Positions "to taste"
    OptionNumberDesc("summer_min_open_pct", "mdi:blinds-horizontal", 0, 100, 5,
                     "%"),
    OptionNumberDesc("heat_shield_pct", "mdi:blinds", 0, 100, 5, "%"),
    OptionNumberDesc("weather_max_open_pct", "mdi:weather-windy-variant", 0, 100,
                     5, "%"),
    OptionNumberDesc("sleep_pct", "mdi:blinds", 0, 100, 5, "%"),
    OptionNumberDesc("rain_close_pct", "mdi:weather-pouring", 0, 100, 5, "%"),
    OptionNumberDesc("dawn_target_pct", "mdi:blinds-open", 0, 100, 5, "%"),
)


_VMC_NUMBERS: tuple[CoordNumberDesc, ...] = (
    CoordNumberDesc(
        "override_minutes", "Override timer", const.OVERRIDE_MIN_DEFAULT,
        0, const.OVERRIDE_MIN_MAX, 5, "mdi:timer-cog-outline",
        lambda c: c.override_minutes,
        lambda c, v: setattr(c, "override_minutes", int(v)), unit="min"),
    CoordNumberDesc(
        "quiet_max_level", "Quiet max level", 1, 0, 2, 1, "mdi:volume-mute",
        lambda c: c.quiet_max_level,
        lambda c, v: setattr(c, "quiet_max_level", int(v)), unit=""),
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry,
                            async_add_entities: AddEntitiesCallback) -> None:
    coordinator = hass.data[const.DOMAIN][entry.entry_id]
    if entry.data.get(const.CONF_MODULE) == const.MODULE_SHUTTER:
        ents: list[NumberEntity] = [
            CoordNumber(coordinator, entry, d) for d in _SHUTTER_NUMBERS]
        ents += [OptionNumber(entry, d) for d in _DS_OPTION_NUMBERS]
        async_add_entities(ents)
    else:
        entities: list[NumberEntity] = [
            ThresholdNumber(coordinator, entry, d) for d in THRESHOLDS]
        entities += [CoordNumber(coordinator, entry, d) for d in _VMC_NUMBERS]
        async_add_entities(entities)


class ThresholdNumber(NumberEntity):
    """A single IAQ threshold backed by config-entry options."""

    _attr_has_entity_name = True
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: DvCoordinator, entry: ConfigEntry,
                 desc: ThresholdDesc) -> None:
        self._coordinator = coordinator
        self._entry = entry
        self._desc = desc
        self._attr_unique_id = f"{entry.entry_id}_{desc.key}"
        self._attr_translation_key = desc.key   # name from translations (i18n)
        self._attr_native_min_value = desc.min_v
        self._attr_native_max_value = desc.max_v
        self._attr_native_step = desc.step
        self._attr_native_unit_of_measurement = desc.unit
        self._attr_device_info = DeviceInfo(
            identifiers={(const.DOMAIN, entry.entry_id)})

    @property
    def native_value(self) -> float:
        return self._entry.options.get(self._desc.key, self._desc.default)

    async def async_set_native_value(self, value: float) -> None:
        options = dict(self._entry.options)
        options[self._desc.key] = value
        # Updating the entry options fires the update listener, which refreshes
        # the coordinator (no reload -> EMA/failsafe state preserved).
        self.hass.config_entries.async_update_entry(
            self._entry, options=options)
        self.async_write_ha_state()


class CoordNumber(NumberEntity, RestoreEntity):
    """A number backed by a coordinator attribute (shutter privacy/lock)."""

    _attr_has_entity_name = True
    # Box (−/value/+) rather than a slider: on mobile a slider is easy to nudge
    # by accident.
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: DsCoordinator, entry: ConfigEntry,
                 desc: CoordNumberDesc) -> None:
        self._coordinator = coordinator
        self._desc = desc
        self._attr_unique_id = f"{entry.entry_id}_{desc.key}"
        self._attr_translation_key = desc.key   # name from translations (i18n)
        self._attr_icon = desc.icon
        self._attr_native_min_value = desc.min_v
        self._attr_native_max_value = desc.max_v
        self._attr_native_step = desc.step
        self._attr_native_unit_of_measurement = desc.unit
        if desc.unit != "%":
            self._attr_mode = NumberMode.BOX
        if desc.category is not None:
            self._attr_entity_category = desc.category
        self._attr_device_info = DeviceInfo(
            identifiers={(const.DOMAIN, entry.entry_id)})

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None:
            try:
                self._desc.setter(self._coordinator, float(last.state))
            except (TypeError, ValueError):
                pass

    @property
    def native_value(self) -> float:
        return self._desc.getter(self._coordinator)

    async def async_set_native_value(self, value: float) -> None:
        self._desc.setter(self._coordinator, value)
        await self._coordinator.async_request_refresh()
        self.async_write_ha_state()


class OptionNumber(NumberEntity):
    """A curated DS tunable, backed by the config-entry options (Configuración).

    Reads/writes the same ``entry.options[key]`` the options menu edits, so both
    editors stay in sync — no duplicate source of truth. Editing the options fires
    the update listener, which refreshes the coordinator without a reload.
    """

    _attr_has_entity_name = True
    _attr_mode = NumberMode.BOX
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, entry: ConfigEntry, desc: OptionNumberDesc) -> None:
        self._entry = entry
        self._desc = desc
        self._attr_unique_id = f"{entry.entry_id}_{desc.key}"
        self._attr_translation_key = desc.key   # name from translations (i18n)
        self._attr_icon = desc.icon
        self._attr_native_min_value = desc.min_v
        self._attr_native_max_value = desc.max_v
        self._attr_native_step = desc.step
        self._attr_native_unit_of_measurement = desc.unit
        self._attr_device_info = DeviceInfo(
            identifiers={(const.DOMAIN, entry.entry_id)})

    @property
    def native_value(self) -> float:
        stored = self._entry.options.get(
            self._desc.key, getattr(_DS_DEFAULTS, self._desc.key))
        v = stored * self._desc.scale
        return round(v, self._desc.precision) if self._desc.precision else v

    async def async_set_native_value(self, value: float) -> None:
        options = dict(self._entry.options)
        options[self._desc.key] = value / self._desc.scale
        self.hass.config_entries.async_update_entry(self._entry, options=options)
        self.async_write_ha_state()
