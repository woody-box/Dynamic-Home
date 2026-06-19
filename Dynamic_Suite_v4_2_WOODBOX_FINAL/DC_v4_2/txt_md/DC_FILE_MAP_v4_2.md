# Dynamic Climate (DC) · FILE MAP · v4.2 (compact · fix_final)

Este documento describe **los archivos reales** del módulo DC v4.2 compact y qué aporta cada uno.

> Nota: “Common” = global. “Zone01” = zona clonable (zone02..zone08).

---

## Common (obligatorios)

### dc_common_inputs.yaml
**Rol:** helpers globales y parámetros “de producto”.  
**Contiene (aprox.):** input_text (9), input_boolean (14), template (2), etc.  
**Ejemplos de contenido:**
- `input_number.dc_zones_total`
- `input_text.dc_zone01_label..dc_zone08_label`
- toggles globales / notify target

### dc_common_logic.yaml
**Rol:** contratos/checks comunes (onboarding, hw_map/startup).  
**Contiene (aprox.):** scripts (3), automations (1), template (3).  
**Por qué existe separado:** es “lógica de instalación/validación”, no control térmico.

### dc_common_scripts.yaml
**Rol:** scripts comunes + estadísticas comunes.  
**Contiene (aprox.):** scripts (6), input_boolean (21), sensores (≈90) + template (2).  

**Factory reset common (dc_init_fabrica_common) también resetea:**
- input_text.dc_ds_facade_groups_json
- input_text.dc_zones_enabled
- input_text.dc_hwmap_check_zones_csv
- input_text.dc_notify_target
- input_boolean.dc_modo_vacaciones
- input_boolean.dc_modo_ayuda

**Backup/restore common cubre esas entidades.**
**Incluye:**
- factory common
- backup/restore common
- masters (all)
- sensores de stats/runtime comunes

---

## Zone01 (obligatorios)

### dc_zone01_inputs.yaml
**Rol:** inputs/defaults de la zona (lo que el usuario ajusta).  
**Contiene (aprox.):** input_number (≈111), input_boolean (19), input_select (7), group (1), template (6), etc.

### dc_zone01_core.yaml
**Rol:** núcleo del pipeline (cálculo target).  
**Contiene (aprox.):** input_number (21), timers (3), template (12).  
Aquí vive la lógica que produce el target final a aplicar.

### dc_zone01_automations.yaml
**Rol:** loop de aplicación/automatizaciones y scripts operativos.  
**Contiene (aprox.):** automations (20), scripts (27), template (3).  
Ejemplos:
- aplicar consigna periódica
- actualización de “last good”
- timers/overrides de operación

### dc_zone01_sdhb.yaml
**Rol:** integración con BUS/SDHB para la zona.  
**Contiene (aprox.):** input_boolean (3), input_number (2), automations (3), template (2).  
Incluye:
- targets SDHB hacia DS:
  - input_text.dc_zone01_ds_targets_csv (default: 'ds')
  - input_text.dc_ds_facade_groups_json (default: '{}')
  - expansión ds_fXXX -> ds_wX (publisher-side)
- enable toggles SDHB por zona
- consumo winner SDHB para bias
- publish/feedback/heartbeat

### dc_zone01_observability.yaml
**Rol:** diagnóstico/salud/auditoría de la zona.  
**Contiene (aprox.):** automations (12), scripts (3), template (30), sensores (12), etc.  
No es “core”, pero es clave para trazabilidad y debug.

---

## Opcional

### dc_testing_optional.yaml
**Rol:** simulador/tests.  
**Uso recomendado:** solo en desarrollo.

---

## Notas de diseño
- Naming determinista: `dc_zone01..dc_zone08`.
- Si `dc_zones_total > 1`, deben existir las zonas correspondientes (para masters).
- El BUS/SDHB se instala aparte (`suite_dynamic_home_bus_v4_2.yaml`).

## Optional tests
- `yaml_zone_opcionales/dc_zone01_testing_golden_scenarios_optional_v4_2.yaml` (golden record/verify)
- `AppDaemons/dc_zone01_golden_record.py` / `dc_zone01_golden_verify.py`

- `yaml_optional/dc_testing_backup_cycle_optional.yaml` (backup-save-restore cycle)
NOTE: In AppDaemon mode, golden/backup are handled by AppDaemon apps; AppDaemons are not required.
