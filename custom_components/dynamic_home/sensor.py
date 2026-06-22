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
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from . import const, zones
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
        (const.CONF_VOC, "COV"),
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


def _mirror_sensors(entry: ConfigEntry, module: str) -> list[SensorEntity]:
    """F36: a stable mirror sensor per configured input role (opt-in)."""
    if not entry.options.get(const.CONF_EXPOSE_MIRRORS, False):
        return []
    out: list[SensorEntity] = []
    for role, name in _MIRROR_ROLES.get(module, ()):
        source = entry.data.get(role)
        if source:
            out.append(HwMirrorSensor(entry, role, name, source))
    return out


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry,
                            async_add_entities: AddEntitiesCallback) -> None:
    coordinator = hass.data[const.DOMAIN][entry.entry_id]
    module = entry.data.get(const.CONF_MODULE)
    if module == const.MODULE_WEATHER:
        async_add_entities([WeatherSourceSensor(coordinator, entry)])
        return
    if module == const.MODULE_ZONES:
        async_add_entities([ZonesSensor(coordinator, entry)])
        return
    if module == const.MODULE_CLIMATE:
        ents: list[SensorEntity] = [DcSensor(coordinator, entry, d)
                                    for d in _DC_SENSORS]
        ents += [DcLearnSensor(coordinator, entry, d) for d in _DC_LEARN]
        if coordinator.has_mold():
            ents.append(MoldIndexSensor(coordinator, entry))
        if coordinator.has_adjacent():
            ents.append(AdjacentAdviceSensor(coordinator, entry))
        ents.append(BusSensor(coordinator, entry))
        ents += _mirror_sensors(entry, module)
        async_add_entities(ents)
        return
    if module == const.MODULE_SHUTTER:
        async_add_entities([BusSensor(coordinator, entry),
                            *_mirror_sensors(entry, module)])
        return
    entities: list[SensorEntity] = [HoursSensor(coordinator, entry, d)
                                    for d in _HOURS]
    entities.append(SpeedSensor(coordinator, entry))
    entities.append(ReasonSensor(coordinator, entry))
    entities.append(ModeSensor(coordinator, entry))
    entities.append(StateSensor(coordinator, entry))
    entities.append(OverrideRemainingSensor(coordinator, entry))
    entities.append(FilterLifeSensor(coordinator, entry))
    if coordinator.has_hrv():
        entities.append(HrvEfficiencySensor(coordinator, entry))
    if coordinator.has_voc():
        entities.append(VocSensor(coordinator, entry))
    entities.append(BusSensor(coordinator, entry))
    entities += _mirror_sensors(entry, module)
    async_add_entities(entities)


class ZonesSensor(CoordinatorEntity, SensorEntity):
    """Zone/group hierarchy (F24): zone count + a readable tree in attributes."""

    _attr_has_entity_name = True
    _attr_name = "Zonas"
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
    _attr_name = "Fuente activa"
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
                 source: str) -> None:
        self._source = source
        self._attr_name = f"{name} (espejo)"
        self._attr_unique_id = f"{entry.entry_id}_mirror_{role}"
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
            return float(st.state)
        except (TypeError, ValueError):
            return st.state

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
            name="Dynamic Home Bus")

    @property
    def native_value(self) -> str | None:
        return self.coordinator.bus_explain.get("winner")

    @property
    def extra_state_attributes(self) -> dict:
        ex = self.coordinator.bus_explain
        return {"source": ex.get("source"), "priority": ex.get("priority"),
                "candidates": ex.get("candidates"), "reason": ex.get("reason")}


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
        self._attr_name = desc.name
        self._attr_icon = desc.icon

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_sensor_data()
        if last is not None and last.native_value is not None:
            self._desc.setter(self.coordinator, float(last.native_value))

    @property
    def native_value(self) -> float:
        return round(self._desc.getter(self.coordinator), 3)


class SpeedSensor(_Base):
    _attr_name = "Speed"
    _attr_icon = "mdi:fan"

    def __init__(self, coordinator: DvCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "speed")

    @property
    def native_value(self) -> int:
        return self.coordinator.current_speed


class ReasonSensor(_Base):
    _attr_name = "Reason"
    _attr_icon = "mdi:information-outline"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: DvCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "reason")

    @property
    def native_value(self) -> str | None:
        data = self.coordinator.data
        return data.reason if data else None


class ModeSensor(_Base):
    _attr_name = "Mode"
    _attr_icon = "mdi:fan-auto"

    def __init__(self, coordinator: DvCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "mode")

    @property
    def native_value(self) -> str:
        return self.coordinator.preset


class StateSensor(_Base):
    """Operational state: boot (not evaluated) / grace (startup) / active."""

    _attr_name = "State"
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

    _attr_name = "Override remaining"
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

    _attr_name = "Filter life"
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

    _attr_name = "Recuperator efficiency"
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
        return {"state": self.coordinator.hrv_state}


class VocSensor(_Base):
    """Observed VOC level (F30). Informational only — it never drives the speed."""

    _attr_name = "VOC"
    _attr_icon = "mdi:molecule"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: DvCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "voc")

    @property
    def native_value(self) -> float | None:
        return self.coordinator.voc_level


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
            diagnostic=True),
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
        self._attr_name = desc.name
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

    _attr_name = "Índice de moho"
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
    _attr_name = "Aviso espacio adyacente"
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


class DcSensor(CoordinatorEntity[DcCoordinator], SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator: DcCoordinator, entry: ConfigEntry,
                 desc: _DcDesc) -> None:
        super().__init__(coordinator)
        self._desc = desc
        self._attr_name = desc.name
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
