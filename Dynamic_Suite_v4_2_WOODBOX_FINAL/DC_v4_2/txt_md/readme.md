# DC (Dynamic Climate) — v4.2 compact (fix_final)

Este paquete implementa Dynamic Climate como un conjunto de *packages* de Home Assistant con naming determinista `dc_zone01..dc_zone08`.

## Archivos (reales)

### Common (obligatorios)
- `dc_common_inputs.yaml`
- `dc_common_logic.yaml`
- `dc_common_scripts.yaml`

### Zone01 (obligatorios)
- `dc_zone01_inputs.yaml`
- `dc_zone01_core.yaml`
- `dc_zone01_automations.yaml`
- `dc_zone01_sdhb.yaml`
- `dc_zone01_observability.yaml`

### Opcional
- `dc_testing_optional.yaml` (simulador/tests), si existe.

## Dependencias
- SDHB/BUS debe instalarse como package independiente (Suite Dynamic Home).
