# DV · Pipeline summary (v4.2)

Este documento resume la **tubería de decisión** de Dynamic Ventilation (DV) en una instalación típica.

## 1) Entradas principales (señales)
- **CO₂ interior**: `sensor.dv_vmc_co2_safe` (o `sensor.dv_vmc_co2_ema` si EMA activado).
- **PM2.5 interior**: `sensor.dv_vmc_pm25_safe` (o `sensor.dv_vmc_pm25_ema` si EMA activado).
- **Humedad / rocío**: señales de dew risk / dry-mode (seguridad).
- **Exterior (opcional)**: WAQI AQI global vía `sensor.dv_vmc_outdoor_aqi_safe` (hostile outside).

## 2) Fase 0 — Habilitación y contratos
1) `input_boolean.dv_vmc_enabled` debe estar ON.
2) `binary_sensor.dv_vmc_hw_contract_ok` debe estar ON (hw_map completo, sin REPLACE_*).
3) `timer.dv_vmc_startup_grace` suaviza el arranque (si aplica en tu build).

## 3) Fase 1 — Normalización (SAFE)
DV nunca usa sensores “crudos” directamente. Usa versiones SAFE (numéricas) y degrada si están KO:
- `*_safe` (y/o `availability:` en templates) para evitar romper dashboards o lógica.

## 4) Fase 2 — Seguridad (dew risk / dry-mode)
Si hay riesgo de condensación o modo de secado activo, DV puede forzar una estrategia mínima de ventilación.
> Nota: en el código actual, **Exterior Hostil** puede capar/apagar la VMC incluso si hay dew risk (se aplica al final del cálculo en Stage 1/2).

## 5) Fase 3 — IAQ (CO₂ + PM2.5)
DV calcula la demanda por IAQ en niveles (V1/V2/V3) aplicando:
- umbrales (base y/o adaptativos)
- histéresis para evitar oscilación
- regla “peor caso manda”:
  - V3 si **CO₂** o **PM2.5** piden V3
  - V2 si cualquiera pide V2
  - baja de nivel solo cuando ambos ya están bajo el umbral de bajada

## 6) Fase 4 — Capa “Exterior hostil” (opcional, WAQI)
Activación: `input_boolean.dv_vmc_hostile_outside_enabled`

Tramos (configurables):
- `< T1` (default 50): sin cap
- `T1–T2` (50–100): cap a V2
- `T2–T3` (100–150): cap a V1
- `>= T3` (>=150): OFF

Telemetría:
- `sensor.dv_vmc_hostile_outside_cap` → 3/2/1/0
- `binary_sensor.dv_vmc_hostile_outside_active`

HW map:
- `sensor.dv_vmc_hw_map.attributes.outdoor_aqi_entity` (por defecto WOODBOX: `sensor.el_picarral_zaragoza_spain_indice_de_calidad_del_aire`)
- Override (tests/avanzado): `input_text.dv_vmc_outdoor_aqi_entity_override`

## 7) Fase 5 — Aplicación (driver)
DV aplica el setpoint final al driver (V1/V2/V3 u OFF) respetando:
- `dv_vmc_driver_busy` (si existe)
- cooldowns / locks (si existen)

## 8) Debug rápido (producción)
- `sensor.dv_vmc_health_summary` / `sensor.dv_vmc_health_code`
- `sensor.dv_vmc_decision_debug` (JSON grande; recomendado excluir del recorder)



## Pipeline summary sensor
- `sensor.dv_vmc_pipeline_summary` (estado compacto + atributos: target_final/reason/caps).
