# DS · FILE MAP — v4.2 compact (fix_final_r4)

## Core (obligatorios)
- **ds_common.yaml**
  - helpers globales del módulo (advanced mode, opciones comunes)
- **ds_bus.yaml**
  - grupos `ds_zoneXX_fY_windows`
  - sincronización de grupos según zone/facade de cada ventana
  - publicación de flags por fachada/zone al BUS (cuando aplique)

## Por ventana (W1..W8)
Para cada `ds_wX`:
- **ds_wX_inputs.yaml**
  - helpers: zone/facade, toggles, límites, parámetros de operación
- **ds_wX_logic.yaml**
  - cálculo/decisión: `target_position`, `target_reason`, degradación segura
- **ds_wX_sdhb.yaml**
  - publish intents DS→BUS (shield/gain/freecool)
  - consume winner BUS→DS (si aplica a lógica)
  - heartbeat

## Opcional
- **ds_testing.yaml**
  - simulación/tests/regresión (no recomendado en producción)

## Parámetros modificables (helpers) — contrato
Estos helpers se configuran desde la UI. El patrón `ds_wX_` aplica a W1..W8.

### input_select
- `input_select.ds_wX_facade`
- `input_select.ds_wX_override_mode`
- `input_select.ds_wX_zone`

### input_boolean
- `input_boolean.ds_wX_cover_inverted`
- `input_boolean.ds_wX_forecast_enabled`
- `input_boolean.ds_wX_interlock_enabled`
- `input_boolean.ds_wX_interlock_notify_enabled`
- `input_boolean.ds_wX_privacy_enabled`
- `input_boolean.ds_wX_sim_enabled`
- `input_boolean.ds_wX_sim_rain`
- `input_boolean.ds_wX_sim_sun_effective`
- `input_boolean.ds_wX_sleep_mode`
- `input_boolean.ds_wX_slew_enabled`
- `input_boolean.ds_wX_weather_protect_enabled`

### input_number
- `input_number.ds_wX_altura_cm`
- `input_number.ds_wX_angulo_fachada_deg`
- `input_number.ds_wX_delta_freecool`
- `input_number.ds_wX_delta_hot_out`
- `input_number.ds_wX_forecast_cold_threshold`
- `input_number.ds_wX_forecast_hot_threshold`
- `input_number.ds_wX_forecast_preclose_time_hhmm`
- `input_number.ds_wX_freecool_max_open_pct`
- `input_number.ds_wX_interlock_tol_pct`
- `input_number.ds_wX_interlock_wait_s`
- `input_number.ds_wX_last_target_pct`
- `input_number.ds_wX_lux_cloudy_max`
- `input_number.ds_wX_lux_day_min`
- `input_number.ds_wX_lux_night_max`
- `input_number.ds_wX_min_change_pct`
- `input_number.ds_wX_min_time_between_moves_min`
- `input_number.ds_wX_offset_edificios_min`
- `input_number.ds_wX_orientacion_deg`
- `input_number.ds_wX_override_position_pct`
- `input_number.ds_wX_privacy_position_pct`
- `input_number.ds_wX_rain_close_pct`
- `input_number.ds_wX_rain_threshold`
- `input_number.ds_wX_sdhb_solar_shield_max_open_pct`
- `input_number.ds_wX_slew_step_pct`
- `input_number.ds_wX_summer_min_open_pct`
- `input_number.ds_wX_voladizo_cm`
- `input_number.ds_wX_weather_max_open_pct`
- `input_number.ds_wX_wind_cap_hold_min`
- `input_number.ds_wX_wind_cap_hyst_kmh`
- `input_number.ds_wX_wind_cap_span_kmh`
- `input_number.ds_wX_wind_limit_kmh`
- `input_number.ds_wX_winter_night_pct`

## Reason codes (target_reason) — contrato
DS expone `sensor.ds_wX_target_reason`. Reason codes principales:

- `delta_freecool`
- `freecool_max_open_pct`
- `freecool_night`
- `lux_night_max`
- `meteo_rain`
- `meteo_wind_cap`
- `night_pct`
- `none`
- `privacy`
- `privacy_active`
- `privacy_from_hhmm`
- `privacy_position_pct`
- `privacy_time`
- `rain`
- `rain_close_pct`
- `rain_enabled`
- `rain_entity`
- `rain_pos`
- `rain_threshold`
- `sdhb_solar_shield`
- `shield_max`
- `summer_solar_shield`
- `wind`
- `wind_enabled`
- `wind_entity`
- `wind_kmh`
- `wind_limit_kmh`
- `wind_safe`
- `winter_night_insulate`
- `winter_night_pct`
- `winter_solar_gain`

## Nota anti‑flapping (slew)
En `v4.2_hotfix` el slew se aplica una sola vez (en el cálculo). El apply usa el target directo.

- yaml_common_obligatorios/ds_common_backup.yaml


### Backup W1
- script.ds_w1_backup_inputs_save / restore
- sensor.ds_w1_backup_storage, sensor.ds_w1_fabrica_keys

Nota (MariaDB/state 255): usar ds_*_backup_*_file (AppDaemon) para backups grandes.

## Optional tests
- `yaml_zone_opcionales/ds_w1_testing_features_optional_v4_2.yaml` (consume gate + ACK)

## Optional tests
- `yaml_zone_opcionales/ds_w1_testing_backup_cycle_optional_v4_2.yaml` (backup-save-restore cycle)

## Optional tests
- `yaml_zone_opcionales/ds_w1_testing_golden_scenarios_optional_v4_2.yaml` (golden record/verify)
- `AppDaemons/ds_w1_golden_record.py` / `ds_w1_golden_verify.py`


### Freecool night y clima asociado
- `freecool_night` consulta el modo HVAC del climate asociado a la ventana (si está habilitado).
- Si no hay climate asignado (o `climate_enabled=off`), la lógica degrada a OFF por seguridad.


## Health summary
- `sensor.ds_w1_health_summary` y `sensor.ds_w1_health_code`.
