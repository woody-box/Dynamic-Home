# DV (Dynamic Ventilation) — v4.2 compact (fix_final)

Unidad principal: `dv_vmc` (producto).

## Archivos reales (obligatorios)
- `dv_vmc_inputs.yaml` — helpers + defaults + contratos/checks
- `dv_vmc_logic.yaml` — cálculo de target / lógica principal
- `dv_vmc_automations.yaml` — aplicación real (automations/scripts)
- `dv_vmc_sdhb.yaml` — integración SDHB (consume/publish/heartbeat)
- `dv_vmc_observability.yaml` — observabilidad/health

## BUS/SDHB
- `suite_dynamic_home_bus_v4_2.yaml` (se instala aparte)

## Opcional
- `dv_testing_simulator_optional.yaml` (tests/sim/regresión)

## SDHB target contractual
- DV consume intents solo cuando `target` coincide con `dv_vmc` (alias opcional: `dv`).
- No se acepta `home`.

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

NOTE (AppDaemon): backup/restore & golden via AppDaemon services; files stored under /config/dynamic_suite/.

## EMA (CO₂ / PM2.5) · Opcional
- **CO₂ EMA**: activa `input_boolean.dv_vmc_co2_ema_enabled`.
  - DV usará `sensor.dv_vmc_co2_ema` (basado en `input_number.dv_vmc_co2_ema_value`) como valor de CO₂ para la lógica IAQ.
  - Parámetro: `input_number.dv_vmc_co2_ema_alpha` (default 0.20). Actualización 1/min.
- **PM2.5 EMA**: activa `input_boolean.dv_vmc_pm25_ema_enabled`.
  - DV usará `sensor.dv_vmc_pm25_ema` (basado en `input_number.dv_vmc_pm25_ema_value`) como valor de PM2.5 para la lógica IAQ.
  - Parámetro: `input_number.dv_vmc_pm25_ema_alpha` (default 0.20). Actualización 1/min.
- Si los toggles están OFF, DV usa los valores instantáneos (`sensor.dv_vmc_co2_safe` / `sensor.dv_vmc_pm25_safe`) como hasta ahora.

## Health summary
- `sensor.dv_vmc_health_summary` y `sensor.dv_vmc_health_code` exponen un estado corto (OK/WARN/FAIL) para diagnóstico rápido.

## Startup grace (configurable + adaptativo)
- `input_number.dv_vmc_startup_grace_s` define la ventana de arranque (default 120s).
- Durante el grace, DV evita falsos KO de hardware.
- El grace termina antes si `binary_sensor.dv_vmc_hw_contract_ok` pasa a ON, o si aparecen placeholders `REPLACE_*` (`sensor.dv_vmc_hw_replace_count > 0`).


## Exterior hostil (WAQI AQI global) — opcional
- Sensor exterior (AQI global): `sensor.dv_vmc_outdoor_aqi_safe`
- Activación: `input_boolean.dv_vmc_hostile_outside_enabled`
- Tramos (configurables):
  - `< T1` (default 50): sin cap (3)
  - `T1–T2` (50–100): cap a V2 (2)
  - `T2–T3` (100–150): cap a V1 (1)
  - `>= T3` (>=150): OFF (0)
- Helpers: `input_number.dv_vmc_hostile_outside_t1/t2/t3`
- Telemetría: `sensor.dv_vmc_hostile_outside_cap` + `binary_sensor.dv_vmc_hostile_outside_active`

### HW map
- `sensor.dv_vmc_hw_map.attributes.outdoor_aqi_entity` (**opcional**) (por defecto en WOODBOX: `sensor.el_picarral_zaragoza_spain_indice_de_calidad_del_aire`)
- Override (tests/avanzado): `input_text.dv_vmc_outdoor_aqi_entity_override` (entity_id alternativo).


## Pipeline summary
- Ver `dv_pipeline_summary_v4_2.md` / `dv_pipeline_summary_v4_2.docx`.


## Pipeline summary
- `sensor.dv_vmc_pipeline_summary` (resumen compacto de decisión).
