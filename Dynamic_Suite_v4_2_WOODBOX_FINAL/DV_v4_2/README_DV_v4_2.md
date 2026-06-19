# DV (Dynamic Ventilation) · README (v4.2)

DV controla una **unidad de ventilación mecánica (VMC)** con *naming determinista* `dv_vmc` (no `dv_home`). fileciteturn25file1

---

## 1) Qué hace DV

- Decide **V1/V2/V3** (y/o ON/OFF según tu driver) en base a:
  - IAQ (principalmente **CO₂**; PM2.5 opcional)
  - Humedad / riesgo de condensación (protección)
  - Restricciones (eco/quiet, horarios, cooldowns, driver busy)
- Publica/consume intents vía **SDHB (BUS)** si está habilitado.

---

## 2) Archivos obligatorios (DV)

Estos archivos deben cargarse como *packages* de Home Assistant: fileciteturn25file0

- `dv_vmc_inputs.yaml`
- `dv_vmc_logic.yaml`
- `dv_vmc_automations.yaml`
- `dv_vmc_sdhb.yaml`
- `dv_vmc_observability.yaml`

### Dependencia externa (BUS)
- `suite_dynamic_home_bus_v4_2.yaml` (se instala aparte). fileciteturn25file0turn25file1

---

## 3) Requisitos

### Home Assistant
- Cargar DV como `packages` (misma carpeta que el resto de la suite).

### AppDaemon (obligatorio para backup/golden si tu build lo usa)
- Instalar el add-on “AppDaemon” en HAOS (Apps).
- Copiar las apps de la suite a la ruta de AppDaemon (según tu instalación HAOS/Docker).
- DV invoca servicios `appdaemon.dynamic_suite_backup/*` y `appdaemon.dynamic_suite_golden/*`.

---

## 4) Instalación rápida (pasos)

1) **Instala el BUS (SDHB)** y verifica que `input_boolean.sdhb_enabled` existe.
2) Copia los **5 YAML obligatorios** de DV a tus `packages` (misma estructura/nombres).
3) Abre el `sensor.dv_vmc_hw_map`:
   - Sustituye cualquier `REPLACE_*` por tus `entity_id` reales.
   - Comprueba `sensor.dv_vmc_hw_replace_count` → debe ser **0**.
   - Comprueba `binary_sensor.dv_vmc_hw_contract_ok` → debe estar **on**.
4) Activa `input_boolean.dv_vmc_enabled`.

---

## 5) Hardware map (hw_map)

DV usa un `hw_map` para desacoplar la lógica del hardware real.

- Si quedan placeholders `REPLACE_*`:
  - `sensor.dv_vmc_hw_replace_count > 0`
  - DV puede levantar una **notificación persistente** y/o bloquear `hw_contract_ok` (según la build).

---

## 6) Startup grace (arranque)

- `input_number.dv_vmc_startup_grace_s` define el tiempo de gracia (default típico: 120 s).
- En builds “experimentales”, el grace puede terminar antes si:
  - `binary_sensor.dv_vmc_hw_contract_ok` pasa a **on**
  - o si aparecen `REPLACE_*` (porque no se van a resolver “solos”).

---

## 7) EMA (CO₂ / PM2.5) — opcional (si tu build lo incluye)

### CO₂ EMA
- Activar: `input_boolean.dv_vmc_co2_ema_enabled`
- Parámetros:
  - `input_number.dv_vmc_co2_ema_alpha`
  - `input_number.dv_vmc_co2_ema_value`
- Sensor expuesto: `sensor.dv_vmc_co2_ema`
- Si está OFF, DV usa `sensor.dv_vmc_co2_safe` (instantáneo).

### PM2.5 EMA (experimental)
- Activar: `input_boolean.dv_vmc_pm25_ema_enabled`
- Parámetros:
  - `input_number.dv_vmc_pm25_ema_alpha`
  - `input_number.dv_vmc_pm25_ema_value`
- Sensor expuesto: `sensor.dv_vmc_pm25_ema`
- Si está OFF, DV usa `sensor.dv_vmc_pm25_safe` (instantáneo).

> Recomendación: mantener CO₂ como driver principal y PM2.5 como secundario, salvo que quieras priorizar salud/partículas.

---

## 8) Observabilidad rápida

- `sensor.dv_vmc_health_summary` / `sensor.dv_vmc_health_code` (si existen en tu build).
- `sensor.dv_vmc_decision_debug` (JSON grande; recomendado excluir del recorder).

---

## 9) Backups (si tu build los incluye)

DV guarda backups en disco bajo `/config/dynamic_suite/...` (ruta exacta según tu suite).
- **Guardar**: servicio AppDaemon `.../save`
- **Restaurar**: servicio AppDaemon `.../restore`

---

## 10) Tests (opcionales)

Puede haber YAML opcionales tipo simulador / features / backup-cycle / recovery.
Úsalos para validar cambios sin tocar producción.

---

## 11) Recomendación MariaDB / recorder

Excluye sensores JSON “grandes” (debug/params/backup_storage) para no saturar BD.
Si tu suite incluye el bloque listo para copiar/pegar, úsalo en `configuration.yaml`.

---

## 12) Troubleshooting

- `hw_contract_ok = off`: revisa `hw_map`, `REPLACE_*`, entidades missing.
- DV no cambia velocidad: revisa `dv_vmc_driver_busy`, cooldowns, y que tu driver tenga los entity_id correctos.
- BUS: revisa `sensor.sdhb_health_summary` y el winner correspondiente a `dv_vmc` si consume intents.
