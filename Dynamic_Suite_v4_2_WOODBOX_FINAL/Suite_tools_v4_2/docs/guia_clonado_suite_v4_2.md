# Paso Final Crítico: Configuración Post‑Clonado en Home Assistant

Una vez hayas clonado los archivos (scripts o manual) y hayas reiniciado Home Assistant, el sistema ya tiene las entidades, pero la “lógica maestra” aún no sabe que existen.
Es obligatorio actualizar los helpers globales para que la suite pase a controlar las nuevas zonas y ventanas.

## A) Dynamic Climate (DC)
* `input_number.dc_zones_total` → total real de zonas (ej. 4).
* `input_text.dc_zones_enabled` → CSV (ej. `zone01,zone02,zone03,zone04`).
* `input_text.dc_hwmap_check_zones_csv` → CSV igual. **Seguridad**: watchdog detecta `REPLACE_*` en clones.

## B) Dynamic Shutter (DS)
* Modelo A: `ds_wX_zone` (ej. `dc_zone02`) y `ds_wX_facade` (ej. `f1`).
* Necesario para grupos BUS `ds_zoneXX_fY_windows` y coordinación de intents.

## C) Dynamic Ventilation (DV)
* Si tu build registra instancias DV en helpers/listas globales, añade `dv_vmc02`/`dv_vmc03`.
* Si DV es instancia única sin registro global, este paso no aplica.

## Verificación rápida
* DC: `dc_zoneXX_hw_replace_count == 0` y `dc_zoneXX_hw_contract_ok == on`.
* DV: `dv_vmc_hw_replace_count == 0` y `dv_vmc_hw_contract_ok == on`.
* DS: `ds_wX_modules_loaded_ok == on` (y `ds_wX_health_summary == OK` si existe).
