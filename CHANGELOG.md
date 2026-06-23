# Changelog — Dynamic Home (integración)

Todas las versiones notables de la integración `custom_components/dynamic_home`.
Formato basado en [Keep a Changelog](https://keepachangelog.com/es/1.1.0/) y
[SemVer](https://semver.org/lang/es/).

## [0.20.0] — 2026-06-23

### Added
- **Changeover comunitario (F37)**: soporte para **suelo radiante comunitario a 2 tubos**
  con **cambio estacional**, donde la comunidad envía agua caliente o fría a todo el
  edificio y tú solo abres válvula. Una **dirección de casa** (calor/frío/apagado) que
  las **zonas comunitarias** (las declaradas `central_shared` en F26) **siguen**: ya no
  pides calor cuando llega agua fría.
  - **Detección manual + automática**: un selector **«Changeover (agua)»**
    (`auto/calor/frío/apagado`); en `auto` se deduce de un **sensor de temperatura del
    agua de impulsión** con umbrales (caliente → calor, fría → frío, templada → reposo).
  - **Observabilidad**: sensor de estado de la casa + la tarjeta de cada zona muestra lo
    que **realmente** hace (`hvac_action`: calentando/enfriando/en reposo).
  - **Opt-in / compatible**: sin changeover configurado, las zonas se comportan **igual
    que antes**; las zonas **individuales** ignoran el changeover.
  - Configuración en las opciones de **Zonas** (sensor de agua + umbrales).

### Internal
- Nuevo módulo puro `changeover.py` con tests (`test_changeover.py`) e integración (zona
  community sigue el agua; individual la ignora; sin configurar = back-compat; resolución
  desde sensor + override manual). El `ZonesCoordinator` resuelve y publica
  `DATA_CHANGEOVER` reusando el poll/listeners de F32; DC lo consume en un único punto
  (`_effective_hvac`), sin tocar el motor `decide`. Suite 411→420.

## [0.19.0] — 2026-06-23

### Added
- **Presencia (F32)**: detección de presencia **robusta por zona** que vive en la
  entrada de **Zonas** (junto a modos y confort). Fusiona **tus propias entidades**
  (RNF-6) — **PIR** (rápido), **mmWave** (presencia sostenida: mantiene «Ocupada»
  durante la inmovilidad, no marca «Vacía» por estar quieto en el sofá) y **contacto
  de puerta** — en **Ocupada/Vacía** por zona, y la casa en **Casa/Fuera/Durmiendo**:
  - la casa pasa a **Fuera** solo cuando no queda nadie **y** hubo apertura de puerta
    reciente o los móviles están fuera (nunca por mera inmovilidad);
  - **Durmiendo** dentro de la ventana nocturna sin movimiento (PIR) reciente;
  - publica el estado (`DATA_PRESENCE` + evento) y, con **auto-pilotaje opcional**,
    fija el **modo de la casa** (Casa/Fuera/Durmiendo) — **sin pisar un Boost/Eco
    manual**.
  - Entidades: **binary_sensor de ocupación por zona** + **presencia de casa**.
  - **Editor** en las opciones de Zonas (ajustes de casa: móviles, auto, ventana de
    sueño; y fuentes por zona). Funciona con **cualquier subconjunto** de fuentes.

### Internal
- Nuevo módulo puro `presence.py` con tests (`test_presence.py`) e integración
  (`test_presence_integration.py`: publica estado, entidades, auto-Fuera conduce el
  modo, no pisa Boost). El `ZonesCoordinator` ahora sondea + escucha cuando hay
  presencia. Suite 398→411. *(Diferido: identidad BLE/Bermuda «quién», puerta
  direccional por orden de eventos, publicación por bus / setback directo por zona.)*

## [0.18.0] — 2026-06-23

### Added
- **Emisores y staging (F25)**: una zona de clima mantiene **un solo cerebro** pero
  puede conducir **varios emisores** (p.ej. suelo radiante como primario de calor y un
  split de AC como primario de frío / **apoyo** de calor). Cada emisor declara su terna
  F26 y el dispositivo real que conduce —una entidad **`climate` y/o un `switch`/
  válvula**— y su rol por modo.
  - **Staging primario/apoyo** (`staging.py`): el apoyo arranca cuando el primario se
    queda corto (desviación sostenida) y se retira con histéresis al recuperar.
  - **Conductos compartidos** entre zonas de un grupo (`shared_emitter.py` +
    `SharedEmitterHub`): las zonas hermanas publican su demanda y una zona **dueña**
    reconcilia **una sola consigna** (agregación **ponderada** por defecto; `mean`/
    `priority`/`worst_stuck` disponibles) y conduce la unidad. **Guarda de undershoot**:
    sin rejillas, la unidad **corta** cuando la zona más satisfecha llega a su
    `consigna ∓ margen`, para no sobre-acondicionar estancias pequeñas; **con rejillas
    motorizadas** cada zona regula su caudal y la guarda no aplica.
  - **Editor de emisores** en las opciones de la zona (añadir/editar/borrar), además de
    categorías de ajuste *Staging de emisores* y *Emisor compartido*
    (`zone_demand_weight`, `shared_undershoot_margin`).
  - **Compatibilidad:** una zona sin lista de emisores declarada se comporta **idéntica
    a antes** (un solo termostato), REQ-EMI-7.

### Internal
- Nuevos módulos puros `emitters.py`, `staging.py`, `shared_emitter.py` con tests
  (`test_emitters`/`test_staging`/`test_shared_emitter`) e integración (staging
  arma/retira, conducto compartido reconcilia + guarda, editor). El motor
  `dc_engine.decide` no se toca; el staging/reconciliación son post-decisión. Suite
  371→398. *(Diferido: canal de compresor por-emisor en F09; prioridad de cola/bypass
  de confort.)*

## [0.17.0] — 2026-06-23

### Added
- **Anti-pico / reparto de cargas eléctricas (F03)**: árbitro de casa **opt-in**
  (switch "Peak limiting") que evita disparar el ICP limitando los **arranques
  simultáneos** y **escalonándolos** (~10 s). Modelo puro `peak.py` (`PeakLoadHub`),
  espejo del agregado de anti-ciclado, con **dos canales** independientes: cargas
  **sostenidas** de calefacción eléctrica (el slot vive mientras la zona demanda) e
  **inrush transitorio** de motores de persiana (pulso que expira tras el recorrido).
  Presupuesto por **nº de cargas** (`peak_max_zones`) o por **vatios**
  (`peak_max_power_w`, medidor real o estimación). En clima se engancha solo cuando
  el **perfil F26** dice que la carga es eléctrica (`peak`) y **no** comunitaria; en
  persianas escalona los arranques masivos (la persiana mantiene su posición y
  reintenta al ciclo siguiente; el slew sigue dando forma al movimiento). Observable
  vía `peak_hold`/`peak_reason` (clima) y `peak_reason`/`peak_deferred_pos` (persiana).

### Changed
- **Anti-ciclado corto (F09) cableado al perfil F26**: la protección de compresor
  solo participa en el agregado cuando la instalación declara **compresor**
  (aerotermia/geotérmica/aire-aire **individual**); en gas, eléctrica directa o
  **fuente comunitaria** queda OFF aunque el switch esté activo. Sin instalación
  declarada se mantiene el opt-in previo (compatibilidad). Con esto se cierra el
  criterio de aceptación de F26 «con fuente comunitaria, F03/F09 no actúan».

### Internal
- Nuevo módulo puro `peak.py` con tests (`test_peak.py`) e integración (gating de F09
  por generador/comunitaria; escalonado de N zonas eléctricas; escalonado de persianas).
  Suite 357→371.

## [0.16.0] — 2026-06-23

### Added
- **Tipo de instalación (F26) · capa de declaración**: cada zona de clima declara
  su instalación en **3 dimensiones independientes** — **Generador** (aerotermia
  aire-agua, geotérmica, aire-aire/AC, calderas de gas/gasoil/biomasa/leña,
  eléctrica directa) × **Distribución** (individual / central compartida) ×
  **Emisión** (suelo/techo radiante, radiadores, toallero, convectores, conductos
  calor/frío, radiante refrescante, fancoil, split). El carácter **central vs
  individual** es una **dimensión aparte** del generador: gas, pellets, gasoil y
  aerotermia pueden ser centrales o individuales; la **eléctrica directa** y el
  **aire-aire** son **siempre individuales** (el asistente omite ese paso).
  De la terna se deriva un **perfil** (`community`/`compressor`/`peak`) que F09/F03
  consumirán: *comunitaria* solo abre válvula (sin compresor ni pico), una **bomba
  de calor individual** activa compresor y pico, las **combustiones** ninguno, y la
  **eléctrica** solo pico. Elegir la terna **precarga defaults** coherentes por
  **inercia** (más lead y anti-ciclado más largo en suelo radiante; al revés en
  fancoil), editables luego. Asistente de 3 pasos en las opciones de clima, sensor
  diagnóstico **"Instalación"** (estado = la terna; atributos = los flags) y modelo
  puro `install.py`. *(El **gating real** de F09/F03, los emisores —F25— y la opción
  "personalizado" quedan para los siguientes ciclos.)*

### Internal
- Nuevo módulo puro `install.py` (catálogo + `profile` + `defaults` por inercia) con
  tests (`test_install.py`) e integración (asistente, perfil, sensor; el generador
  forzado individual salta el paso de distribución). Suite 343→357.

## [0.15.0] — 2026-06-22

### Added
- **Anti-ciclado corto (F09)**: protección de compresor **opt-in** (switch
  "Anti short-cycle" en cada zona de clima) con **min ON**, **min OFF** y **máx
  arranques/hora** (por defecto 6). Clave: en aerotermia/bomba de calor el
  **compresor es compartido**, así que el anti-ciclado actúa sobre el **agregado**
  (un hub único de casa): un arranque es la primera zona que enciende con todas
  apagadas y una parada la última que se apaga, de modo que el flapping de una zona
  **no cuenta como arranque** si otra mantiene el compresor despierto. Vigila el
  ON/OFF que **DC manda** al termostato: cuando el agregado retiene un arranque
  (min OFF / máx arranques) o sostiene el min ON, la zona conduce el termostato a
  **OFF**. **La seguridad manda** (REQ-CYC-3): ante condensación/ventana/orden de
  seguridad, cede y apaga aunque no se cumpla el min ON. Tiempos configurables.
  Helper puro `anticycle.py`. *(Gating por instalación —F26— y agrupación fina por
  compresor —F25— quedan para más adelante; por ahora un grupo único de casa.)*

### Internal
- Nuevo módulo puro `anticycle.py` (estado de compresor + hub agregado) con tests
  dedicados; hub compartido en `hass.data` como el SDHB.
- Suite de 343 tests; `ruff` + `hassfest` + HACS en verde.

## [0.14.0] — 2026-06-22

### Added
- **Confort↔Economía (F23)**: nuevo **mando por presets** `Eco / Equilibrado /
  Confort` que escala de forma **coherente** la agresividad del sistema en clima y
  ventilación a la vez — bandas/consignas, atenuación nocturna, agresividad del lead
  y umbrales de ventilación. **Global con override por zona**, exactamente como el
  modo de la casa (F01): dos `select` en la entrada de Zonas ("Confort casa" +
  "Confort {zona}", con `auto` heredando). Los presets son **deltas integrados
  predecibles** (no editables): `Eco` ensancha la banda, atenúa más de noche, suaviza
  el lead y ventila menos; `Confort` al revés; `Equilibrado` no toca nada. **Ligado a
  F01**: con el mando en `Equilibrado`, el modo `Eco` de la casa aplica el preset
  económico (una elección explícita del mando siempre manda). Helper puro
  `comfort.py`.

### Internal
- Nuevo módulo puro `comfort.py` (resolución por ámbito + deltas DC/DV) con tests
  dedicados; reutiliza la maquinaria de F01 (`coordinator_zones.publish_modes`,
  `select.py`, `zones.scope_for_module`).
- Suite de 334 tests; `ruff` + `hassfest` + HACS en verde.

## [0.13.0] — 2026-06-22

### Added
- **Programador semanal (F21)**: nuevo **editor de programación por días** (hasta
  **4 tramos/día**, por día de la semana) en las opciones de la VMC y de cada zona
  de clima. La **estética/mecánica es común**, pero **cada entrada tiene su propia
  programación independiente**:
  - **Clima (DC)**: el tramo fija la **consigna BASE absoluta** (no un offset); los
    biases del motor siguen aplicándose encima (Base → biases → TARGET). Las
    vacaciones siguen teniendo prioridad sobre la programada.
  - **VMC (DV)**: el tramo fija la **velocidad/encendido base** — `Off` apaga la
    franja (como el horario simple), `V1/V2/V3` actúan de **suelo** sobre la
    velocidad automática; el cap de horas de silencio y los modos siguen mandando.
  - El perfil se activa con el switch **"Programador"** (en DV reaprovecha el switch
    de horario; si el perfil semanal está vacío, sigue valiendo el horario on/off
    simple por entidades `time`). Helper puro `schedule.py`, editor que reutiliza el
    patrón del editor de zonas (menú de 7 días → tramos, con copiar-a-días). Sensor
    diagnóstico **"Programación"** con el valor del tramo activo y el próximo cambio.
    Hook de presencia (F32) previsto para el futuro.

### Internal
- Nuevo módulo puro `schedule.py` (modelo semanal: tramos, valor activo con
  continuidad en medianoche) con tests dedicados.
- Suite de 323 tests; `ruff` + `hassfest` + HACS en verde.

## [0.12.0] — 2026-06-22

### Added
- **Energía por módulo (F06)**: la VMC, las zonas de clima y las persianas exponen
  ahora un sensor de **energía (kWh)** (`device_class: energy`,
  `state_class: total_increasing`) que entra directo en el **panel de Energía** de
  Home Assistant y sobrevive a reinicios (`RestoreSensor`). Cada módulo usa un
  **medidor de potencia real** si se configura (nuevo campo opcional "Power meter"
  en los tres asistentes) y, si no, una **estimación**: la VMC integra la potencia
  por velocidad (`V1/V2/V3`, tunables), el clima la potencia mientras pide
  calor/frío (reaprovecha la señal de demanda real de F27), y la persiana estima la
  energía (marginal) de cada movimiento del motor (`recorrido completo` × Δ%). Solo
  energía por ahora; el coste (€) queda para un ciclo posterior.
- **Sombreado geométrico real (F15)**: nuevo switch opt-in **"Geometric shading"**
  por persiana. Cuando está activo, la rama de protección solar de verano deja de
  usar el escudo fijo por "impacto" y calcula la **penetración real del sol en el
  suelo** (geometría de alféizar, alto de ventana, voladizo, azimut y profundidad
  de sala) para bajar la persiana **solo lo justo** —por pasos— y proteger los
  `target_penetration_m` de suelo. Con sol alto apenas cierra; con sol de tarde
  bajo cierra más. Con el switch apagado (por defecto), el comportamiento es
  idéntico al actual (`summer_solar_shield`).

### Internal
- Nuevo módulo puro `energy.py` (helpers de integración kWh) con tests dedicados;
  geometría de penetración en `ds_engine` (`solar_penetration_m`/`geo_shade_pos`).
- Suite de 304 tests; `ruff` + `hassfest` + HACS en verde.

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
