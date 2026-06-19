# Changelog — Dynamic Home (integración)

Todas las versiones notables de la integración `custom_components/dynamic_home`.
Formato basado en [Keep a Changelog](https://keepachangelog.com/es/1.1.0/) y
[SemVer](https://semver.org/lang/es/).

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
