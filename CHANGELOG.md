# Changelog — Dynamic Home (integración)

Todas las versiones notables de la integración `custom_components/dynamic_home`.
Formato basado en [Keep a Changelog](https://keepachangelog.com/es/1.1.0/) y
[SemVer](https://semver.org/lang/es/).

## [0.7.1] — 2026-06-22

Release correctivo. El tag `v0.7.0` se creó apuntando por error al commit de
`v0.6.0` (antes de mergear la sub-fase 1b), por lo que empaquetaba el código de
0.6.0. `v0.7.1` re-publica desde `main` el contenido previsto para 0.7.0.

### Fixed
- **Versión empaquetada**: `manifest` y tag coherentes con el código realmente
  mergeado (F27/F22/F20/F31 + README de adopción). Sin cambios funcionales
  respecto al contenido descrito en [0.7.0].

## [0.7.0] — 2026-06-22

Cierre de la sub-fase 1b (clima, DC) y reescritura del README orientada a la
adopción.

### Added
- **DC · Señal de demanda real (F27)**: usa el estado real de relé/potencia,
  helpers de demanda o `hvac_action` (prioridad c > b > a) para alimentar el
  Adaptive Lead, con *fallback* a la inferencia previa; `binary_sensor` "Demanda
  real". Convive con un termostato de backup sin combatirlo.
- **DC · Índice de moho (F22)**: índice "horas sobre umbral de HR con
  decaimiento" (persistido, con histéresis) que avisa (Repairs + evento) y dispara
  secado por **dos vías**: petición al bus de DV (respetando su gate `dp_diff`) y
  un **deshumidificador** opcional por zona.
- **DC · Ventana abierta inferida (F20)**: sin sensor de ventana, una caída de
  temperatura coherente con la demanda apaga la zona (`off_window_inferred`) con
  confirmación/recuperación/timeout; `binary_sensor` "Ventana (inferida)".
- **DC · Aviso de espacio adyacente (F31)**: advisory por zona (terraza/galería):
  en `heat` avisa para abrir (ganancia solar), en `cool` alarma si la puerta está
  abierta con el adyacente caliente. Evento + sensor enum.

### Docs
- **README de adopción** en inglés (primario) + `README.es.md` en español:
  para quién es/no es, diagrama de arquitectura (Mermaid), tabla de estado,
  arranque seguro, limitaciones y seguridad ampliada.
- Nuevo **`docs/EXAMPLES.md`** con 3 ejemplos mínimos (VMC 3 velocidades, zona de
  clima, persiana por fachada).
- Nota de backlog **F36** (sensores espejo de hardware para dashboards estables).

### Internal
- Suite de 236 tests; `ruff` + `hassfest` + HACS en verde.

## [0.6.0] — 2026-06-21

Cierre de la sub-fase 1a (ventilación, DV) y de la infraestructura transversal
de servicios/eventos/diagnóstico.

### Added
- **DV · Ventilación anticipatoria (F11)**: detector de pendiente (derivada de
  CO₂/PM2.5) que pre-eleva la velocidad antes de cruzar umbrales, con histéresis
  on/off y ventana de mantenimiento.
- **DV · Secado por punto de rocío (F13)**: gate de anticondensación que solo
  ventila para secar si el aire exterior es realmente más seco (margen `dp_diff`
  + histéresis), evitando meter humedad.
- **DV · Horas de silencio (F12)**: cap nocturno de velocidad (OFF/V1/V2) en una
  franja diaria, con **excepción de seguridad** si CO₂/PM2.5 superan un umbral
  crítico (salud > silencio).
- **DV · Boost temporizado (F14)**: servicio `dynamic_home.boost` que fuerza V3
  N minutos y **auto-revierte**; re-invocar reinicia la cuenta.
- **DV · Eficiencia del recuperador (F28)**: sensor diagnóstico de rendimiento
  (3 sondas opcionales) válido en calor y frío, con estado
  `recovering`/`bypass`/`idle`.
- **DV · IAQ extendido (F30)**: **VOC como observación** (sensor diagnóstico que
  no actúa); solo CO₂/PM2.5 mueven la velocidad.
- **DV · Vida del filtro (F08)**: sensor de vida restante + evento "filtro due"
  con histéresis (una vez por cruce) y servicio de reset.
- **Servicios y eventos nativos (F10)**: `reset_learning`, `set_observe`,
  `reset_filter`, `recalibrate`, `boost`.
- **Explicador de conflictos del bus (F02)**: sensores + eventos que exponen el
  ganador, la fuente, la prioridad y los candidatos del bus SDHB.
- **Aviso de degradado DC sostenido (F07)**: incidencia de Repairs cuando una
  zona DC queda degradada de forma sostenida.

### Changed
- **DV · robustez de CO₂**: suelo de cordura que rechaza lecturas físicamente
  imposibles (sensor desconectado/erróneo) antes de decidir.

### Internal
- Endurecido un test flaky del sensor de vida del filtro (resolución por
  `entity_registry` en vez de slug fijo).
- Endurecida la spec de F25 (agregación ponderada + guarda de undershoot en
  conductos compartidos sin zonificar) — solo documentación.
- Suite de 212 tests, 0 flake; `ruff` + `hassfest` + HACS en verde.

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
