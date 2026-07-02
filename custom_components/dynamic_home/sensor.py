"""Sensor platform — VMC telemetry (DV).

Running hours per speed, total machine hours and filter hours (all restored
across restarts), plus the current speed and decision reason for diagnostics.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
    CONCENTRATION_PARTS_PER_MILLION,
    DEGREE,
    PERCENTAGE,
    EntityCategory,
    UnitOfEnergy,
    UnitOfPrecipitationDepth,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util
from homeassistant.util import slugify

from . import const, reason_text, schedule, zones
from .coordinator import DvCoordinator


@dataclass(frozen=True)
class _HoursDesc:
    key: str
    name: str
    icon: str
    getter: Callable[[DvCoordinator], float]
    setter: Callable[[DvCoordinator, float], None]


_HOURS: tuple[_HoursDesc, ...] = (
    _HoursDesc("hours_v1", "Hours V1", "mdi:fan-speed-1",
               lambda c: c.speed_hours[1],
               lambda c, v: c.speed_hours.__setitem__(1, v)),
    _HoursDesc("hours_v2", "Hours V2", "mdi:fan-speed-2",
               lambda c: c.speed_hours[2],
               lambda c, v: c.speed_hours.__setitem__(2, v)),
    _HoursDesc("hours_v3", "Hours V3", "mdi:fan-speed-3",
               lambda c: c.speed_hours[3],
               lambda c, v: c.speed_hours.__setitem__(3, v)),
    _HoursDesc("hours_machine", "Machine hours", "mdi:fan-clock",
               lambda c: c.machine_hours,
               lambda c, v: setattr(c, "machine_hours", v)),
    _HoursDesc("hours_filter", "Filter hours", "mdi:air-filter",
               lambda c: c.filter_hours,
               lambda c, v: setattr(c, "filter_hours", v)),
)


# F36: input roles republished as stable per-role mirror sensors (numeric
# inputs only; switches/covers/climate/binary roles are skipped).
_MIRROR_ROLES: dict[str, tuple[tuple[str, str], ...]] = {
    const.MODULE_VMC: (
        (const.CONF_CO2, "CO₂"),
        (const.CONF_PM25, "PM2.5"),
        (const.CONF_T_IN, "Temperatura interior"),
        (const.CONF_T_EXT, "Temperatura exterior"),
        (const.CONF_AQI, "AQI exterior"),
        (const.CONF_HUM_IN, "Humedad interior"),
        (const.CONF_HUM_BATH, "Humedad baño"),
        (const.CONF_HUM_EXT, "Humedad exterior"),
        (const.CONF_HRV_SUPPLY, "HRV impulsión"),
        (const.CONF_HRV_INTAKE, "HRV admisión"),
        (const.CONF_HRV_EXTRACT, "HRV extracción"),
        (const.CONF_HRV_EXHAUST, "HRV expulsión"),
        (const.CONF_VOC, "COV"),
        (const.CONF_NOX, "NOx"),
    ),
    const.MODULE_CLIMATE: (
        (const.CONF_DC_T_INT, "Temperatura interior"),
        (const.CONF_DC_T_EXT, "Temperatura exterior"),
        (const.CONF_DC_HUMIDITY, "Humedad interior"),
        (const.CONF_DC_WIND, "Viento"),
        (const.CONF_DC_ADJ_TEMP, "Temperatura adyacente"),
    ),
    const.MODULE_SHUTTER: (
        (const.CONF_DS_T_IN, "Temperatura interior"),
        (const.CONF_DS_T_OUT, "Temperatura exterior"),
        (const.CONF_WIND, "Viento"),
    ),
}


# Recuperator probes exposed as first-class temperature sensors (F28).
_HRV_TEMPS: tuple[tuple[str, str, str], ...] = (
    ("supply", "HRV supply", const.CONF_HRV_SUPPLY),
    ("intake", "HRV intake", const.CONF_HRV_INTAKE),
    ("extract", "HRV extract", const.CONF_HRV_EXTRACT),
    ("exhaust", "HRV exhaust", const.CONF_HRV_EXHAUST),
)


# Display precision per mirrored role: concentrations are integers (a decimal of
# a µg/m³ or ppm is noise), temperatures and humidity keep one decimal. This also
# strips the float32 representation artifacts of the raw source (e.g. 1.20000004).
_MIRROR_PRECISION: dict[str, int] = {
    const.CONF_CO2: 0, const.CONF_PM25: 0, const.CONF_AQI: 0,
    const.CONF_VOC: 0, const.CONF_NOX: 0, const.CONF_DC_WIND: 0,
    const.CONF_WIND: 0,
}
_MIRROR_PRECISION_DEFAULT = 1   # temperatures, humidity, HRV probes

# Module tag prefixed to the mirror name, so all mirrors carry the Dynamic Home
# convention (DH-DV/DH-DS/DH-DC) and group/search cleanly. Single source of truth
# in const, shared with the primary-entity suffix.
_MIRROR_TAG = const.MODULE_TAG


def _mirror_sensors(entry: ConfigEntry, module: str) -> list[SensorEntity]:
    """F36: a stable mirror sensor per configured input role (opt-in)."""
    if not entry.options.get(const.CONF_EXPOSE_MIRRORS, False):
        return []
    tag = _MIRROR_TAG.get(module, "DH")
    out: list[SensorEntity] = []
    for role, name in _MIRROR_ROLES.get(module, ()):
        source = entry.data.get(role)
        if source:
            precision = _MIRROR_PRECISION.get(role, _MIRROR_PRECISION_DEFAULT)
            out.append(
                HwMirrorSensor(entry, role, f"{tag} {name}", source, precision))
    return out


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry,
                            async_add_entities: AddEntitiesCallback) -> None:
    coordinator = hass.data[const.DOMAIN][entry.entry_id]
    module = entry.data.get(const.CONF_MODULE)
    if module == const.MODULE_WEATHER:
        wx_ents: list[SensorEntity] = [WeatherSourceSensor(coordinator, entry)]
        # Per-field values (failover-backed). The raw-only ones (precip, storm /
        # precip probability) only appear when their raw source is configured.
        wx_ents += [WxValueSensor(coordinator, entry, d) for d in _WX_VALUES
                    if d.requires_conf is None or coordinator._hw(d.requires_conf)]
        wx_ents.append(WxConditionSensor(coordinator, entry))
        wx_ents.append(WxWindDirSensor(coordinator, entry))
        async_add_entities(wx_ents)
        return
    if module == const.MODULE_ZONES:
        async_add_entities([ZonesSensor(coordinator, entry),
                            ChangeoverSensor(coordinator, entry)])
        return
    if module == const.MODULE_ENERGY:
        ents: list[SensorEntity] = [HeadroomSensor(coordinator, entry),
                                    TariffSensor(coordinator, entry),
                                    HouseEnergySensor(coordinator, entry),
                                    HousePowerSensor(coordinator, entry)]
        if coordinator.has_pv():                    # F34 gating (⚠️ PV)
            ents.append(SurplusSensor(coordinator, entry))
        if coordinator._hw(const.CONF_ENERGY_PRICE):   # cost needs a price sensor
            ents.append(HouseCostSensor(coordinator, entry))
        async_add_entities(ents)
        return
    if module == const.MODULE_CLIMATE:
        ents: list[SensorEntity] = [DcSensor(coordinator, entry, d)
                                    for d in _DC_SENSORS]
        ents += [DcLearnSensor(coordinator, entry, d) for d in _DC_LEARN]
        if coordinator.has_water():
            ents += [DcSensor(coordinator, entry, d) for d in _DC_COND_SENSORS]
        if coordinator.has_mold():
            ents.append(MoldIndexSensor(coordinator, entry))
        if coordinator.has_adjacent():
            ents.append(AdjacentAdviceSensor(coordinator, entry))
        if coordinator.has_install():
            ents.append(InstallSensor(coordinator, entry))
        ents.append(BusSensor(coordinator, entry))
        ents.append(EnergySensor(coordinator, entry))
        ents.append(PowerSensor(coordinator, entry))
        ents.append(ScheduleSensor(coordinator, entry, is_vmc=False))
        ents.append(ReasonHumanSensor(coordinator, entry, const.MODULE_CLIMATE))
        ents += _mirror_sensors(entry, module)
        async_add_entities(ents)
        return
    if module == const.MODULE_SHUTTER:
        ds_ents: list[SensorEntity] = [
            BusSensor(coordinator, entry),
            EnergySensor(coordinator, entry),
            PowerSensor(coordinator, entry),
            *[DsEnergyWindowSensor(coordinator, entry, w)
              for w in _DS_ENERGY_WINDOWS],
            DsPositionSensor(coordinator, entry),
            DsTargetSensor(coordinator, entry),
            DsReasonSensor(coordinator, entry),
            ReasonHumanSensor(coordinator, entry, const.MODULE_SHUTTER),
            DsOverrideRemainingSensor(coordinator, entry),
            DsControlModeSensor(coordinator, entry),
            DsSunSensor(coordinator, entry)]
        # First-class context sensors, to read the "why" at a glance — each only
        # when its source is configured.
        if coordinator._hw(const.CONF_DS_T_IN):
            ds_ents.append(DsIndoorTempSensor(coordinator, entry))
        if coordinator._hw(const.CONF_DS_T_OUT):
            ds_ents.append(DsOutdoorTempSensor(coordinator, entry))
        if (coordinator._hw(const.CONF_DS_T_IN)
                and coordinator._hw(const.CONF_DS_T_OUT)):
            ds_ents.append(DsTempDiffSensor(coordinator, entry))
        if coordinator._hw(const.CONF_CLIMATE):
            ds_ents.append(DsClimateModeSensor(coordinator, entry))
            ds_ents.append(DsClimateSetpointSensor(coordinator, entry))
            ds_ents.append(DsClimateTempSensor(coordinator, entry))
        ds_ents.extend(_mirror_sensors(entry, module))
        # House-wide shutter counts: one shared set, owned by the first DS entry.
        # Every DS entry leaves its adder registered so, when the owning entry
        # unloads, another live one can ADOPT the shared sensors without a reload
        # (see adopt_shared_shutter_sensors).
        data = hass.data.setdefault(const.DOMAIN, {})
        data.setdefault("_ds_summary_adders", {})[entry.entry_id] = (
            async_add_entities, coordinator, entry)
        data.setdefault(const.DATA_DS_SUMMARY_OWNER, entry.entry_id)
        if data[const.DATA_DS_SUMMARY_OWNER] == entry.entry_id:
            ds_ents += _shared_shutter_sensors(coordinator, entry)
        async_add_entities(ds_ents)
        return
    entities: list[SensorEntity] = [HoursSensor(coordinator, entry, d)
                                    for d in _HOURS]
    if coordinator._hw(const.CONF_CO2):
        entities.append(Co2Sensor(coordinator, entry))
    if coordinator._hw(const.CONF_PM25):
        entities.append(Pm25Sensor(coordinator, entry))
    entities.append(SpeedSensor(coordinator, entry))
    entities.append(ReasonSensor(coordinator, entry))
    entities.append(ReasonHumanSensor(coordinator, entry, const.MODULE_VMC))
    entities.append(ModeSensor(coordinator, entry))
    entities.append(StateSensor(coordinator, entry))
    entities.append(OverrideRemainingSensor(coordinator, entry))
    entities.append(FilterLifeSensor(coordinator, entry))
    if coordinator.has_hrv():
        entities.append(HrvEfficiencySensor(coordinator, entry))
    for role, name, key in _HRV_TEMPS:
        if coordinator._hw(key):
            entities.append(HrvTempSensor(coordinator, entry, role, name))
    if coordinator._bathrooms():
        entities.append(ShowerRiseSensor(coordinator, entry))
    if coordinator.has_voc():
        entities.append(VocSensor(coordinator, entry))
    if coordinator.has_nox():
        entities.append(NoxSensor(coordinator, entry))
    if coordinator.has_dew_in():
        entities.append(DewPointSensor(coordinator, entry, _DEW_IN))
    if coordinator.has_dew_out():
        entities.append(DewPointSensor(coordinator, entry, _DEW_OUT))
    if coordinator.has_dew_in() and coordinator.has_dew_out():
        entities.append(DewPointSensor(coordinator, entry, _DEW_DIFF))
    entities.append(BusSensor(coordinator, entry))
    entities.append(EnergySensor(coordinator, entry))
    entities.append(PowerSensor(coordinator, entry))
    entities.append(ScheduleSensor(coordinator, entry, is_vmc=True))
    entities += _mirror_sensors(entry, module)
    async_add_entities(entities)


class ChangeoverSensor(CoordinatorEntity, SensorEntity):
    """Community changeover (F37): resolved water direction + manual/water_temp."""

    _attr_has_entity_name = True
    _attr_translation_key = "changeover"
    _attr_icon = "mdi:sun-snowflake-variant"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["heat", "cool", "off", "unknown"]
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_changeover_state"
        self._attr_device_info = DeviceInfo(
            identifiers={(const.DOMAIN, entry.entry_id)})

    @property
    def native_value(self) -> str:
        return self.coordinator.changeover or "unknown"

    @property
    def extra_state_attributes(self) -> dict:
        data = self.hass.data.get(const.DOMAIN, {}).get(const.DATA_CHANGEOVER) or {}
        return {"manual": self.coordinator.changeover_manual,
                "water_temp": data.get("water_temp")}


class HeadroomSensor(CoordinatorEntity, SensorEntity):
    """Import headroom (F34): watts left under the contracted power (ICP)."""

    _attr_has_entity_name = True
    _attr_translation_key = "headroom"
    _attr_icon = "mdi:transmission-tower"
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = "W"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_headroom"
        self._attr_device_info = DeviceInfo(
            identifiers={(const.DOMAIN, entry.entry_id)}, name=entry.title,
            manufacturer="Dynamic Home", model="Dynamic Energy")

    @property
    def native_value(self) -> float | None:
        return self.coordinator.context.get("import_headroom_w")

    @property
    def extra_state_attributes(self) -> dict:
        ctx = self.coordinator.context
        return {"contracted_w": ctx.get("contracted_w"),
                # No grid meter -> peak falls back to an N-loads count budget.
                "mode": "watts" if ctx.get("import_headroom_w") is not None
                else "n_loads"}


class TariffSensor(CoordinatorEntity, SensorEntity):
    """Tariff state (F34): cheap / normal / peak."""

    _attr_has_entity_name = True
    _attr_translation_key = "tariff"
    _attr_icon = "mdi:cash-clock"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["cheap", "normal", "peak"]

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_tariff"
        self._attr_device_info = DeviceInfo(
            identifiers={(const.DOMAIN, entry.entry_id)})

    @property
    def native_value(self) -> str | None:
        return self.coordinator.context.get("tariff_state")

    @property
    def extra_state_attributes(self) -> dict:
        return {"scarcity": self.coordinator.context.get("scarcity")}


class SurplusSensor(CoordinatorEntity, SensorEntity):
    """PV surplus (F34, ⚠️ gated on PV): production − consumption."""

    _attr_has_entity_name = True
    _attr_translation_key = "surplus"
    _attr_icon = "mdi:solar-power"
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = "W"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_surplus"
        self._attr_device_info = DeviceInfo(
            identifiers={(const.DOMAIN, entry.entry_id)})

    @property
    def native_value(self) -> float | None:
        return self.coordinator.context.get("surplus_w")


class HouseEnergySensor(CoordinatorEntity, RestoreSensor):
    """House energy total (F34 §8.2): sum of every module's kWh; Energy dashboard.

    Restored as a monotonic floor: right after a restart the modules haven't
    restored their own counters yet, so the live sum dips towards 0 — reported
    as-is, the Energy dashboard reads the dip as a meter reset and DOUBLES the
    consumption. The floor keeps the state monotonic through the restore window.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "house_energy"
    _attr_icon = "mdi:home-lightning-bolt"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_suggested_display_precision = 3

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_house_kwh"
        self._floor = 0.0
        self._attr_device_info = DeviceInfo(
            identifiers={(const.DOMAIN, entry.entry_id)})

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_sensor_data()
        if last is not None and last.native_value is not None:
            self._floor = float(last.native_value)

    @property
    def native_value(self) -> float:
        return round(max(self.coordinator.house_kwh, self._floor), 3)


class HouseCostSensor(CoordinatorEntity, RestoreSensor):
    """House gross cost (F34 §8.2, gated on a price sensor): accumulated €.

    Restored across restarts so the running cost keeps climbing.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "house_cost"
    _attr_icon = "mdi:cash"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_house_cost"
        self._attr_device_info = DeviceInfo(
            identifiers={(const.DOMAIN, entry.entry_id)})
        self._attr_native_unit_of_measurement = (
            coordinator.hass.config.currency or "EUR")

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_sensor_data()
        if last is not None and last.native_value is not None:
            self.coordinator.house_cost = float(last.native_value)

    @property
    def native_value(self) -> float:
        return round(self.coordinator.house_cost, 2)


class HousePowerSensor(CoordinatorEntity, SensorEntity):
    """House instantaneous power (F06/REQ-ENE-5): sum of every module's ``power_w``."""

    _attr_has_entity_name = True
    _attr_translation_key = "house_power"
    _attr_icon = "mdi:home-lightning-bolt-outline"
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "W"
    _attr_suggested_display_precision = 0

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_house_power"
        self._attr_device_info = DeviceInfo(
            identifiers={(const.DOMAIN, entry.entry_id)})

    @property
    def native_value(self) -> float:
        return round(self.coordinator.house_power_w, 1)


class ZonesSensor(CoordinatorEntity, SensorEntity):
    """Zone/group hierarchy (F24): zone count + a readable tree in attributes."""

    _attr_has_entity_name = True
    _attr_translation_key = "zones"
    _attr_icon = "mdi:home-group"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_zones"
        self._attr_device_info = DeviceInfo(
            identifiers={(const.DOMAIN, entry.entry_id)}, name=entry.title,
            manufacturer="Dynamic Home", model="Dynamic Home")

    def _titles(self) -> dict:
        return {e.entry_id: e.title
                for e in self.hass.config_entries.async_entries(const.DOMAIN)}

    @property
    def native_value(self) -> int:
        return len(self.coordinator.tree["zones"])

    @property
    def extra_state_attributes(self) -> dict:
        tree = self.coordinator.tree
        titles = self._titles()
        n_z, n_g, n_m = zones.counts(tree)
        readable = {
            z["name"]: [titles.get(m, m) for m in z["modules"]]
            for z in tree["zones"].values()
        }
        return {"groups": n_g, "assigned_modules": n_m,
                "zones": readable,
                "group_members": {g["name"]: list(g["zones"])
                                  for g in tree["groups"].values()}}


class WeatherSourceSensor(CoordinatorEntity, SensorEntity):
    """Active weather source (F33): which source is serving, and whether degraded."""

    _attr_has_entity_name = True
    _attr_translation_key = "weather_source"
    _attr_icon = "mdi:weather-partly-cloudy"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_wx_source"
        self._attr_device_info = DeviceInfo(
            identifiers={(const.DOMAIN, entry.entry_id)})

    @property
    def native_value(self) -> str:
        return self.coordinator.active_label

    @property
    def extra_state_attributes(self) -> dict:
        co = self.coordinator
        since = co.active_since
        return {"alert": co.alert_active,
                "since": dt_util.utc_from_timestamp(since).isoformat()
                if since else None}


class ReasonHumanSensor(CoordinatorEntity, SensorEntity):
    """Human-readable text of the decision reason (companion to ``Motivo``).

    Shows a phrase ("Refrigerando", "Apertura por amanecer"…) so a card can read
    the *why* with no templating. Its entity_id mirrors the Motivo sensor's with a
    ``_human`` suffix; the raw code stays available in the ``code`` attribute.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "reason_human"
    _attr_icon = "mdi:message-text-outline"

    def __init__(self, coordinator, entry: ConfigEntry, module: str) -> None:
        super().__init__(coordinator)
        self._module = module
        self._attr_unique_id = f"{entry.entry_id}_reason_human"
        self._attr_device_info = DeviceInfo(
            identifiers={(const.DOMAIN, entry.entry_id)})
        # Pin the entity_id to "<Motivo sensor>_human" so it sits right next to it,
        # whatever that sensor's (possibly legacy) object_id is. Falls back to a
        # predictable slug if the Motivo sensor isn't registered yet (first setup).
        from homeassistant.helpers import entity_registry as er
        base = er.async_get(coordinator.hass).async_get_entity_id(
            "sensor", const.DOMAIN, f"{entry.entry_id}_reason")
        self.entity_id = (f"{base}_human" if base
                          else f"sensor.{slugify(entry.title)}_motivo_human")

    def _code(self) -> str | None:
        d = self.coordinator.data
        return getattr(d, "reason", None) if d is not None else None

    @property
    def native_value(self) -> str | None:
        return reason_text.humanize(self._module, self._code())

    @property
    def extra_state_attributes(self) -> dict:
        return {"code": self._code()}


@dataclass(frozen=True)
class _WxValDesc:
    key: str                    # translation key + unique_id suffix
    field: str                  # WxData.values key
    icon: str
    device_class: SensorDeviceClass | None = None
    unit: str | None = None
    diagnostic: bool = False
    requires_conf: str | None = None   # only create when this raw source is set
    precision: int | None = None       # suggested display precision (0 = integer)


# Individual weather values resolved per-field from the configured providers
# (with failover), so they survive a provider going down and are directly usable
# in dashboards/automations. The "rich" extras land under Diagnostics.
_WX_VALUES: tuple[_WxValDesc, ...] = (
    _WxValDesc("wx_temperature", "temperature", "mdi:thermometer",
               SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS),
    _WxValDesc("wx_humidity", "humidity", "mdi:water-percent",
               SensorDeviceClass.HUMIDITY, PERCENTAGE),
    _WxValDesc("wx_pressure", "pressure", "mdi:gauge",
               SensorDeviceClass.ATMOSPHERIC_PRESSURE, UnitOfPressure.HPA),
    _WxValDesc("wx_wind", "wind", "mdi:weather-windy",
               SensorDeviceClass.WIND_SPEED, UnitOfSpeed.KILOMETERS_PER_HOUR),
    _WxValDesc("wx_wind_bearing", "wind_bearing", "mdi:compass", None, DEGREE),
    _WxValDesc("wx_precip", "precip", "mdi:weather-pouring",
               SensorDeviceClass.PRECIPITATION, UnitOfPrecipitationDepth.MILLIMETERS,
               requires_conf=const.CONF_WX_PRECIP),
    _WxValDesc("wx_gust", "gust", "mdi:weather-windy-variant",
               SensorDeviceClass.WIND_SPEED, UnitOfSpeed.KILOMETERS_PER_HOUR,
               diagnostic=True),
    _WxValDesc("wx_uv", "uv", "mdi:weather-sunny-alert", None, "UV Index",
               diagnostic=True, precision=0),
    _WxValDesc("wx_cloud", "cloud", "mdi:weather-cloudy", None, PERCENTAGE,
               diagnostic=True),
    _WxValDesc("wx_dewpoint", "dewpoint", "mdi:thermometer-water",
               SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS,
               diagnostic=True),
    _WxValDesc("wx_storm_prob", "storm_prob", "mdi:weather-lightning", None,
               PERCENTAGE, diagnostic=True, requires_conf=const.CONF_WX_STORM_PROB),
    _WxValDesc("wx_precip_prob", "precip_prob", "mdi:weather-rainy", None,
               PERCENTAGE, diagnostic=True, requires_conf=const.CONF_WX_PRECIP_PROB),
)


class WxValueSensor(CoordinatorEntity, SensorEntity):
    """A single weather value, resolved per-field across providers (failover)."""

    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry: ConfigEntry, desc: _WxValDesc) -> None:
        super().__init__(coordinator)
        self._desc = desc
        if desc.field == "wind_bearing":
            # A 0/360 angle has no meaningful statistical mean: MEASUREMENT
            # would make the long-term stats average N (350°) with N (10°) to E.
            self._attr_state_class = None
        self._attr_translation_key = desc.key
        self._attr_icon = desc.icon
        self._attr_device_class = desc.device_class
        self._attr_native_unit_of_measurement = desc.unit
        if desc.precision is not None:
            self._attr_suggested_display_precision = desc.precision
        self._attr_unique_id = f"{entry.entry_id}_{desc.key}"
        if desc.diagnostic:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_device_info = DeviceInfo(
            identifiers={(const.DOMAIN, entry.entry_id)})

    @property
    def native_value(self) -> float | None:
        d = self.coordinator.data
        return d.values.get(self._desc.field) if d else None

    @property
    def available(self) -> bool:
        return self.native_value is not None

    @property
    def extra_state_attributes(self) -> dict:
        d = self.coordinator.data
        return {"source": d.sources.get(self._desc.field) if d else None}


# Standard Home Assistant weather-condition vocabulary (matches what a weather.*
# entity — e.g. Google Weather — reports as its state).
_WX_CONDITIONS = [
    "clear-night", "cloudy", "exceptional", "fog", "hail", "lightning",
    "lightning-rainy", "partlycloudy", "pouring", "rainy", "snowy",
    "snowy-rainy", "sunny", "windy", "windy-variant",
]


class WxConditionSensor(CoordinatorEntity, SensorEntity):
    """Outdoor weather condition (failover-backed), mirroring a weather.* state.

    The DW equivalent of a provider's condition sensor (e.g. Google Weather's
    ``*_condicion_meteorologica``): its state is the condition of the active
    weather source, so it survives a provider failover. Reusable anywhere,
    including the DS weather-alert slots.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "wx_condition"
    _attr_icon = "mdi:weather-partly-cloudy"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = _WX_CONDITIONS

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_wx_condition"
        self._attr_device_info = DeviceInfo(
            identifiers={(const.DOMAIN, entry.entry_id)})

    @property
    def native_value(self) -> str | None:
        d = self.coordinator.data
        cond = d.condition if d else None
        return cond if cond in _WX_CONDITIONS else None

    @property
    def available(self) -> bool:
        return self.native_value is not None

    @property
    def extra_state_attributes(self) -> dict:
        d = self.coordinator.data
        return {"source": d.active_entity if d else None}


# 8-point compass. Lowercase keys are the stable internal states (hassfest requires
# [a-z0-9-_] translation keys); the translations localise them to display form
# (en: n->N, sw->SW…; es: sw->SO, w->O, nw->NO).
_WX_WIND_DIRS = ["n", "ne", "e", "se", "s", "sw", "w", "nw"]


class WxWindDirSensor(CoordinatorEntity, SensorEntity):
    """Wind bearing as a readable compass point (companion to the degrees sensor).

    Converts the resolved ``wind_bearing`` (degrees) into an 8-point cardinal
    direction; the raw degrees ride along in the ``degrees`` attribute.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "wx_wind_dir"
    _attr_icon = "mdi:compass-outline"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = _WX_WIND_DIRS
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_wx_wind_dir"
        self._attr_device_info = DeviceInfo(
            identifiers={(const.DOMAIN, entry.entry_id)})

    def _bearing(self) -> float | None:
        d = self.coordinator.data
        return d.values.get("wind_bearing") if d else None

    @property
    def native_value(self) -> str | None:
        deg = self._bearing()
        if deg is None:
            return None
        return _WX_WIND_DIRS[int((deg + 22.5) // 45) % 8]

    @property
    def available(self) -> bool:
        return self._bearing() is not None

    @property
    def extra_state_attributes(self) -> dict:
        return {"degrees": self._bearing()}


class HwMirrorSensor(SensorEntity):
    """F36: republishes a configured source entity under a stable id.

    Dashboards/automations reference this entity instead of the raw hardware
    entity_id, so replacing a physical sensor only means reconfiguring the entry
    (the mirror's unique_id, keyed by entry+role, never changes). Copies the
    source's value, unit, device_class and state_class.
    """

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, entry: ConfigEntry, role: str, name: str,
                 source: str, precision: int | None = None) -> None:
        self._source = source
        self._precision = precision
        self._attr_name = f"{name} (espejo)"
        self._attr_unique_id = f"{entry.entry_id}_mirror_{role}"
        if precision is not None:
            self._attr_suggested_display_precision = precision
        self._attr_device_info = DeviceInfo(
            identifiers={(const.DOMAIN, entry.entry_id)})

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(async_track_state_change_event(
            self.hass, [self._source], self._source_changed))

    @callback
    def _source_changed(self, event) -> None:
        self.async_write_ha_state()

    def _state(self):
        return self.hass.states.get(self._source)

    @property
    def available(self) -> bool:
        st = self._state()
        return st is not None and st.state not in (
            "unknown", "unavailable", "none", "")

    @property
    def native_value(self):
        st = self._state()
        if st is None:
            return None
        try:
            val = float(st.state)
        except (TypeError, ValueError):
            return st.state
        # Round to the role precision: kills float32 noise (1.20000004 -> 1.2)
        # and drops meaningless decimals on concentrations.
        return val if self._precision is None else round(val, self._precision)

    @property
    def native_unit_of_measurement(self):
        st = self._state()
        return st.attributes.get("unit_of_measurement") if st else None

    @property
    def device_class(self):
        st = self._state()
        raw = st.attributes.get("device_class") if st else None
        try:
            return SensorDeviceClass(raw) if raw else None
        except ValueError:
            return None

    @property
    def state_class(self):
        st = self._state()
        raw = st.attributes.get("state_class") if st else None
        try:
            return SensorStateClass(raw) if raw else None
        except ValueError:
            return None


class BusSensor(CoordinatorEntity, SensorEntity):
    """Winning SDHB bus intent for this consumer.

    Every module's bus sensor is grouped under one shared "Dynamic Home Bus"
    device (via a fixed identifier, not the per-entry one) so the whole bus is
    observable from a single place in the UI. The state is the winning intent;
    the attributes explain *why* (source, priority, candidate count).
    """

    _attr_has_entity_name = True
    _attr_icon = "mdi:transit-connection-variant"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_bus"
        self._attr_name = entry.title
        self._attr_device_info = DeviceInfo(
            identifiers={(const.DOMAIN, const.BUS_DEVICE_ID)},
            name="Dynamic Home · Bus")

    @property
    def native_value(self) -> str | None:
        return self.coordinator.bus_explain.get("winner")

    @property
    def extra_state_attributes(self) -> dict:
        ex = self.coordinator.bus_explain
        ttl = ex.get("ttl_remaining")
        return {"source": ex.get("source"), "priority": ex.get("priority"),
                "candidates": ex.get("candidates"), "reason": ex.get("reason"),
                "target": ex.get("target") or "(broadcast)",
                "ttl_remaining_s": round(ttl) if ttl is not None else None,
                "runner_up": ex.get("runner_up"),
                "runner_up_priority": ex.get("runner_up_priority")}


# House-wide shutter counts: each predicate buckets a cover's current position.
_DS_COVER_COUNTS = (
    ("covers_open", "mdi:window-open", lambda p: p == 100),
    ("covers_closed", "mdi:window-closed", lambda p: p == 0),
    ("covers_ajar", "mdi:window-shutter", lambda p: p is not None and 0 < p < 100),
)


class DsCoverCountSensor(CoordinatorEntity, SensorEntity):
    """How many DS-managed covers are open / closed / ajar (house-wide).

    Counts only the shutters this integration manages — not the raw physical
    covers — so it never double-counts. One shared set of sensors under the
    "Dynamic Home · Persianas" device, owned by the first DS entry; refreshes
    whenever that entry's coordinator ticks.
    """

    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry: ConfigEntry, key: str, icon: str,
                 pred) -> None:
        super().__init__(coordinator)
        self._pred = pred
        self._attr_translation_key = key
        self._attr_icon = icon
        self._attr_unique_id = f"{const.DOMAIN}_{key}"      # global (single set)
        self._attr_device_info = DeviceInfo(
            identifiers={(const.DOMAIN, const.SHUTTERS_DEVICE_ID)},
            name="Dynamic Home · Persianas")
        self._unsub_covers = None

    def _ds_coordinators(self):
        from .coordinator import DsCoordinator
        return [co for co in self.hass.data.get(const.DOMAIN, {}).values()
                if isinstance(co, DsCoordinator)]

    def _cover_eids(self) -> list[str]:
        return [e for e in (co._hw(const.CONF_COVER)
                            for co in self._ds_coordinators()) if e]

    def _positions(self):
        return [co._current_pos() for co in self._ds_coordinators()]

    @callback
    def _track_covers(self) -> None:
        """(Re)subscribe to the managed covers' state so the counts are live even
        when a sibling shutter (not the owner) moves or is added later."""
        if self._unsub_covers is not None:
            self._unsub_covers()
        eids = self._cover_eids()
        self._unsub_covers = (async_track_state_change_event(
            self.hass, eids, self._cover_changed) if eids else None)

    @callback
    def _cover_changed(self, event) -> None:
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._track_covers()
        self.async_on_remove(
            lambda: self._unsub_covers() if self._unsub_covers else None)

    @callback
    def _handle_coordinator_update(self) -> None:
        # The owner ticked: siblings may have appeared/gone -> re-arm tracking.
        self._track_covers()
        super()._handle_coordinator_update()

    @property
    def native_value(self) -> int:
        return sum(1 for p in self._positions() if self._pred(p))

    @property
    def extra_state_attributes(self) -> dict:
        return {"total": len(self._positions())}


class _SharedSunSensor(SensorEntity):
    """Base for the house-wide sun sensors on the shared 'Persianas' device.

    Reads the native ``sun.sun`` entity (global, same for every shutter) and
    refreshes whenever it updates. Created once, alongside the shutter counts.
    """

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, key: str) -> None:
        self._attr_translation_key = key
        self._attr_unique_id = f"{const.DOMAIN}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(const.DOMAIN, const.SHUTTERS_DEVICE_ID)},
            name="Dynamic Home · Persianas")

    def _sun(self):
        return self.hass.states.get("sun.sun")

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(async_track_state_change_event(
            self.hass, ["sun.sun"], self._sun_changed))

    @callback
    def _sun_changed(self, event) -> None:
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        return self._sun() is not None


class DsSunDayNightSensor(_SharedSunSensor):
    """Day or night (from the sun being above/below the horizon)."""

    _attr_icon = "mdi:theme-light-dark"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["day", "night"]

    def __init__(self) -> None:
        super().__init__("sun_day_night")

    @property
    def native_value(self) -> str | None:
        st = self._sun()
        return None if st is None else (
            "day" if st.state == "above_horizon" else "night")


class DsSunElevationSensor(_SharedSunSensor):
    """Sun elevation above the horizon (degrees)."""

    _attr_icon = "mdi:angle-acute"
    _attr_native_unit_of_measurement = "°"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1

    def __init__(self) -> None:
        super().__init__("sun_elevation")

    @property
    def native_value(self) -> float | None:
        st = self._sun()
        return st.attributes.get("elevation") if st else None


class DsSunAzimuthSensor(_SharedSunSensor):
    """Sun azimuth / compass bearing (degrees)."""

    _attr_icon = "mdi:compass"
    _attr_native_unit_of_measurement = "°"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1

    def __init__(self) -> None:
        super().__init__("sun_azimuth")

    @property
    def native_value(self) -> float | None:
        st = self._sun()
        return st.attributes.get("azimuth") if st else None


class _SunWindowSensor(_SharedSunSensor):
    """A sun transition window as a readable ``De HH:MM a HH:MM`` range."""

    _start_attr = ""
    _end_attr = ""

    def _edges(self):
        st = self._sun()
        if st is None:
            return None, None
        s = dt_util.parse_datetime(st.attributes.get(self._start_attr) or "")
        e = dt_util.parse_datetime(st.attributes.get(self._end_attr) or "")
        if s is not None and e is not None and s > e:
            # Mid-window (e.g. between dawn and sunrise) the start already
            # points to tomorrow while the end is still today's: show the
            # coherent same-day pair instead of a crossed range.
            from datetime import timedelta as _td
            s = s - _td(days=1)
        return s, e

    @property
    def native_value(self) -> str | None:
        s, e = self._edges()
        if s is None or e is None:
            return None
        return (f"De {dt_util.as_local(s):%H:%M} "
                f"a {dt_util.as_local(e):%H:%M}")

    @property
    def extra_state_attributes(self) -> dict:
        s, e = self._edges()
        return {"start": dt_util.as_local(s).isoformat() if s else None,
                "end": dt_util.as_local(e).isoformat() if e else None}


class DsSunriseSensor(_SunWindowSensor):
    """Next sunrise window: from first light (dawn) to fully risen."""

    _attr_icon = "mdi:weather-sunset-up"
    _start_attr = "next_dawn"
    _end_attr = "next_rising"

    def __init__(self) -> None:
        super().__init__("sunrise")


class DsSunsetSensor(_SunWindowSensor):
    """Next sunset window: from starting to set (sunset) to fully hidden (dusk)."""

    _attr_icon = "mdi:weather-sunset-down"
    _start_attr = "next_setting"
    _end_attr = "next_dusk"

    def __init__(self) -> None:
        super().__init__("sunset")


_DS_SHARED_SUN = (DsSunDayNightSensor, DsSunElevationSensor, DsSunAzimuthSensor,
                  DsSunriseSensor, DsSunsetSensor)


class _Base(CoordinatorEntity[DvCoordinator], SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator: DvCoordinator, entry: ConfigEntry,
                 key: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(const.DOMAIN, entry.entry_id)})


class HoursSensor(_Base, RestoreSensor):
    """Cumulative running-hours counter, restored across restarts."""

    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfTime.HOURS
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator: DvCoordinator, entry: ConfigEntry,
                 desc: _HoursDesc) -> None:
        super().__init__(coordinator, entry, desc.key)
        self._desc = desc
        self._attr_translation_key = desc.key
        self._attr_icon = desc.icon

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_sensor_data()
        if last is not None and last.native_value is not None:
            self._desc.setter(self.coordinator, float(last.native_value))

    @property
    def native_value(self) -> float:
        return round(self._desc.getter(self.coordinator), 3)


class EnergySensor(_Base, RestoreSensor):
    """Cumulative energy (F06), real or estimated; feeds the Energy dashboard.

    Shared by the VMC/DC/DS coordinators (all expose ``energy_kwh``). Restored
    across restarts so the total keeps climbing.
    """

    _attr_translation_key = "energy"
    _attr_icon = "mdi:lightning-bolt"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_suggested_display_precision = 3

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "energy")

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_sensor_data()
        if last is not None and last.native_value is not None:
            restored = float(last.native_value)
            self.coordinator.energy_kwh = restored
            # Tell the house aggregator this jump is a restore, not consumption
            # (it would otherwise bill the restored kWh as a phantom cost).
            self.coordinator.energy_kwh_restored = True
            # DS keeps a rolling history for the 24h/30d windows; reseed it at
            # the restored total, or those windows would show the WHOLE history
            # as "consumed in the last 24 h" after every restart.
            hist = getattr(self.coordinator, "_energy_hist", None)
            if hist is not None:
                hist.clear()
                hist.append((dt_util.utcnow().timestamp(), restored))

    @property
    def native_value(self) -> float:
        return round(self.coordinator.energy_kwh, 3)


class PowerSensor(_Base):
    """Instantaneous power (F06/REQ-ENE-5), real or estimated; per module.

    Shared by the VMC/DC coordinators (both expose ``power_w``: the watts feeding
    the kWh integral — a real meter if configured, else the per-state estimate).
    """

    _attr_translation_key = "power"
    _attr_icon = "mdi:flash"
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "W"
    _attr_suggested_display_precision = 0

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "power")

    @property
    def native_value(self) -> float:
        return round(self.coordinator.power_w, 1)


@dataclass(frozen=True)
class _EnergyWindow:
    key: str            # translation key + unique_id suffix
    seconds: float      # rolling window length
    icon: str


_DS_ENERGY_WINDOWS: tuple[_EnergyWindow, ...] = (
    _EnergyWindow("energy_24h", 86400.0, "mdi:lightning-bolt-outline"),
    _EnergyWindow("energy_30d", 30 * 86400.0, "mdi:calendar-month-outline"),
)


class DsEnergyWindowSensor(_Base):
    """Energy consumed by the shutter motor over a rolling window (24 h / 30 d).

    Complements the cumulative ``Energy`` total: a bounded figure that goes up and
    down, so no ``state_class`` (it is not a monotonic meter). Rebuilds after a
    restart as the in-memory history refills.
    """

    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_suggested_display_precision = 3
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry: ConfigEntry,
                 win: _EnergyWindow) -> None:
        super().__init__(coordinator, entry, win.key)
        self._win = win
        self._attr_translation_key = win.key
        self._attr_icon = win.icon

    @property
    def native_value(self) -> float:
        return round(self.coordinator.energy_window_kwh(self._win.seconds), 3)


class DsPositionSensor(_Base):
    """Real shutter position (% open) read back from the cover (diagnostic).

    The managed cover already shows the physical position, but as a cover it is
    not a graphable numeric sensor. This re-publishes the cover's
    ``current_position`` as a plain ``%`` sensor (history/statistics friendly,
    easy to template against), with the commanded ``target`` and the ``reason``
    as attributes — so a glance shows what the shutter *is* vs what the system
    *wants* and why. ``unknown`` when the cover reports no position feedback.
    """

    _attr_translation_key = "position"
    _attr_icon = "mdi:window-shutter"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "position")

    @property
    def native_value(self) -> int | None:
        return self.coordinator._current_pos()

    @property
    def extra_state_attributes(self) -> dict:
        data = self.coordinator.data
        return {"target": getattr(data, "pos", None),
                "reason": getattr(data, "reason", None)}


class DsTargetSensor(_Base):
    """Commanded target position (the % the cascade wants).

    The key signal in observe-only, where the real cover never moves: this is
    "what it would have done". The reason and the decision details (impact,
    penetration, indoor/outdoor temps...) ride along as attributes.
    """

    _attr_translation_key = "target_position"
    _attr_icon = "mdi:window-shutter-cog"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "target")

    @property
    def native_value(self) -> int | None:
        data = self.coordinator.data
        return data.pos if data else None

    @property
    def extra_state_attributes(self) -> dict:
        data = self.coordinator.data
        attrs = {"reason": getattr(data, "reason", None),
                 "peak_reason": self.coordinator.peak_reason,
                 "alert_source": self.coordinator.alert_source}
        if data:
            attrs.update(data.details)
        return attrs


class DsReasonSensor(_Base):
    """Why the shutter is where it is (the winning cascade branch).

    Graphable as a state, so in observe-only you can follow *why* across the day
    (rain, summer_solar_shield, winter_cold_shield, meteo_alert...) and validate
    the logic before letting it drive the hardware.
    """

    _attr_translation_key = "reason"
    _attr_icon = "mdi:information-outline"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "reason")

    @property
    def native_value(self) -> str | None:
        data = self.coordinator.data
        return data.reason if data else None

    @property
    def extra_state_attributes(self) -> dict:
        data = self.coordinator.data
        return dict(data.details) if data else {}


class DsOverrideRemainingSensor(_Base):
    """Minutes left on the shutter's manual hold before it resumes auto (0 if none)."""

    _attr_translation_key = "override_remaining"
    _attr_icon = "mdi:timer-sand"
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "override_remaining")

    @property
    def native_value(self) -> float:
        return self.coordinator.override_remaining_min

    @property
    def extra_state_attributes(self) -> dict:
        return {"held_position": self.coordinator.manual_pos}


class DsIndoorTempSensor(_Base):
    """Indoor temperature this shutter uses for its decisions (first-class)."""

    _attr_translation_key = "ds_indoor_temp"
    _attr_icon = "mdi:home-thermometer"
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "ds_indoor_temp")

    @property
    def native_value(self) -> float | None:
        return self.coordinator._num(const.CONF_DS_T_IN)


class DsOutdoorTempSensor(_Base):
    """Outdoor temperature this shutter uses for its decisions (first-class)."""

    _attr_translation_key = "ds_outdoor_temp"
    _attr_icon = "mdi:sun-thermometer"
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "ds_outdoor_temp")

    @property
    def native_value(self) -> float | None:
        return self.coordinator._num(const.CONF_DS_T_OUT)


class DsTempDiffSensor(_Base):
    """Indoor−outdoor temperature differential for this shutter's room.

    ``t_in − t_out`` (e.g. living room vs street/terrace): at a glance a small
    delta hints the window/shutter is open (the room tracks outside), a large one
    that it is closed and insulating. Only created when both temperatures are set.
    """

    _attr_translation_key = "ds_temp_diff"
    _attr_icon = "mdi:thermometer-lines"
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "ds_temp_diff")

    @property
    def native_value(self) -> float | None:
        t_in = self.coordinator._num(const.CONF_DS_T_IN)
        t_out = self.coordinator._num(const.CONF_DS_T_OUT)
        if t_in is None or t_out is None:
            return None
        return round(t_in - t_out, 1)

    @property
    def extra_state_attributes(self) -> dict:
        return {"indoor": self.coordinator._num(const.CONF_DS_T_IN),
                "outdoor": self.coordinator._num(const.CONF_DS_T_OUT)}


class DsControlModeSensor(_Base, RestoreEntity):
    """Whether the shutter runs on DS automation or is held by a manual override.

    ``auto`` = the cascade drives it; ``manual`` = a hand/external command armed a
    hold (press "Resume auto" to cancel it). The reason and the remaining hold time
    ride along as attributes. The hold itself is restored across a Home Assistant
    restart from this sensor's last state — an update mid-hold must not silently
    hand the shutter back to the automation (trap safety).
    """

    _attr_translation_key = "ds_control_mode"
    _attr_icon = "mdi:hand-back-right"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["auto", "manual"]

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "ds_control_mode")

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is None or self.coordinator.manual_pos is not None:
            return
        pos = last.attributes.get("held_position")
        until = last.attributes.get("hold_until_ts")
        if pos is None or until is None:
            return
        until_f = float("inf") if until == "inf" else float(until)
        if until_f > dt_util.utcnow().timestamp():
            self.coordinator.manual_pos = max(0, min(100, int(pos)))
            self.coordinator.manual_until = until_f
            self.hass.async_create_task(self.coordinator.async_request_refresh())

    @property
    def native_value(self) -> str:
        return "manual" if self.coordinator.manual_pos is not None else "auto"

    @property
    def extra_state_attributes(self) -> dict:
        co = self.coordinator
        # hold_until_ts is a str/float (never math.inf — attributes are JSON).
        if co.manual_pos is None:
            until = None
        elif co.manual_until == float("inf"):
            until = "inf"
        else:
            until = round(co.manual_until, 1)
        return {"held_position": co.manual_pos,
                "remaining_min": co.override_remaining_min,
                "hold_until_ts": until,
                "reason": getattr(co.data, "reason", None)}


class DsSunSensor(_Base):
    """Whether the sun strikes this shutter's facade: "Persiana al Sol" / "…​ a la
    Sombra". The generic sun data (day/night, elevation, azimuth) lives in its own
    sensors on the shared "Dynamic Home · Persianas" device, so this one only
    flips when the shading actually changes (no minute-by-minute history churn).
    """

    _attr_translation_key = "ds_sun"
    _attr_icon = "mdi:sun-angle"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "ds_sun")

    @property
    def native_value(self) -> str:
        return ("Persiana al Sol" if self.coordinator.sun_impact > 0
                else "Persiana a la Sombra")

    @property
    def extra_state_attributes(self) -> dict:
        co = self.coordinator
        return {"in_sun": co.sun_impact > 0, "impact": round(co.sun_impact)}


class DsClimateModeSensor(_Base):
    """Mode of the zone's linked climate (heat/cool/off) — gates the whole cascade."""

    _attr_translation_key = "ds_climate_mode"
    _attr_icon = "mdi:thermostat"

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "ds_climate_mode")

    @property
    def native_value(self) -> str | None:
        return self.coordinator.climate_mode


class DsClimateSetpointSensor(_Base):
    """Target temperature set on the zone's linked climate (first-class)."""

    _attr_translation_key = "ds_climate_setpoint"
    _attr_icon = "mdi:thermostat-box"
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "ds_climate_setpoint")

    @property
    def native_value(self) -> float | None:
        return self.coordinator.climate_setpoint


class DsClimateTempSensor(_Base):
    """Current temperature reported by the zone's linked climate (first-class)."""

    _attr_translation_key = "ds_climate_temp"
    _attr_icon = "mdi:thermometer"
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "ds_climate_temp")

    @property
    def native_value(self) -> float | None:
        return self.coordinator.climate_temp


class ScheduleSensor(CoordinatorEntity, SensorEntity):
    """Weekly scheduler (F21): the active slot's value + next change (diagnostic).

    Shared by VMC (speed) and DC (base setpoint). State is ``off`` when the
    program is disabled and ``—`` when enabled but no slot applies.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "schedule"
    _attr_icon = "mdi:calendar-clock"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry: ConfigEntry, is_vmc: bool) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._is_vmc = is_vmc
        self._attr_unique_id = f"{entry.entry_id}_schedule"
        self._attr_device_info = DeviceInfo(
            identifiers={(const.DOMAIN, entry.entry_id)})

    def _now(self):
        n = dt_util.now()
        return n.weekday(), n.hour * 60 + n.minute

    @property
    def native_value(self):
        if not self.coordinator.schedule_enabled:
            return "off"
        wd, m = self._now()
        v = schedule.active_value(self._entry.options.get(const.CONF_SCHEDULE),
                                  wd, m)
        if v is None:
            return "—"
        if self._is_vmc:
            return "Off" if int(v) == 0 else f"V{int(v)}"
        return v

    @property
    def extra_state_attributes(self) -> dict:
        wd, m = self._now()
        prof = self._entry.options.get(const.CONF_SCHEDULE)
        return {"enabled": self.coordinator.schedule_enabled,
                "next_change": schedule.next_change(prof, wd, m)}


class SpeedSensor(_Base):
    _attr_translation_key = "speed"
    _attr_icon = "mdi:fan"

    def __init__(self, coordinator: DvCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "speed")

    @property
    def native_value(self) -> int:
        return self.coordinator.current_speed


@dataclass(frozen=True)
class _DewDesc:
    key: str
    getter: Callable
    device_class: SensorDeviceClass | None
    icon: str


# Dew points expose the dry-mode (F13) gate: drying ventilates effectively when
# the Δ (dp_in - dp_out) clears the drying margin (outside air is drier).
_DEW_IN = _DewDesc("dew_point_in", lambda c: c.dew_point_in,
                   SensorDeviceClass.TEMPERATURE, "mdi:water-thermometer")
_DEW_OUT = _DewDesc("dew_point_out", lambda c: c.dew_point_out,
                    SensorDeviceClass.TEMPERATURE, "mdi:water-thermometer-outline")
# The Δ is a temperature spread, not an absolute temperature -> no device_class.
_DEW_DIFF = _DewDesc("dew_point_diff", lambda c: c.dew_point_diff,
                     None, "mdi:delta")


class DewPointSensor(_Base):
    """Dew point (°C) indoors/outdoors, and their spread, for the F13 gate."""

    _attr_native_unit_of_measurement = "°C"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: DvCoordinator, entry: ConfigEntry,
                 desc: _DewDesc) -> None:
        super().__init__(coordinator, entry, desc.key)
        self._desc = desc
        self._attr_translation_key = desc.key
        self._attr_icon = desc.icon
        if desc.device_class is not None:
            self._attr_device_class = desc.device_class

    @property
    def native_value(self) -> float | None:
        return self._desc.getter(self.coordinator)


class ReasonSensor(_Base):
    _attr_translation_key = "reason"
    _attr_icon = "mdi:information-outline"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: DvCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "reason")

    @property
    def native_value(self) -> str | None:
        data = self.coordinator.data
        return data.reason if data else None

    @property
    def extra_state_attributes(self) -> dict:
        # The live IAQ drivers next to the thresholds actually in use (adaptive or
        # fixed), plus the shower trigger and the dry-mode margin — so you can see
        # *why* the speed is what it is and whether a threshold is mis-tuned.
        return dict(self.coordinator.iaq_snapshot)


class HrvTempSensor(_Base):
    """One recuperator probe as a first-class temperature sensor (F28).

    Supply (insuflación), intake (admisión), extract (extracción) and exhaust
    (expulsión) — graphable individually instead of only as efficiency-sensor
    attributes.
    """

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1
    _attr_icon = "mdi:thermometer"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry: ConfigEntry, role: str,
                 name: str) -> None:
        super().__init__(coordinator, entry, f"hrv_{role}")
        self._role = role
        self._attr_translation_key = f"hrv_{role}"

    @property
    def native_value(self) -> float | None:
        return self.coordinator.hrv_temperatures.get(self._role)


class ShowerRiseSensor(_Base):
    """Live shower trigger: the bathroom RH rise over its own baseline (F13).

    The shower boost fires when this rise reaches ``trigger_on``. A steady level
    reads ~0 (no false boost); a shower spikes it. The ``effective`` attribute
    shows whether expelling helps (outside drier).
    """

    _attr_translation_key = "shower_rise"
    _attr_icon = "mdi:shower"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "shower_rise")

    @property
    def native_value(self) -> float | None:
        return self.coordinator.shower_rise

    @property
    def extra_state_attributes(self) -> dict:
        s = self.coordinator.iaq_snapshot
        return {"trigger_on": s.get("shower_on"),
                "trigger_off": s.get("shower_off"),
                "bathroom": s.get("shower_bathroom"),
                "effective": s.get("shower_effective"),
                "enabled": s.get("shower_enabled"),
                "needs": "bathroom humidity (+ outdoor for the expel gate)"}


class ModeSensor(_Base):
    _attr_translation_key = "mode"
    _attr_icon = "mdi:fan-auto"

    def __init__(self, coordinator: DvCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "mode")

    @property
    def native_value(self) -> str:
        return self.coordinator.preset


class StateSensor(_Base):
    """Operational state: boot (not evaluated) / grace (startup) / active."""

    _attr_translation_key = "op_state"
    _attr_icon = "mdi:state-machine"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: DvCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "state")

    @property
    def native_value(self) -> str:
        if self.coordinator.data is None:
            return "boot"
        if self.coordinator.in_grace:
            return "grace"
        if self.coordinator.preset == "off":
            return "off"
        return "manual" if self.coordinator.preset != "auto" else "active"


class OverrideRemainingSensor(_Base):
    """Minutes left before a manual override auto-reverts to auto (0 if none)."""

    _attr_translation_key = "override_remaining"
    _attr_icon = "mdi:timer-sand"
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: DvCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "override_remaining")

    @property
    def native_value(self) -> int:
        until = self.coordinator.override_until
        if not until:
            return 0
        remaining = until - dt_util.utcnow().timestamp()
        return max(0, round(remaining / 60))


class FilterLifeSensor(_Base):
    """Remaining filter life as a percentage (100 % = fresh, 0 % = due)."""

    _attr_translation_key = "filter_life"
    _attr_icon = "mdi:air-filter"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator: DvCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "filter_life")

    @property
    def native_value(self) -> float:
        return round(self.coordinator.filter_life_pct, 1)


class HrvEfficiencySensor(_Base):
    """Heat-recovery efficiency (%) with a recovering/bypass/idle state attribute."""

    _attr_translation_key = "hrv_efficiency"
    _attr_icon = "mdi:heat-wave"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator: DvCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "hrv_efficiency")

    @property
    def native_value(self) -> float | None:
        return self.coordinator.hrv_efficiency_pct

    @property
    def extra_state_attributes(self) -> dict:
        # Expose all configured recuperator temperatures alongside η + state.
        return {"state": self.coordinator.hrv_state,
                **self.coordinator.hrv_temperatures}


class VocSensor(_Base):
    """Observed VOC level (F30). Informational only — it never drives the speed."""

    _attr_translation_key = "voc"
    _attr_icon = "mdi:molecule"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: DvCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "voc")

    @property
    def native_value(self) -> float | None:
        return self.coordinator.voc_level


class NoxSensor(_Base):
    """Observed NOx index (Sensirion). Informational only — never drives speed.

    A relative index (~100 nominal, no unit), like the VOC index.
    """

    _attr_translation_key = "nox"
    _attr_icon = "mdi:molecule"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: DvCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "nox")

    @property
    def native_value(self) -> float | None:
        return self.coordinator.nox_level


class Co2Sensor(_Base):
    """Live CO₂ as a first-class sensor (the VMC's required input, re-exposed)."""

    _attr_translation_key = "co2"
    _attr_device_class = SensorDeviceClass.CO2
    _attr_native_unit_of_measurement = CONCENTRATION_PARTS_PER_MILLION
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0

    def __init__(self, coordinator: DvCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "co2")

    @property
    def native_value(self) -> float | None:
        return self.coordinator._num(const.CONF_CO2)


class Pm25Sensor(_Base):
    """Live PM2.5 as a first-class sensor (the VMC's required input, re-exposed)."""

    _attr_translation_key = "pm25"
    _attr_device_class = SensorDeviceClass.PM25
    _attr_native_unit_of_measurement = CONCENTRATION_MICROGRAMS_PER_CUBIC_METER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0

    def __init__(self, coordinator: DvCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "pm25")

    @property
    def native_value(self) -> float | None:
        return self.coordinator._num(const.CONF_PM25)


# --------------------------------------------------------------------------- #
# DC (climate) diagnostic sensors — expose the pipeline for dashboards
# --------------------------------------------------------------------------- #
from homeassistant.const import UnitOfTemperature  # noqa: E402

from .coordinator import DcCoordinator  # noqa: E402


@dataclass(frozen=True)
class _DcDesc:
    key: str
    name: str
    icon: str
    getter: Callable[[DcCoordinator], object]
    unit: str | None = None
    diagnostic: bool = False
    attrs: Callable[[DcCoordinator], dict] | None = None


def _detail(co: DcCoordinator, k: str):
    d = co.data
    return d.details.get(k) if d else None


_DC_SENSORS: tuple[_DcDesc, ...] = (
    _DcDesc("target", "Target", "mdi:thermometer-check",
            lambda c: c.data.target if c.data else None,
            UnitOfTemperature.CELSIUS,
            attrs=lambda c: dict(c.data.details) if c.data else {}),
    _DcDesc("base", "Base activa", "mdi:home-thermometer",
            lambda c: _detail(c, "base"), UnitOfTemperature.CELSIUS),
    _DcDesc("target_raw", "Target RAW", "mdi:thermometer-lines",
            lambda c: _detail(c, "target_raw"), UnitOfTemperature.CELSIUS),
    _DcDesc("dew_point", "Temperatura de condensación", "mdi:thermometer-water",
            lambda c: c.dew_point_c, UnitOfTemperature.CELSIUS),
    _DcDesc("mods_total", "Mods total", "mdi:sigma",
            lambda c: _detail(c, "mods_total"), UnitOfTemperature.CELSIUS,
            diagnostic=True),
    _DcDesc("lead", "Lead", "mdi:clock-fast",
            lambda c: _detail(c, "lead_h"), "h", diagnostic=True),
    _DcDesc("reason", "Rama de decisión", "mdi:directions-fork",
            lambda c: c.data.reason if c.data else None, diagnostic=True),
    # One dedicated sensor per bias (1:1 with dashboard chips).
    _DcDesc("bias_exterior", "Bias exterior", "mdi:home-thermometer-outline",
            lambda c: _detail(c, "bias_exterior"), UnitOfTemperature.CELSIUS,
            diagnostic=True),
    _DcDesc("bias_vmc", "Bias VMC", "mdi:fan",
            lambda c: _detail(c, "bias_vmc"), UnitOfTemperature.CELSIUS,
            diagnostic=True),
    _DcDesc("bias_trend", "Bias tendencia", "mdi:trending-up",
            lambda c: _detail(c, "bias_trend"), UnitOfTemperature.CELSIUS,
            diagnostic=True),
    _DcDesc("bias_brake", "Bias freno", "mdi:car-brake-alert",
            lambda c: _detail(c, "bias_brake"), UnitOfTemperature.CELSIUS,
            diagnostic=True),
    _DcDesc("bias_forecast", "Bias forecast", "mdi:weather-partly-cloudy",
            lambda c: _detail(c, "bias_forecast"), UnitOfTemperature.CELSIUS,
            diagnostic=True,
            attrs=lambda c: {"forecast_source": c._forecast_source()}),
    _DcDesc("bias_facade", "Bias fachadas", "mdi:window-shutter",
            lambda c: _detail(c, "bias_facade"), UnitOfTemperature.CELSIUS,
            diagnostic=True),
    _DcDesc("sdhb_bias", "Bias bus", "mdi:transit-connection-variant",
            lambda c: _detail(c, "sdhb_bias"), UnitOfTemperature.CELSIUS,
            diagnostic=True),
)


# Cold-surface condensation breakdown — only when a floor/water temp is set.
# "cond_margin" is the decisive value (corrected): negative => wet => zone off.
_DC_COND_SENSORS: tuple[_DcDesc, ...] = (
    _DcDesc("floor_temp", "Temperatura de suelo", "mdi:heating-coil",
            lambda c: c.floor_temp_c, UnitOfTemperature.CELSIUS),
    _DcDesc("cond_spread", "Desvío real condensación", "mdi:arrow-expand-vertical",
            lambda c: c.cond_spread_real, UnitOfTemperature.CELSIUS,
            diagnostic=True),
    _DcDesc("cond_margin", "Margen de condensación", "mdi:water-thermometer",
            lambda c: c.cond_margin_corrected, UnitOfTemperature.CELSIUS,
            diagnostic=True,
            attrs=lambda c: {
                "margen_establecido": c._cond_margin_set,
                "desvio_real": c.cond_spread_real,
                "temperatura_suelo": c.floor_temp_c,
                "punto_rocio": c.dew_point_c,
                "humedo": (c.cond_margin_corrected is not None
                           and c.cond_margin_corrected < 0),
            }),
)


@dataclass(frozen=True)
class _DcLearnDesc:
    key: str
    name: str
    icon: str
    getter: Callable[[DcCoordinator], float]
    setter: Callable[[DcCoordinator, float], None]
    unit: str | None = None
    as_int: bool = False


_DC_LEARN: tuple[_DcLearnDesc, ...] = (
    _DcLearnDesc("lead_gain_adaptive", "Lead adaptativo", "mdi:brain",
                 lambda c: c.lead_gain_adaptive,
                 lambda c, v: setattr(c, "lead_gain_adaptive", v), "h"),
    _DcLearnDesc("learn_rate", "Tasa aprendida", "mdi:speedometer",
                 lambda c: c.learn_rate_ema,
                 lambda c, v: setattr(c, "learn_rate_ema", v), "°C/h"),
    _DcLearnDesc("learn_overshoot", "Overshoot aprendido", "mdi:arrow-expand-up",
                 lambda c: c.learn_overshoot_ema,
                 lambda c, v: setattr(c, "learn_overshoot_ema", v),
                 UnitOfTemperature.CELSIUS),
    _DcLearnDesc("learned_lag", "Retardo térmico", "mdi:timer-sand",
                 lambda c: c.learned_lag_h,
                 lambda c, v: setattr(c, "learned_lag_h", v), "h"),
    _DcLearnDesc("adapt_ok_count", "Ciclos aprendidos", "mdi:counter",
                 lambda c: c.adapt_ok_count,
                 lambda c, v: setattr(c, "adapt_ok_count", int(v)), as_int=True),
    _DcLearnDesc("adapt_abort_count", "Ciclos abortados", "mdi:cancel",
                 lambda c: c.adapt_abort_count,
                 lambda c, v: setattr(c, "adapt_abort_count", int(v)), as_int=True),
)


class DcLearnSensor(_Base, RestoreSensor):
    """Learned adaptive-lead value, restored across restarts (diagnostic)."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator: DcCoordinator, entry: ConfigEntry,
                 desc: _DcLearnDesc) -> None:
        super().__init__(coordinator, entry, desc.key)
        self._desc = desc
        self._attr_translation_key = desc.key
        self._attr_icon = desc.icon
        self._attr_native_unit_of_measurement = desc.unit

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_sensor_data()
        if last is not None and last.native_value is not None:
            self._desc.setter(self.coordinator, float(last.native_value))

    @property
    def native_value(self):
        v = self._desc.getter(self.coordinator)
        return int(v) if self._desc.as_int else round(float(v), 3)


class MoldIndexSensor(_Base, RestoreSensor):
    """Mold-risk index (F22): accumulated hours, restored across restarts."""

    _attr_translation_key = "mold_index"
    _attr_icon = "mdi:mushroom-outline"
    _attr_native_unit_of_measurement = "h"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator: DcCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "mold_index")

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_sensor_data()
        if last is not None and last.native_value is not None:
            self.coordinator.mold_index = float(last.native_value)

    @property
    def native_value(self) -> float:
        return round(self.coordinator.mold_index, 1)

    @property
    def extra_state_attributes(self) -> dict:
        return {"active": self.coordinator._mold_active}


class AdjacentAdviceSensor(CoordinatorEntity[DcCoordinator], SensorEntity):
    """Adjacent warm-space advisory (F31): open_gain / close_alarm / none."""

    _attr_has_entity_name = True
    _attr_translation_key = "adjacent_advice"
    _attr_icon = "mdi:door-sliding"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["none", "open_gain", "close_alarm"]
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: DcCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_adjacent_advice"
        self._attr_device_info = DeviceInfo(
            identifiers={(const.DOMAIN, entry.entry_id)})

    @property
    def native_value(self) -> str:
        return self.coordinator.adjacent_advice


class InstallSensor(CoordinatorEntity[DcCoordinator], SensorEntity):
    """Installation profile (F26): generator/distribution/emitter + derived flags.

    Diagnostic only: the state is the declared triple and the attributes carry the
    inertia class and the ``compressor``/``peak``/``community`` flags that F09/F03
    consume.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "install"
    _attr_icon = "mdi:radiator"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: DcCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_install"
        self._attr_device_info = DeviceInfo(
            identifiers={(const.DOMAIN, entry.entry_id)})

    @property
    def native_value(self) -> str:
        o = self._entry.options
        return "/".join((o.get(const.CONF_GENERATOR, ""),
                         o.get(const.CONF_DISTRIBUTION, ""),
                         o.get(const.CONF_EMISSION, "")))

    @property
    def extra_state_attributes(self) -> dict:
        return self.coordinator.install_profile or {}


class DcSensor(CoordinatorEntity[DcCoordinator], SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator: DcCoordinator, entry: ConfigEntry,
                 desc: _DcDesc) -> None:
        super().__init__(coordinator)
        self._desc = desc
        self._attr_translation_key = desc.key
        self._attr_icon = desc.icon
        self._attr_native_unit_of_measurement = desc.unit
        self._attr_unique_id = f"{entry.entry_id}_{desc.key}"
        if desc.diagnostic:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_device_info = DeviceInfo(
            identifiers={(const.DOMAIN, entry.entry_id)})

    @property
    def native_value(self):
        return self._desc.getter(self.coordinator)

    @property
    def extra_state_attributes(self) -> dict | None:
        return self._desc.attrs(self.coordinator) if self._desc.attrs else None


def _shared_shutter_sensors(coordinator, entry: ConfigEntry) -> list[SensorEntity]:
    """The house-wide shared set (counts + sun) bound to the owning DS entry."""
    ents: list[SensorEntity] = [
        DsCoverCountSensor(coordinator, entry, key, icon, pred)
        for key, icon, pred in _DS_COVER_COUNTS]
    ents += [cls() for cls in _DS_SHARED_SUN]
    return ents


def adopt_shared_shutter_sensors(hass: HomeAssistant,
                                 prefer: str | None = None) -> bool:
    """Re-home the shared "Dynamic Home · Persianas" sensors on a live DS entry.

    When the owning entry unloads, its platform tears the shared sensors down and
    no other entry re-runs its own sensor setup — without this the house counts
    and sun sensors simply vanished until a restart. Uses the adder each DS entry
    registered at setup; returns True when someone adopted.
    """
    data = hass.data.get(const.DOMAIN, {})
    adders = data.get("_ds_summary_adders") or {}
    order = ([prefer] if prefer in adders else []) + list(adders)
    for eid in order:
        adder, coordinator, entry = adders[eid]
        data[const.DATA_DS_SUMMARY_OWNER] = eid
        adder(_shared_shutter_sensors(coordinator, entry))
        return True
    return False
