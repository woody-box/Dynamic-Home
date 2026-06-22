# Changelog — Dynamic Home (integración)

Todas las versiones notables de la integración `custom_components/dynamic_home`.
Formato basado en [Keep a Changelog](https://keepachangelog.com/es/1.1.0/) y
[SemVer](https://semver.org/lang/es/).

## [0.11.3] — 2026-06-22

### Added
- **Aviso de filtro por Repairs (F08)**: al cruzar el umbral de vida del filtro, la
  VMC crea ahora una incidencia en **Ajustes → Reparaciones** (`filter_due`,
  no-fixable + `learn_more_url`) además del evento `dynamic_home_filter_due` que
  ya emitía. La incidencia se **borra** al pulsar "Reset filter hours" (o el
  servicio `dynamic_home.reset_filter`) y al descargar la entrada. Completa F08
  (el número "Vida del filtro (h)", el sensor de % y el botón de reset ya existían).

### Docs
- F08 y **F10** (servicios + eventos, ya estaba completo: 5 servicios con
  `services.yaml`/traducciones + 4 eventos) marcados como implementados.

### Internal
- Suite de 283 tests; `ruff` + `hassfest` + HACS en verde.

## [0.11.2] — 2026-06-22

### Added
- **Explicador de conflictos del bus (F02)**: cada **consumidor** del SDHB (cada
  VMC, cada persiana y DC en su self-bias) expone un `sensor` con el **intent
  ganador** como estado y el **porqué** en atributos —`source`, `priority`,
  `candidates`, `reason`, `target`, `ttl_remaining_s`— más el **aspirante**
  (`runner_up`/`runner_up_priority`, el segundo intent de mayor prioridad que
  pierde, sin la lista completa de descartados). Todos cuelgan de un **dispositivo
  central** "Dynamic Home · Bus". `hub.explain()` devuelve ahora el TTL restante
  del ganador y el runner-up (orden estable que coincide con `winner()`). Emite
  `dynamic_home_conflict` al cambiar el ganador; solo estado actual (sin logbook).

### Internal
- Suite de 281 tests; `ruff` + `hassfest` + HACS en verde.

## [0.11.1] — 2026-06-22

### Added
- **Repairs sobre `degraded` — transversal DV·DS·DC (F07)**: un módulo cuya
  fuente **requerida** está configurada pero **ausente/renombrada u obsoleta**
  (`unavailable`/`unknown`) de forma sostenida (> 5 min) crea una incidencia en
  **Ajustes → Reparaciones** que **lista las fuentes que faltan**, y emite el
  evento `dynamic_home_degraded` al instante (en la transición). La lógica se
  factoriza en un mixin `DegradedTracker` (`repairs.py`) compartido por los tres
  módulos: **DV** vigila los relés `sw_pwr/v2/v3` + `co2`/`pm25`; **DS** el
  `cover`; **DC** la Tª interior (igual que antes). Cada módulo expone ahora el
  `binary_sensor` "Degradado". La incidencia se borra al recuperarse la fuente o
  al descargar la entrada.

### Notes
- Incidencia **no-fixable** + `learn_more_url` (el texto remite a *Dispositivos y
  servicios → Configurar*); el **botón que reabre el config flow** queda diferido.

### Internal
- Suite de 280 tests; `ruff` + `hassfest` + HACS en verde.

## [0.11.0] — 2026-06-22

### Added
- **Modos de la casa (F01)**: un modo `Home/Away/Sleep/Boost/Eco` que sesga todos
  los módulos a la vez, **por ámbito** (modo casa + **override por zona**, sobre la
  jerarquía de F24). En la entrada de Zonas: un `select` "Modo casa" + un "Modo
  <zona>" por zona (restaurados). La entrada resuelve el **modo efectivo por
  módulo** y lo publica; **DV** capa su velocidad por modo (Sleep/Eco/Away,
  configurable, con excepción de seguridad por aire crítico) y **Boost** fuerza V3;
  **DC** entra en **vacación** en `Away` (sustituye/añade al switch, existe aunque
  DC no esté). Evento `dynamic_home_mode_changed`; la capa de modo
  (`effective_from_published`) queda lista para módulos futuros (F25).

### Notes
- Pendiente (anotado): pieza de **horario** de la jerarquía (es F21), efecto de
  modo en DS y override por **grupo** (v0.11.0 cubre zona).

### Internal
- Suite de 277 tests; `ruff` + `hassfest` + HACS en verde.

## [0.10.0] — 2026-06-22

### Added
- **Zonas y grupos — estructura (F24)**: jerarquía **propia** zona → grupo → casa
  (no Areas de HA) en una **entrada singleton** "Dynamic Home · Zonas" con un
  **editor de árbol** en sus opciones (crear zonas/grupos, asignar módulos a zonas
  y zonas a grupos, con validación 1 módulo→1 zona y 1 zona→1 grupo). El árbol se
  persiste y se **publica** para que otros módulos resuelvan el ámbito de cada
  módulo (`scope_for_module`); sensor diagnóstico de la jerarquía. **Alcance: solo
  estructura** — el **modo/perfil por ámbito llega con F01**, que consumirá esto.

### Internal
- Suite de 269 tests; `ruff` + `hassfest` + HACS en verde.

## [0.9.0] — 2026-06-22

Primer **módulo nuevo** desde el port: una capa meteo propia. (Salto de versión
menor por estrenar un módulo.)

### Added
- **Dynamic Weather (F33)** — nuevo módulo `weather`, capa meteo **resiliente y
  agnóstica** que **no obtiene datos** sino que agrega **varias fuentes en cascada
  con fallback**: hasta 3 entidades `weather.*` priorizadas (Open-Meteo sin clave,
  OWM, met.no, AEMET…) + **sensores crudos** de respaldo. Expone:
  - una entidad **`weather` proxy** que espeja la fuente activa y **reenvía
    `get_forecasts`** → DC (forecast bias) y free-cooling la consumen transparente
    y con fallback;
  - un **`binary_sensor` de alerta** derivada (condición peligrosa / viento /
    precipitación) consumible por **DS (F17)**;
  - un **sensor de fuente activa** (diagnóstico, con `since`) y evento al cambiar.
  Caducidad y umbrales de alerta configurables. **Sin APIs/keys** en la
  integración (RNF-6). El forecast solo está disponible si la fuente activa es una
  entidad `weather`.

### Internal
- Suite de 263 tests; `ruff` + `hassfest` + HACS en verde.

## [0.8.4] — 2026-06-22

### Added
- **DV · Campana extractora coordinada (F35)**: cuando el **PM2.5 interior** sube
  (cocinar), la campana se enciende/sube para limpiar el aire (umbral por
  velocidad con histéresis), complementando a la VMC. Para campanas de **3 relés
  (uno por velocidad)** se expone una entidad `fan` "Campana" (auto + manual) con
  **driver break-before-make** (nunca dos velocidades a la vez) y un **vigilante
  de interlock** que corrige si dos relés quedan activos. Respeta *observe*.
  Configurable (categoría *Campana extractora*). _Se recomienda además un
  interlock hardware: el software coordina, no sustituye protecciones físicas._

### Internal
- Suite de 257 tests; `ruff` + `hassfest` + HACS en verde.

## [0.8.3] — 2026-06-22

### Added
- **DS · Avisos meteo / protección anticipatoria (F17)**: hasta 3 `binary_sensor`
  de alerta (genérica / granizo / viento), cada uno con su **posición de
  protección**; ante una alerta la persiana se protege **antes** del fenómeno y
  mantiene la protección un **hold** configurable tras despejarse. Si hay varias,
  gana la más protectora. Rama `meteo_alert` (protegida, por encima de
  lluvia/viento; el override manda). **Agnóstica de proveedor**: el dato meteo lo
  aporta el usuario (Meteoalarm / Open-Meteo / template) o el futuro módulo
  Weather (F33) — sin APIs dentro de la integración. Configurable (categoría
  *Avisos meteo*).

### Internal
- Suite de 251 tests; `ruff` + `hassfest` + HACS en verde.

## [0.8.2] — 2026-06-22

### Added
- **DS · Aislamiento nocturno estacional (F16)**: switch *opt-in* por zona que, de
  noche (sol bajo el horizonte), aplica la estrategia según el **modo del climate**:
  en `heat` **cierra para aislar**; en `cool` **abre para purgar** la masa térmica
  si el exterior está más fresco, o **cierra para protegerla** en noche cálida.
  Rama `night_insulate` en la cascada (cede a override/lluvia/privacidad);
  autocontenido (no toca el free-cooling base). Configurable (categoría
  *Aislamiento nocturno*).

### Internal
- Suite de 247 tests; `ruff` + `hassfest` + HACS en verde.

## [0.8.1] — 2026-06-22

### Added
- **DS · Apertura gradual al amanecer (F19)**: switch *opt-in* por zona que, al
  amanecer (cruce de elevación del sol), sube la persiana **por pasos**
  (`dawn_step_pct` cada `dawn_step_min` hasta `dawn_target_pct`) en lugar de
  abrirla de golpe. Cede a override/lluvia/privacidad, **solo abre** (no pelea con
  free-cooling ni con el usuario) y respeta si ya estaba abierta. Configurable
  (categoría *Amanecer gradual*).

### Internal
- Suite de 244 tests; `ruff` + `hassfest` + HACS en verde.

## [0.8.0] — 2026-06-22

### Added
- **Espejos de hardware para dashboards (F36)**: opción `expose_mirrors` por zona
  (off por defecto) que expone un sensor **espejo estable por rol de entrada**
  (temperatura, humedad, CO₂, viento, …) en DC/DV/DS. El dashboard apunta a la
  entidad de la integración (`unique_id` por `entry`+rol), así **reemplazar un
  sensor físico solo exige reconfigurar la entrada**, sin tocar dashboards. El
  espejo copia valor/unidad/`device_class`/`state_class` y sigue al origen;
  cambiar el toggle recarga la entrada.

### Internal
- Suite de 239 tests; `ruff` + `hassfest` + HACS en verde.

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
