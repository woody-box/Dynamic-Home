# Changelog — Dynamic Home (integración)

Todas las versiones notables de la integración `custom_components/dynamic_home`.
Formato basado en [Keep a Changelog](https://keepachangelog.com/es/1.1.0/) y
[SemVer](https://semver.org/lang/es/).

## [0.41.0] — 2026-06-26

### Added
- **Persiana · escudo térmico (calor ambiente)**: en modo **frío**, cuando **fuera hace más
  calor que dentro** (por `hot_delta`) pero el sol **ya no da** en esa fachada, la persiana
  **deja de abrirse** y se mantiene en una posición de protección en vez de dejar entrar el
  calor de la terraza/ambiente. Cubre el hueco que tenía la protección solar (que solo
  actuaba con **sol directo**): al irse el sol, la persiana se abría aunque siguiera haciendo
  calor fuera. Posición configurable **`heat_shield_pct`** en *Posiciones de persiana*, por
  defecto **0 %** (cerrada del todo); súbela a 20/40 si quieres algo de luz. Respeta
  override/lluvia/viento/alertas como el resto de la cascada, y **cede ante el sol directo**
  (ahí sigue mandando el sombreado solar/geométrico).

### Internal
- `DsConfig.heat_shield_pct` (def. 0) + rama `summer_heat_shield` en `decide_cover`, tras
  `shield_ok` (gated `is_cool and temps_ok and t_out >= t_in + hot_delta`); no afecta a
  persianas sin clima/cambio estacional ni sin sensores de Tª (back-compat). Categoría
  `positions` (EN/ES, paridad). Tests: motor (cierra sin sol; configurable; no si no hace
  más calor; cede al sol directo; solo en frío) + integración (frío + calor + sol fuera de
  fachada → `summer_heat_shield` a 0 %).

## [0.40.0] — 2026-06-26

### Added
- **Persiana · sensor de posición real**: cada persiana expone ahora un sensor de
  diagnóstico **Position** (`%`) que **re-publica la posición física real** leída del
  `cover` (`current_position`). La entidad `cover` ya la mostraba, pero como cover no es un
  sensor numérico graficable; este sensor sí entra en el histórico/estadísticas y es fácil de
  usar en plantillas. Como atributos lleva el **objetivo** que manda la cascada DS (`target`)
  y el **motivo** (`reason`), así de un vistazo ves lo que la persiana *es* frente a lo que el
  sistema *quiere* y por qué. `unknown` si el cover no reporta posición.
- **Sombreado geométrico (F15) · separación del alero**: nuevo parámetro **Separación del
  alero (cm)** (`overhang_offset_cm`) en *Geometría de ventana*. Es la **distancia vertical
  entre el alero/voladizo y el borde superior de la ventana**: el alero solo da sombra al
  cristal por debajo de esa separación, así que un alero alto (p. ej. el tejado de una terraza
  cubierta) sombrea mucho menos que uno a ras de la ventana. Afina tanto el `solar_impact`
  como el modelo de penetración (`solar_penetration_m`). `0` = a ras (comportamiento previo).

### Internal
- `DsConfig.overhang_offset_cm` resta del alto de sombra del voladizo (`max(0, overhang·tan(el)
  − offset)`) en `solar_impact`/`solar_penetration_m`; `DsPositionSensor` (reusa `_Base`,
  `unique_id={entry}_position`). Tests: motor (offset reduce sombra en impacto y penetración) +
  integración (sensor reporta el real con `target`/`reason`; `unknown` sin feedback). Etiquetas
  EN/ES en la categoría `geometry` (paridad strings/en/es).

## [0.39.0] — 2026-06-25

### Added
- **Reconfigurar entidades sin borrar el módulo**: nuevo paso **Editar entidades / hardware**
  en *Configurar* (opciones) de cada módulo (VMC, persianas, clima, meteo, energía). Re-muestra
  el formulario de entidades **precargado** con lo que ya tienes y permite **añadir, cambiar o
  quitar** cualquiera (sensores, relés, recuperador… p. ej. los relés de la campana que se te
  olvidaron). Al guardar actualiza la config y **recarga** el módulo para que surta efecto —
  **sin borrar ni volver a añadir**, conservando opciones e histórico. Compatible con HA 2024.3
  (el «Reconfigurar» nativo necesita 2024.4+).

### Internal
- `_HARDWARE_SCHEMA` (reusa los schemas de alta) + `async_step_hardware` en el options-flow
  (preserva datos no-schema, borra opcionales vaciados, `async_update_entry` + reload);
  «hardware» en el menú; paso `hardware` con la **unión** de etiquetas de campos de todos los
  módulos (EN/ES, paridad). Test (añadir campana + quitar opcional + preservar módulo).

## [0.38.0] — 2026-06-25

### Added
- **Recuperador (F28) · 4ª temperatura + exponer todas**: nuevo campo opcional **Temp.
  expulsión HRV** (aire expulsado al exterior) en la config de la VMC. El sensor
  **Recuperator efficiency** ahora expone **todas** las temperaturas configuradas como
  atributos (`supply`, `intake`, `extract`, `exhaust`) junto al rendimiento (η) y su
  estado (recovering/bypass/idle). La 4ª sonda **no** entra en el cálculo de η (sigue
  siendo impulsión/admisión/extracción); se expone para observabilidad. También disponible
  como **mirror** opt-in (`Hardware mirrors`) para graficar cada temperatura por separado.

## [0.37.0] — 2026-06-25

### Added
- **Umbrales adaptativos · visibles para comparar**: con *Adaptive thresholds* activo, el
  ventilador expone como **atributos** los umbrales que ha **aprendido** (`adaptive_co2_v2`,
  `adaptive_co2_v3`, `adaptive_pm_v2`, `adaptive_pm_v3` — p90/p95 de tu histórico) y el
  número de muestras acumuladas (`adaptive_samples`). Así puedes **compararlos con los
  fijos** y ver cómo convergen antes de fiarte. `None` hasta que hay muestras suficientes.

## [0.36.1] — 2026-06-25

### Fixed
- **Paso "Baños" sin etiqueta en el menú de opciones de la VMC**: el paso existía (F13,
  v0.36.0) pero faltaba su entrada en el menú, así que aparecía **en blanco** en *Configurar*
  y era fácil no encontrarlo. Añadida la etiqueta **Baños (boost de ducha)** / *Bathrooms
  (shower boost)* en EN y ES.

## [0.36.0] — 2026-06-24

### Added
- **Ventilación (F13) · varios baños para el boost de ducha**: en las opciones de la VMC,
  un nuevo paso **Baños** permite declarar hasta **6 baños**, cada uno con **nombre** (p. ej.
  "Baño pasillo") y su **sensor de humedad**. El boost de ducha vigila la **mayor subida de
  humedad** entre todos, así una ducha en **cualquier** baño lo dispara; y el atributo
  `shower_bathroom` del ventilador indica **qué baño** lo activó. Rellenas solo las filas
  que tengas. **Back-compat**: el campo único *Humedad baño* de siempre sigue funcionando.

### Internal
- `coordinator_dv._bathrooms()` (lista de opciones `bath_hum_/bath_name_1..6`, fallback al
  `hum_bath` legacy) + `_rh_delta` toma el máx y guarda `shower_bathroom`; `shower_enabled`
  se activa con cualquier baño; atributo en `fan.py`. Paso de opciones `bathrooms` +
  traducciones EN/ES. Tests (máx + nombre; legacy; el paso guarda/borra). Suite 469→472.

## [0.35.5] — 2026-06-24

### Fixed
- **Campo `hum_in` sin etiqueta en la config de VMC**: el selector de **humedad interior**
  (opcional, alimenta el punto de rocío / modo secado de la VMC) mostraba la clave cruda
  `hum_in` porque le faltaba la traducción. Añadida en EN y ES (*"Humedad interior
  (opcional, punto de rocío / secado)"*). Distinto de *Humedad baño* (boost de ducha) y
  *Humedad exterior*.

## [0.35.4] — 2026-06-24

### Fixed
- **Imágenes del README en HACS**: el README usaba rutas **relativas** (`docs/img/…`) que
  GitHub resuelve pero **HACS no** (salían rotas en el panel de información). Ahora usan
  **URL absolutas** `raw.githubusercontent.com/.../main/…` en ambos READMEs (EN/ES), así se
  ven dentro de HACS. *(El **icono blanco** de la lista de HACS es aparte: sale del repo
  `home-assistant/brands`; ver `docs/brand/README.md` para publicarlo — los assets ya están
  listos.)*

## [0.35.3] — 2026-06-24

### Added
- **Pista direccional en la ayuda por campo**: ~110 parámetros que solo decían *qué eran*
  ahora añaden una pista compacta de **qué pasa si los subes/bajas** — p. ej.
  `lead_base_h` *"(↑ = anticipa antes)"*, `brake_thresholds_1` *"(↓ = frena antes)"*,
  `winter_night_pct` *"(↓ = cierra más para aislar)"*, `hood_pm_v1` *"(↓ = sube de
  velocidad antes)"*. Completa el trío de ayuda contextual (campo + categoría + guía
  TUNING.md). EN + ES (paridad).

## [0.35.2] — 2026-06-24

### Added
- **Ayuda por categoría en las opciones**: cada una de las **44 categorías** de parámetros
  (Consignas base, Tendencia y lead, Freno, Anti-pico, Free-cooling, Posiciones…) muestra
  ahora una **descripción** arriba del formulario que explica **qué hace el grupo y cómo se
  relacionan sus mandos** (p. ej. "más anticipación → más freno", "el reparto de prioridad
  no vive aquí, vive en Anti-pico", "configura el changeover para no ventilar calor"). Era
  el hueco que la ayuda por campo aislado no cubría. EN + ES (paridad).

## [0.35.1] — 2026-06-24

### Added (docs)
- **`docs/TUNING.md` · guía de ajuste por objetivo**: agrupa los muchos parámetros por
  **lo que el usuario quiere conseguir** ("que anticipe más", "que no oscile", "que respete
  el ICP", "sombra en verano"…), diciendo **qué mover, hacia dónde y qué vigilar junto**
  (la relación entre mandos que no captura la ayuda por campo). Cubre DC/DV/DS + la cascada
  del target + cómo validar un cambio. Enlazada desde el README. Solo documentación.

## [0.35.0] — 2026-06-24

### Added
- **Anti-ciclado adaptativo (F09)**: switch opt-in **"Adaptive anti-cycle"**. Cuando la
  zona ya ha **aprendido su retardo térmico** (madurez del lead adaptativo), el **min
  ON/OFF** del compresor se **dimensiona desde ese aprendizaje** en vez de un valor fijo:
  una estancia lenta (alta inercia) tolera ciclos más largos; una rápida, más cortos.
  Con **clamps de seguridad** (180–1800 s) para que siga siendo una protección real del
  compresor. Sin el switch o sin aprendizaje maduro, se usa el valor configurado.

### Internal
- `dc_engine.anticycle_bounds(learned_lag_h)` puro (≈1800 s/h de lag, clamp 180–1800,
  simétrico) + constantes; `coordinator_dc` aplica el override en `_anticycle_step` tras la
  madurez (`adapt_ok_count ≥ ANTICYCLE_AUTOSIZE_MIN_SAMPLES`); switch `anticycle_autosize`.
  Tests puro (escala + clamps) + integración (override con madurez, estático sin ella).
  Suite 467→469.

## [0.34.0] — 2026-06-24

### Added
- **Clima (F37) · modo "seguir al edificio" (`HEAT_COOL`)**: las zonas **comunitarias**
  ofrecen un cuarto modo de termostato, **Calor/Frío** (`HVACMode.HEAT_COOL`), que significa
  *"sigo la dirección del changeover"*. UI honesta: antes una zona comunitaria en *Calor*
  podía estar **enfriando** (porque el anillo de la comunidad va en frío) y la tarjeta no lo
  reflejaba; ahora se expresa explícito y la **acción** muestra la dirección real. Las zonas
  individuales mantienen los 3 modos de siempre.

### Internal
- `coordinator_dc.follow_changeover` (flag) + resolución a heat/cool/off cada ciclo desde
  el changeover (el motor nunca ve `"heat_cool"`); `climate.py` ofrece `HEAT_COOL` solo en
  zonas `community` (property `hvac_modes`), lo mapea en `hvac_mode` y restaura el modo.
  `HEAT_COOL` es un modo estándar de HA (sin traducciones nuevas). Tests (comunitaria sigue
  el changeover y al voltear; individual no lo ofrece). Suite 465→467.

## [0.33.0] — 2026-06-24

### Added
- **Servicios · exportar/importar opciones** (round-trip guardar/clonar): cierra la otra
  mitad del "save/load" (cargar ya existía por presets; exportar por diagnostics).
  - `dynamic_home.export_options` devuelve (como **datos de respuesta**) los valores de
    opciones ajustados de los módulos seleccionados.
  - `dynamic_home.import_options` **fusiona** un diccionario de valores en los módulos
    seleccionados; **solo aplica claves válidas** del `options_spec` de ese módulo (las
    desconocidas y las de datos se descartan, nunca se inyectan). Los cambios entran en
    vivo. Caso de uso: ajustar una zona y **clonarla** a las demás.

### Internal
- `_export_options` (`SupportsResponse.ONLY`) / `_import_options` en `__init__.py`
  (validación de claves reusando `options_spec`); `services.yaml` + traducciones EN/ES
  (paridad). Test de round-trip (exporta → importa, con descarte de basura). Suite 464→465.

## [0.32.1] — 2026-06-24

### Added (docs)
- **`docs/QUICKSTART.md`** — onboarding en 10 min: montar una zona de clima **ficticia**
  sobre helpers, activar **Observe only** y leer los **reason codes** sin tocar hardware.
  Incluye referencia de reason codes por módulo y resolución de problemas.
- **`docs/PROFILES.md`** — una receta por **perfil de instalación real** (radiante
  comunitario, VMC de 3 velocidades, persianas multi-fachada, aerotermia con tarifa), cada
  una con su perfil F26, el **preset** a aplicar y los reason codes a vigilar.
- Enlazados desde el README (sección *Examples* + índice de documentación). Control de
  exactitud de claves, switches, servicios y reason codes contra el código actual. Solo
  documentación.

## [0.32.0] — 2026-06-24

### Added
- **Diagnósticos · export descargable por módulo** (el "save" que faltaba): Ajustes →
  Dispositivos y servicios → el dispositivo → ⋮ → **Descargar diagnósticos**. Genera un
  **JSON** con las fuentes configuradas, los **valores de opciones** ajustados y una
  instantánea del estado vivo (decisión/reason, perfil F26, energía). Solo números y
  entidades —nunca un secreto—, así que es seguro adjuntarlo al reportar una incidencia.

### Internal
- Nueva plataforma `diagnostics.py` (`async_get_config_entry_diagnostics`, redacción
  vía `async_redact_data`, snapshot JSON-safe con fallback `dataclasses.asdict`). Sirve a
  DV/DC/DS/Energy/Zones por igual (atributos por `getattr`). Tests (DC con perfil; entrada
  sin coordinator). Suite 462→464.

## [0.31.0] — 2026-06-24

### Added
- **Presets · uno por perfil de instalación**: el menú *Aplicar un preset* (opciones del
  módulo) ahora ofrece un punto de partida por cada perfil real:
  - **DS · "Persianas motorizadas · multi-fachada"** (nuevo en persianas, que no tenían
    ninguno): avisos meteo, escudo solar de verano, aislamiento nocturno, cap de viento con
    histéresis, rampa de amanecer y escalonado de arranque de motores.
  - **DC · "Aerotermia individual · tarifa por tramos + anti-pico"**: consignas de bomba de
    calor, sesgo de tarifa (lead barato 1.5 / pico 0.6 + base 0.3), anti-pico (1 zona,
    stagger, bypass de confort 2.5) y anti-ciclado de compresor.
  - (Se mantienen los previos: DC "Salón radiante comunitario" y DV "VMC doble flujo".)

### Internal
- Dos entradas nuevas en `presets.py` (claves validadas por el guard `options_spec`);
  tests de aplicación de cada preset. Suite 460→462.

## [0.30.0] — 2026-06-24

### Added
- **Ventilación (F37/F07) · aviso "free-cooling sin changeover"**: si tienes el
  **free-cooling activo**, **alguna zona en calefacción** y **no has configurado el
  changeover**, Dynamic Home levanta un aviso en **Reparaciones** explicando que el
  free-cooling puede ventilar el calor que pagas en días templados de invierno, y cómo
  arreglarlo (configurar el changeover o desactivar el free-cooling). El aviso **se borra
  solo** en cuanto desaparece cualquiera de las tres condiciones, y **solo aparece si hay
  evidencia de calefacción** (no molesta a climas solo-frío).

### Internal
- `coordinator_dv._freecool_changeover_advisory` (issue no-fixable `freecool_no_changeover`,
  `ISSUE_FREECOOL_NO_CHANGEOVER`); traducciones EN/ES (paridad). Test de integración
  (sube con calefacción + sin changeover; baja al configurar changeover o al enfriar).
  Suite 459→460.

## [0.29.2] — 2026-06-24

### Internal
- **Documentación del límite de fairness F09/F03**: aclarado en docstrings (`anticycle.py`,
  `peak.py`) y en REQUIREMENTS que el reparto por prioridad (arrancar primero la zona más
  desviada) vive en **F03/peak**, y que **F09/anticycle es un guard agregado y mecánico**
  sin orden por zona (`anticycle_max_starts_hold` por igual a todas). Corregida de paso una
  nota obsoleta (la agrupación por `compressor_id` se entregó en v0.27.0). Solo docs.

## [0.29.1] — 2026-06-24

### Internal
- **F03/peak · test de convergencia (no starvation)**: cubre el caso "waiter de
  prioridad media bajo presión sostenida de zonas más hambrientas". Demuestra que
  `peak_yield` solo **retrasa** —nunca starva— a la zona media: cada zona, al concederse,
  pasa a activa y **sale del pool de waiters**, así que la media arranca en cuanto el flujo
  finito de zonas más desviadas se agota. Documenta por qué no hace falta envejecer la
  prioridad. Solo test, sin cambio de comportamiento.

## [0.29.0] — 2026-06-23

### Added
- **Ventilación (F37) · la temporada de calor suprime el free-cooling**: cuando el
  changeover de casa está en **calor**, DV deja de hacer free-cooling. Antes, un día
  templado de invierno (más caliente dentro que fuera) activaba el free-cooling por la
  histéresis de temperatura y **ventilaba el calor que estás pagando**. Sin changeover
  configurado, comportamiento idéntico (free-cooling solo por temperatura).

### Internal
- `DvInputs.heating_season` + guarda en `compute_freecool`; `coordinator_dv._house_changeover`
  (espejo del de DC/DS) alimenta `heating_season = changeover == "heat"`. Tests puro
  (suprime free-cooling) + integración (changeover de calor lo apaga). Suite 456→458.

## [0.28.0] — 2026-06-23

### Added
- **Persianas (F37) · siguen la temporada del edificio**: una persiana sin termostato
  propio adopta el **changeover de casa** (calor/frío) como temporada, de modo que en
  **verano** hace escudo solar y free-cooling nocturno y en **invierno** ganancia solar y
  aislamiento nocturno — antes esto solo se activaba con un `climate` enlazado por persiana
  (imposible en instalación comunitaria). Un termostato propio que pide heat/cool sigue
  mandando; sin changeover configurado, comportamiento idéntico al anterior.

### Internal
- `coordinator_ds._house_changeover` (espejo del de DC: override por zona vía
  `zones.scope_for_module`, si no el estado de casa) y `_hvac_mode` cae a él cuando no hay
  termostato activo. Tests de integración (temporada de casa + el termostato propio gana y
  luego cede). Suite 454→456.

## [0.27.0] — 2026-06-23

### Added
- **Anti-ciclado (F09) · canal de compresor por-emisor**: cada emisor puede declarar su
  **`Id de compresor`** en el editor de emisores. Dos bombas de calor con id distinto se
  **protegen por separado** (cada una con su propio mínimo ON/OFF y arranques/hora), así
  una no retiene a la otra. Por defecto todos comparten `"default"` — un único compresor
  de casa, idéntico al comportamiento anterior.

### Internal
- `AntiCycleHub` pasa a **multi-canal** (`evaluate(..., channel=...)`, `participates`,
  `clear` en todos los canales; un `CompressorState` por canal). `coordinator_dc` calcula
  el hold **por canal** (`_channel_holds`) y `_build_emitter_commands` retiene cada emisor
  por su propio compresor. `compressor_id` en `emitters.normalize` + editor + traducciones.
  Tests puros (canales independientes) + integración. Suite 451→454.

## [0.26.0] — 2026-06-23

### Added
- **Energía (F06 §REQ-ENE-5) · potencia instantánea**: cada módulo (VMC/DC) expone su
  **potencia instantánea** (`Power`, W, medidor real o estimación — la misma que alimenta
  el kWh), y el módulo Energy agrega la **potencia total de casa** (`Potencia de casa`, W,
  suma de todos los módulos), también publicada en `DATA_ENERGY` (`house_power_w`).

### Removed
- **F07 · botón fixable de Repairs descartado**: el issue de fuente requerida ya se
  **borra solo** al recuperarse la entidad y tiene `learn_more_url`; un `ConfirmRepairFlow`
  no aportaba valor. Se mantiene el issue no-fixable + enlace.

### Internal
- `power_w` en los coordinators DV/DC/DS (DS≈0 en reposo); `EnergyCoordinator._aggregate`
  suma `house_power_w`; sensores `PowerSensor` (por módulo) y `HousePowerSensor` (casa).
  Tests de integración (agregación de potencia + sensor por módulo). Suite 449→451.

## [0.25.0] — 2026-06-23

### Added
- **Energía (F34 §8.3) · sesgo de tarifa en DC** (REQ-TAR-4): cuando el módulo Energy
  publica el estado de tarifa, cada zona de clima **modula su anticipación** (Adaptive
  Lead). En tarifa **barata** ensancha el lead (`× lead barato`, 1.5) para
  **preacondicionar** mientras la energía es barata; en **pico** lo recorta (`× lead
  pico`, 0.6) para evitar rampas caras. Opcionalmente, un **sesgo de base** (`Sesgo de
  base °C`, por defecto 0 = off) carga la masa térmica en barato y se deja llevar en pico.
  Sin módulo Energy, el comportamiento es idéntico al actual.

### Internal
- `dc_engine.tariff_lead_mult` / `tariff_bias` (puros); `DcInputs.tariff_state` +
  `DcConfig` (`tariff_lead_cheap_mult`/`tariff_lead_peak_mult`/`tariff_bias_c`);
  `coordinator_dc._tariff_state()` lee `DATA_ENERGY` (como el headroom). Nueva categoría
  de opciones `tariff_bias` + traducciones (paridad). Tests puros + integración (lead
  barato > neutro > pico). Suite 445→449.

## [0.24.0] — 2026-06-23

### Added
- **Energía (F34 §8.2) · agregación de casa** (REQ-EAG-1/2/3): el módulo Energy ahora
  **suma** el consumo (`energy_kwh`) que cada módulo ya mantiene (DC/DV/DS, F06) en un
  **total de casa** (`Consumo de casa`, kWh, `total_increasing`) que entra en el **panel de
  Energía** de HA. Con un **sensor de precio** configurado, expone además un **coste de
  casa** (€, `Coste de casa`) que acumula ΔkWh×precio (coste **bruto**, restaurado entre
  reinicios). Sin sensor de precio, el sensor de coste no se crea.

### Internal
- `energy_engine.add_cost` (puro, ΔkWh negativo no resta, precio None no suma);
  `EnergyCoordinator._aggregate` (Σ de los coordinators no-`_` con `energy_kwh`; el primer
  ciclo siembra el previo para no contar los kWh restaurados); `house_kwh`/`house_cost` en
  el blob `DATA_ENERGY`. Sensores `HouseEnergySensor`/`HouseCostSensor`. Tests puro +
  integración. Suite 441→445.

## [0.23.0] — 2026-06-23

### Added
- **Anti-pico (F03) · prioridad de cola + bypass de confort** (REQ-PIC-5): cuando el
  presupuesto de pico está ajustado, arranca primero la zona **más alejada de su
  consigna** (prioridad por desviación); y una zona con una **desviación severa**
  (`peak_comfort_bypass_c`, °C, por defecto **2.5**; 0 lo desactiva) **se salta el
  límite** de pico — el confort gana al recorte (la seguridad sigue ganando por encima).
- **Anti-ciclado (F09) · por emisor**: en una zona con varios emisores, el guard de
  compresor ahora retiene **solo los emisores de bomba de calor**; un emisor de gas o
  eléctrico de la misma zona **sigue funcionando**. (El recorte de pico y las paradas de
  seguridad siguen afectando a todos.)

### Changed / Removed
- **F32 (presencia)**: se **descartan** del proyecto la **puerta direccional** (entrar
  vs salir por orden de eventos) y la **identidad BLE dedicada**. La presencia se queda
  con sensores de presencia/movimiento/móvil/puerta. Bermuda sigue siendo usable
  enchufando su `binary_sensor` de ocupación por zona en las fuentes existentes.

### Internal
- `peak.py` lleva un libro de waiters + `priority` en `evaluate`; `_peak_step` calcula la
  desviación (bypass + prioridad) y `_build_emitter_commands` aplica el hold de
  anti-ciclado por emisor (bomba de calor). Tests puros (`test_peak.py`) + integración.
  Suite 436→441.

## [0.22.0] — 2026-06-23

### Added
- **Changeover (F37) · histéresis + override por zona**:
  - **Histéresis de temporada**: cuando el agua de impulsión ronda los umbrales, el
    changeover ya **no parpadea** — una vez en calor/frío, el agua debe alejarse
    `hysteresis_c` (°C, configurable, por defecto 2) del umbral antes de cambiar de
    dirección.
  - **Override de changeover por zona**: cada zona tiene un selector
    **«Changeover {zona}»** (`auto/calor/frío/apagado`); en `auto` hereda la dirección
    de la casa, y con un valor fijo **fuerza** su propia dirección (para colectores
    independientes). El selector de casa sigue gobernando el resto.

### Internal
- `changeover.resolve(...)` ahora acepta el estado previo (histéresis) y se añade
  `changeover.effective(house, override)`; `ZonesCoordinator` publica los overrides en
  `DATA_CHANGEOVER["zones"]` y DC resuelve el changeover de su zona por `scope_for_module`.
  Tests puros (histéresis, effective) + integración (override por zona gana a la casa;
  histéresis no parpadea; publicación de overrides). Suite 431→436.

## [0.21.0] — 2026-06-23

### Added
- **Módulo Dynamic Energy (F34) · núcleo + tarifa + anti-pico de red**: un módulo
  nuevo (entrada única por casa, como Zonas) que **publica el contexto energético de la
  casa** y **no comanda** a nadie — cada módulo sigue mandando sobre sí mismo y la
  seguridad prevalece. **Agnóstico**: enchufas tus propias entidades (potencia de red,
  precio, y opcionalmente FV/consumo) y funciona con **cualquier subconjunto**.
  - Publica `import_headroom_w` (margen hasta la potencia contratada/ICP), `tariff_state`
    (**barato/normal/pico** por sensor de precio **o tramos fijos**), `scarcity` (caro y
    sin excedente) y, **solo si declaras FV**, `surplus_w`.
  - **Anti-pico de red (consolida F03):** el margen de red **aprieta dinámicamente** el
    presupuesto de pico de las zonas eléctricas (sin medidor → degrada a «N cargas»;
    desactivado en instalaciones comunitarias). Solo **baja** un presupuesto que el árbitro
    de pico ya aplicaba; ningún mecanismo nuevo.
  - Entidades: **Margen de red**, **Tarifa**, **Escasez** (+ **Excedente FV** si hay FV).
  - **FV/batería y carga del VE quedan diferidos** (validación externa); los campos de FV
    están preparados (present-but-gated) para añadirlos sin romper nada.

### Internal
- Nuevo módulo puro `energy_engine.py` + `coordinator_energy.py` con tests
  (`test_energy_engine.py` + `test_energy_integration.py`: publica `DATA_ENERGY` con solo
  red+precio; sin FV no expone excedente ni rompe; tarifa fija determinista; el headroom
  aprieta el pico de una zona DC eléctrica). Suite 420→431.

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
