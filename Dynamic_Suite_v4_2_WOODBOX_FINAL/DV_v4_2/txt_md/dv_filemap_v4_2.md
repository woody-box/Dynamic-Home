# DV · FILE MAP — v4.2 compact (fix_final)

Este documento describe la función de cada archivo real del módulo DV.

## Core (obligatorios)
- **dv_vmc_inputs.yaml**
  - Helpers del usuario + defaults + contratos/checks (hw_map, onboarding, startup checks)
- **dv_vmc_logic.yaml**
  - Lógica de control: cálculo de target/escenarios (IAQ, dew, freecool, etc.)
- **dv_vmc_automations.yaml**
  - Aplicación real: automatizaciones, cooldowns, locks y scripts para cambiar velocidad
- **dv_vmc_sdhb.yaml**
  - Integración BUS/SDHB: consume intents (winner dv_vmc), publish feedback/heartbeat
- **dv_vmc_observability.yaml**
  - Observabilidad y health: sensores de diagnóstico, salud, módulos cargados

## Opcional
- **dv_testing_simulator_optional.yaml**
  - Simulador/tests/regresión (no recomendado en producción)

## SDHB consume rules (contract)
- `sensor.dv_vmc_sdhb_intent_matched` acepta `target` = `dv_vmc` (alias `dv`).
- `home` se considera legacy y se ignora.

## HW_MAP (REPLACE_*) — qué es y cómo resolverlo
DV usa un `hw_map` para desacoplar el código de tus entity_id reales. Si queda algún `REPLACE_*`, el onboarding/startup lo detecta.

### Imprescindibles / muy recomendados
- `REPLACE_sw_v1`: switch/fan speed 1 (imprescindible)
- `REPLACE_sw_v2`: switch/fan speed 2 (imprescindible)
- `REPLACE_sw_v3`: switch/fan speed 3 (imprescindible)
- `REPLACE_t_in`: temperatura interior (imprescindible)
- `REPLACE_t_ext`: temperatura exterior (muy recomendado)
- `REPLACE_hum_exterior`: humedad exterior (recomendado para dew/freecool)
- `REPLACE_dp_exterior`: punto de rocío exterior (o derivado)
- `REPLACE_dp_casa`: punto de rocío interior/casa (o derivado)

### Opcionales (habilitan funciones)
- `REPLACE_co2`: CO2 para IAQ (opcional)
- `REPLACE_pm25`: PM2.5 para IAQ (opcional)
- `REPLACE_hum_bano_pasillo`: humedad baño pasillo (opcional / boost por humedad)
- `REPLACE_hum_bano_dormitorio`: humedad baño dormitorio (opcional / boost por humedad)
- `REPLACE_dp_bano_pasillo`: punto de rocío baño pasillo (opcional)
- `REPLACE_dp_bano_dormitorio`: punto de rocío baño dormitorio (opcional)
- `REPLACE_t_asp`: temperatura aspiración (opcional)
- `REPLACE_t_ins`: temperatura impulsión (opcional)
- `REPLACE_sw_pwr`: switch potencia/enable general (opcional si no existe)
- `REPLACE_pwr_power`: sensor potencia eléctrica (opcional)
- `REPLACE_pwr_energy`: sensor energía (opcional)
- `REPLACE_sdhb_winner_entity`: solo si BUS/SDHB activo (winner entity)
- `REPLACE_sdhb_source_slot`: solo si BUS/SDHB activo (slot/source)

**Regla de producto:** si dejas un `REPLACE_*` sin resolver, esa función degradará o quedará deshabilitada; no debería romper el paquete, pero sí limitar comportamiento.

## Hotfix v4.2 — Hardware guard
- `sensor.dv_vmc_hw_replace_count` (detecta REPLACE_*)
- `timer.dv_vmc_startup_grace` (120s)
- `binary_sensor.dv_vmc_hw_contract_ok` incluye `warming_up` durante la gracia

## Backup/Restore externo (AppDaemons)
- `AppDaemon.dv_vmc_backup_save` escribe JSON en `dynamic_suite/dv/vmc/dv_vmc_backup.json`
- `AppDaemon.dv_vmc_backup_restore` restaura desde ese JSON
- Wrappers: `script.dv_vmc_backup_save` / `script.dv_vmc_backup_restore`

## Optional tests
- `yaml_zone_opcionales/dv_testing_features_optional_v4_2.yaml` (hw_replace_count guard)

## Optional tests
- `yaml_zone_opcionales/dv_testing_backup_cycle_optional_v4_2.yaml` (backup-save-restore cycle)

## Optional tests
- `yaml_zone_opcionales/dv_vmc_testing_golden_scenarios_optional_v4_2.yaml` (golden record/verify)
- `AppDaemons/dv_vmc_golden_record.py` / `dv_vmc_golden_verify.py`

## Extras (v4.2 · experimental)
- EMA (CO₂): `input_boolean.dv_vmc_co2_ema_enabled`, `input_number.dv_vmc_co2_ema_alpha`, `input_number.dv_vmc_co2_ema_value`, `sensor.dv_vmc_co2_ema`, automation `dv_vmc_co2_ema_update_1m`.
- EMA (PM2.5): `input_boolean.dv_vmc_pm25_ema_enabled`, `input_number.dv_vmc_pm25_ema_alpha`, `input_number.dv_vmc_pm25_ema_value`, `sensor.dv_vmc_pm25_ema`, automation `dv_vmc_pm25_ema_update_1m`.
- Health: `sensor.dv_vmc_health_summary`, `sensor.dv_vmc_health_code`.
- Startup grace adaptativo: automations `dv_vmc_startup_grace_end_early_on_contract_ok` y `dv_vmc_startup_grace_end_early_on_replace_placeholders`.


## Testing opcional
- dv_testing_hostile_outside_optional.yaml — valida el cap por tramos de Exterior Hostil.


## Documentación
- dv_pipeline_summary_v4_2.md / dv_pipeline_summary_v4_2.docx — resumen ejecutivo del pipeline de decisión DV.

- dv_vmc_pipeline_summary (sensor) — resumen compacto de decisión.
