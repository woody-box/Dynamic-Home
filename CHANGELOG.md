# Changelog — Dynamic Home (integración)

Todas las versiones notables de la integración `custom_components/dynamic_home`.
Formato basado en [Keep a Changelog](https://keepachangelog.com/es/1.1.0/) y
[SemVer](https://semver.org/lang/es/).

## [0.5.0] — 2026-06-20

### Added
- **DC · Adaptive Lead**: lazo opt-in que aprende la inercia térmica de cada zona
  (tasa de calentamiento, overshoot y retardo) de ciclos reales y autocalibra la
  anticipación. Sensores `RestoreSensor` de los valores aprendidos + `binary_sensor`
  "Degradado" que pausa el aprendizaje si falta un sensor núcleo.
- **Modo observación (dry-run)** por módulo: calcula y publica al bus pero no toca
  hardware (switch "Observe only").
- **DV · OFF real** (preset manual `off` que el motor no revierte) y **override con
  temporizador** + auto-reversión a auto; sensores de estado y minutos restantes.
- **Configuración por UI completa**, agrupada por categoría (DC 11 · DS 5 · VMC 8),
  con los defaults viviendo solo en los dataclasses del motor (`options_spec.py`).

### Changed
- **VMC · seguridad de relés**: secuencia break-before-make (nunca V2+V3 a la vez)
  y apagado seguro de los relés de velocidad antes de cortar alimentación.
- **DS · persiana**: la entidad reporta la posición física real del cover; el
  objetivo calculado pasa a atributo `target_position`.

### Internal
- Renombrado `engine.py → dv_engine.py`; `coordinator.py` partido por dominio.
- CI: lint (ruff) + validación (hassfest); orden de claves del manifest corregido.
- 129+ tests, 0 flake.

## [0.4.0] — 2026-06-19

### Changed
- **Tooling/calidad**: CI con ruff + hassfest + HACS; `ruff.toml`.
- **Refactor** de mantenibilidad (engines y coordinators por dominio).
- La suite YAML original v4.2 sale de `main` a la rama `archive/v4.2-source`.

## [0.3.0] — 2026-06-19

Primera versión pública instalable por HACS. Port de la suite YAML original
(DC/DV/DS + bus SDHB) a una integración nativa de Home Assistant.

### Added
- **Tres módulos coordinados**, cada uno como una entidad nativa:
  - **DC · Dynamic Climate** → `climate` (consigna por zona: base día/noche,
    bias exterior, límites y cuantización, override manual).
  - **DV · Dynamic Ventilation** → `fan` (velocidad V1/V2/V3 por IAQ con EMA e
    histéresis, free-cooling, dry mode, cap por AQI, anti-flapping, gate de
    horario/permiso, failsafe con lockout, boost por ducha, umbrales adaptativos).
  - **DS · Dynamic Shutter** → `cover` (cascada override → lluvia → privacidad →
    free-cool → solar shield → invierno; caps de viento, bus y slew; impacto
    solar geométrico).
- **Bus SDHB en memoria** (`bus.py`, puro) compartido por todas las instancias,
  con arbitraje por prioridad y targets de fachada.
- **DC como cerebro**: publica `request_solar_gain` (calor) / `request_solar_shield`
  (frío) que DS y DV consumen.
- **Targeting solar dinámico**: DC calcula qué fachadas ilumina el sol y dirige la
  intención solo ahí, re-dirigiendo al moverse el sol.
- **Ángulo de aceptación por fachada** (`facade_span_deg`): fachadas estrechas o
  amplias según la geometría real.
- **Multi-instancia**: varias zonas, persianas y VMC coordinadas automáticamente.
- **Config flow** con menú (VMC / persiana / clima) y options flow (umbrales IAQ).
- Traducciones **inglés** y **español**.
- Suite de **88 tests** (lógica pura + integración en HA) y **CI** en cada push.
- Empaquetado **HACS** (`hacs.json`, layout en la raíz).

### Notes
- Requiere Home Assistant ≥ 2024.3.
- La lógica de decisión vive en módulos puros sin dependencias de HA
  (`*_engine.py`); los *wrappers* solo traducen estado.
- La suite YAML original se conserva en `Dynamic_Suite_v4_2_WOODBOX_FINAL/` como
  referencia/legado.
