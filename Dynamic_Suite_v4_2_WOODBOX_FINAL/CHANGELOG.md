# Changelog

Este proyecto sigue un changelog "limpio": se documenta a partir de la primera release pública v4.2 (sin historia anterior).

## [v4.2] — Stable

### Added
- Suite completa v4.2 (DC/DV/DS/SDHB) con backups y golden vía AppDaemon.
- Paquete `suite_tools` para clonado masivo.
- Tests opcionales (features / backup-cycle / recovery / golden scenarios) por módulo.

### Changed
- Rutas de backup/golden unificadas bajo `/config/dynamic_suite/...`.
- Documentación consolidada (manual suite+SDHB, manuales DC/DV/DS).

### Fixed
- Correcciones P0/P1 (contratos, wiring, YAML, documentación) para garantizar instalación mínima estable.

## [v4.2-p2] — Stable (P2)

### Added
- DV: `input_number.dv_vmc_startup_grace_s` (startup grace configurable; default 120s).
- SDHB: `input_text.sdhb_priority_map_json` (priority map configurable en JSON, con fallback seguro).

### Changed
- SDHB: nota documental sobre slots reservados para escalado (ds_w9..w12, dv_vmc02/dv_vmc03).

