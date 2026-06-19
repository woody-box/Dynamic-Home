# Suite v4.2 — Freeze checklist (pre-UI/UX)

Objetivo: poder declarar la suite **congelada** (sin bugs conocidos) y pasar a UI/UX sin miedo.

> Este checklist es **procedimental**: se ejecuta cuando vas a cerrar una versión.
> No introduce lógica nueva en runtime.

---

## 0) Precondiciones

- Tienes instalados los packages de:
  - DC v4.2
  - DV v4.2
  - DS v4.2
  - SDHB v4.2
- Has reiniciado Home Assistant tras actualizar YAML.
- Espera al menos **3 minutos** tras arranque (DV tiene *startup grace* de 120s).

---

## 1) Contracts (PASO OBLIGATORIO)

### DV
- `binary_sensor.dv_vmc_hw_contract_ok` debe estar `on` (tras 120s).
- `sensor.dv_vmc_hw_missing_count` = 0
- `sensor.dv_vmc_hw_replace_count` = 0

### DC
- `binary_sensor.dc_hwmap_contract_ok` `on` (si aplica en tu instalación)
- `binary_sensor.dc_runtime_contract_ok` `on`

### DS (W1 como referencia)
- `binary_sensor.ds_w1_sdhb_enabled` según tu configuración
- si consumes bus: `binary_sensor.ds_w1_sdhb_allow_override` responde a winner (ver sección 3)

### SDHB
- `sensor.sdhb_*` (winners) disponibles para targets activos (por ejemplo `sensor.sdhb_winner_ds_w1`)

**PASS** si todos los contracts relevantes están OK y no hay placeholders.

---

## 2) Backup/Restore (PASO OBLIGATORIO)

### DC (common)
1. Ejecuta `script.dc_common_backup_save`
2. Comprueba que `input_text.dc_common_backup_json` NO está vacío
3. (Opcional) Ejecuta `script.dc_common_backup_restore` y verifica que no hay errores

### DV
1. Ejecuta `script.dv_vmc_backup_inputs_save`
2. Comprueba que `input_text.dv_vmc_backup_inputs_json` NO está vacío
3. (Opcional) Ejecuta `script.dv_vmc_backup_inputs_restore`

### DS (W1)
1. Ejecuta `script.ds_w1_backup_inputs_save`
2. Comprueba que `input_text.ds_w1_backup_json` NO está vacío
3. (Opcional) Ejecuta `script.ds_w1_backup_inputs_restore`

**PASS** si los JSON de backup se generan y restore no rompe nada.

---

## 3) Bus + integración mínima (PASO OBLIGATORIO)

### SDHB tests (opcionales, pero recomendados)
- Activa `input_boolean.sdhb_tests_enabled`
- Ejecuta el escenario de arbitraje (prioridades) y verifica `PASS`.

### E2E (DC → SDHB → DS)
- Activa `input_boolean.sdhb_e2e_tests_enabled`
- Selecciona `e2e_dc_solar_shield_ds_w1`
- Debe terminar en `PASS`:
  - winner = `request_solar_shield`
  - DS refleja consumo (`binary_sensor.ds_w1_sdhb_request_solar_shield` = `on`)

**PASS** si SDHB tests pasan y el E2E pasa.

---

## 4) Golden regression (recomendado)

### DV
- Ejecuta el simulador/golden si lo tienes habilitado
- Debe reportar `PASS` en escenarios principales

**PASS** si no hay regressions.

---

## 5) Limpieza (recomendado)

- Desactiva tests:
  - `input_boolean.sdhb_tests_enabled` (o deja que auto-OFF lo apague)
  - `input_boolean.sdhb_e2e_tests_enabled`
- Comprueba que no quedan warnings de YAML en el log tras reinicio.

---

## Criterio de Freeze (FINAL)

Puedes declarar **v4.2 congelada** cuando:

- (1) Contracts OK
- (2) Backup/restore OK
- (3) Bus + E2E OK
- (4) (Recomendado) Golden DV OK
- (5) Sin warnings persistentes de YAML/entidades inexistentes


## Rendimiento (MariaDB) — recorder exclusions
- Bloque listo para copiar/pegar: `docs/recorder_exclusions_v4_2.md` / `docs/recorder_exclusions_v4_2.docx`.

## Health summaries
- SDHB: `sensor.sdhb_health_summary`
- DV: `sensor.dv_vmc_health_summary`
- DS: `sensor.ds_w1_health_summary`


## Post‑clonado (obligatorio)
- Ver guía: `Suite_tools_v4_2/docs/guia_clonado_suite_v4_2.md` (Paso Final Crítico).
