# Examples

Minimal, copy-pasteable setups for each module. Add the integration
(**Settings → Devices & services → Add integration → Dynamic Home**), pick the
module, and fill the fields with your entities.

> **Test with dummy entities first.** Create `input_boolean`/`switch` helpers for
> the relays, turn on **Observe only**, and watch the reason codes for a few days
> before pointing Dynamic Home at real hardware.

---

## Example 1 — 3-speed ventilation (DV)

A simple HRV/VMC with three speeds driven by relays and the two air-quality
sensors that actually move the speed (CO₂ and PM2.5).

### How it works

Dynamic Ventilation picks the **minimum speed** the air quality needs:

- **V1** — base ventilation.
- **V2** — when CO₂, humidity or PM2.5 start rising.
- **V3** — when air quality needs a stronger response.
- **Manual override** — temporary forced speed.
- **Failsafe** — safe mode when sensors are missing or out of range.

Speeds are wired break-before-make (never V2 and V3 on at once). The power switch
is turned on/off around the speed relays.

### Entities

| Role | Field | Example entity | Required |
|------|-------|----------------|:-:|
| Power | `sw_pwr` | `switch.vmc_power` | ✅ |
| Speed 2 relay | `sw_v2` | `switch.vmc_v2` | ✅ |
| Speed 3 relay | `sw_v3` | `switch.vmc_v3` | ✅ |
| CO₂ | `co2` | `sensor.co2_living` | ✅ |
| PM2.5 | `pm25` | `sensor.pm25_living` | ✅ |
| Indoor temp | `t_in` | `sensor.temp_living` | ⬜ |
| Outdoor temp | `t_ext` | `sensor.temp_outdoor` | ⬜ |
| Outdoor AQI | `outdoor_aqi_entity` | `sensor.outdoor_aqi` | ⬜ |

> V1 = both speed relays OFF; V2 = `sw_v2` ON; V3 = `sw_v3` ON. Temperatures
> enable free-cooling; AQI caps ventilation on hostile-outside days.

---

## Example 2 — A climate zone (DC)

One zone needs only an indoor temperature sensor and the shutter target it drives
on the bus. Everything else is optional and unlocks more behaviour.

### How it works

Dynamic Climate computes a **per-zone target** (day/night base + biases:
exterior, trend, forecast, facade, bus) and a reason code. While heating it
publishes `request_solar_gain` to its shutter target; while cooling,
`request_solar_shield` — so the shutters react on the sunlit facade.

### Entities

| Role | Field | Example | Required |
|------|-------|---------|:-:|
| Indoor temp | `dc_t_int` | `sensor.temp_living` | ✅ |
| Shutter target | `ds_target` | `ds` (default) | ✅ |
| Outdoor temp | `dc_t_ext` | `sensor.temp_outdoor` | ⬜ |
| Real thermostat | `dc_climate` | `climate.living_floor` | ⬜ |
| Indoor humidity | `dc_humidity` | `sensor.rh_living` | ⬜ |
| Window contact | `dc_window` | `binary_sensor.window_living` | ⬜ |
| Real demand / relay | `dc_valve` | `switch.floor_valve` | ⬜ |
| Dehumidifier | `dc_dehumidifier` | `switch.dehumidifier` | ⬜ |

> Humidity enables dew-point protection and the mold-risk index; a window contact
> pauses the zone (and without one, an open window can be inferred from a sharp
> temperature drop against demand); `dc_valve` feeds the Adaptive Lead with the
> real heating/cooling demand.

---

## Example 3 — A shutter by facade (DS)

One window = one `cover`. The facade azimuth tells Dynamic Shutter where the sun
hits, so a climate zone can shield only that facade.

### How it works

DS computes a target position `0..100` through a **priority cascade**, then caps
it (wind, bus, slew):

1. Override (lock / hold / ttl)
2. Weather (rain → close)
3. Privacy schedule
4. Summer free-cooling at night
5. Summer solar shield
6. Winter solar gain
7. Winter night insulation
8. Default (open)

### Entities

| Role | Field | Example | Required |
|------|-------|---------|:-:|
| Cover | `cover` | `cover.living_window` | ✅ |
| Facade azimuth (°) | `facade_azimuth_deg` | `180` (south) | ✅ |
| Facade span (°) | `facade_span_deg` | `90` | ⬜ |
| Indoor temp | `ds_t_in` | `sensor.temp_living` | ⬜ |
| Outdoor temp | `ds_t_out` | `sensor.temp_outdoor` | ⬜ |

> The shutter listens on its facade `ds_f<azimuth>` (e.g. `ds_f180`); set a
> climate zone's `ds_target` to `ds` to drive all facades, or to a specific
> facade to scope it.

---

See the per-module algorithms in [`SPEC_DC.md`](SPEC_DC.md),
[`SPEC_DV.md`](SPEC_DV.md) and [`SPEC_DS.md`](SPEC_DS.md) (Spanish).
