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
    PERCENTAGE,
    EntityCategory,
    UnitOfEnergy,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from . import const, schedule, zones
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


def _mirror_sensors(entry: ConfigEntry, module: str) -> list[SensorEntity]:
    """F36: a stable mirror sensor per configured input role (opt-in)."""
    if not entry.options.get(const.CONF_EXPOSE_MIRRORS, False):
        return []
    out: list[SensorEntity] = []
    for role, name in _MIRROR_ROLES.get(module, ()):
        source = entry.data.get(role)
        if source:
            precision = _MIRROR_PRECISION.get(role, _MIRROR_PRECISION_DEFAULT)
            out.append(HwMirrorSensor(entry, role, name, source, precision))
    return out


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry,
                            async_add_entities: AddEntitiesCallback) -> None:
    coordinator = hass.data[const.DOMAIN][entry.entry_id]
    module = entry.data.get(const.CONF_MODULE)
    if module == const.MODULE_WEATHER:
        async_add_entities([WeatherSourceSensor(coordinator, entry)])
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
        ents += _mirror_sensors(entry, module)
        async_add_entities(ents)
        return
    if module == const.MODULE_SHUTTER:
        ds_ents: list[SensorEntity] = [
            BusSensor(coordinator, entry),
            EnergySensor(coordinator, entry),
            DsPositionSensor(coordinator, entry),
            DsTargetSensor(coordinator, entry),
            DsReasonSensor(coordinator, entry),
            DsOverrideRemainingSensor(coordinator, entry)]
        # First-class context sensors, to read the "why" at a glance — each only
        # when its source is configured.
        if coordinator._hw(const.CONF_DS_T_IN):
            ds_ents.append(DsIndoorTempSensor(coordinator, entry))
        if coordinator._hw(const.CONF_DS_T_OUT):
            ds_ents.append(DsOutdoorTempSensor(coordinator, entry))
        if coordinator._hw(const.CONF_CLIMATE):
            ds_ents.append(DsClimateModeSensor(coordinator, entry))
            ds_ents.append(DsClimateSetpointSensor(coordinator, entry))
            ds_ents.append(DsClimateTempSensor(coordinator, entry))
        ds_ents.extend(_mirror_sensors(entry, module))
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
            identifiers={(const.DOMAIN, entry.entry_id)})

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


class HouseEnergySensor(CoordinatorEntity, SensorEntity):
    """House energy total (F34 §8.2): sum of every module's kWh; Energy dashboard."""

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
        self._attr_device_info = DeviceInfo(
            identifiers={(const.DOMAIN, entry.entry_id)})

    @property
    def native_value(self) -> float:
        return round(self.coordinator.house_kwh, 3)


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
            identifiers={(const.DOMAIN, entry.entry_id)})

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
            self.coordinator.energy_kwh = float(last.native_value)

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
