# Changelog — Dynamic Home (integración)

Todas las versiones notables de la integración `custom_components/dynamic_home`.
Formato basado en [Keep a Changelog](https://keepachangelog.com/es/1.1.0/) y
[SemVer](https://semver.org/lang/es/).

## [0.89.0] — 2026-07-01

### Added
- **DW · sensor de Dirección del viento (rumbo cardinal).** Además del rumbo en grados
  (`wx_wind_bearing`), Dynamic Weather expone ahora el mismo dato como **punto cardinal**
  de 8 rumbos, más legible (N/NE/E/SE/S/**SO**/**O**/**NO** en español). Es de tipo enum y,
  como el resto de sensores de DW, sigue a la fuente activa con failover. Los grados
  originales quedan en el atributo `degrees`.

### Internal
- `WxWindDirSensor` en `sensor.py` (convierte `wind_bearing` → rumbo; estado interno en
  abreviaturas inglesas estables, localizado a español vía traducciones de estado).
  Alta en la rama `MODULE_WEATHER`. Traducciones es/en/strings. Test de integración
  (45°→NE, 350°→N, atributo `degrees`).

## [0.88.1] — 2026-07-01

### Fixed
- **DS · los sensores de energía 24h/30d se llamaban todos "Energía".** Les faltaba la
  clave de traducción, así que Home Assistant usaba el nombre por defecto del `device_class`
  y no se distinguían del acumulado. Ahora muestran **"Energía (últimas 24 h)"** y
  **"Energía (últimos 30 días)"** (el `entity_id` no cambia).

## [0.88.0] — 2026-07-01

### Added
- **DS · tres sensores de energía por persiana.** Junto al total acumulado (`Energía`)
  aparecen:
  - **Energía (últimas 24 h)** y **Energía (últimos 30 días)** (`energy_24h`/`energy_30d`):
    consumo del motor en ventanas móviles, calculado a partir de instantáneas del
    acumulado (una cada 5 min, hasta 30 días). Se rehacen tras un reinicio conforme el
    historial se vuelve a llenar.
  - **Potencia** (`power`, W): potencia instantánea — el medidor real si está configurado
    (`power_meter`), si no la del motor en el instante en que se mueve (0 en reposo, el
    estado normal de una persiana).

### Internal
- `energy.window_kwh(samples, current, now, window_s)` puro + `coordinator_ds`
  historial down-sampled (`_record_energy`, buckets de 5 min/30 días) y
  `energy_window_kwh`; `power_w` real/estimado por movimiento. `DsEnergyWindowSensor`
  (sin `state_class`: valor acotado, no monótono) + alta de `PowerSensor` en DS.
  Traducciones es/en/strings. Tests puros (ventana) + integración (potencia + ventanas).

## [0.87.0] — 2026-07-01

### Added
- **DS · dos sensores nuevos por persiana.**
  - **Diferencial interior-exterior** (`ds_temp_diff`): la resta `Tª interior − Tª exterior`
    de la sala de la persiana (p. ej. salón vs calle/terraza). De un vistazo, un diferencial
    pequeño sugiere ventana/persiana abierta y uno grande que está cerrada y aislando. Solo
    se crea si están configuradas ambas temperaturas (interior y exterior).
  - **Modo de control** (`ds_control_mode`): indica si la persiana va en **automático**
    (mandada por DS) o en **manual (override)** por una orden a mano/externa. Así, cuando
    esté en manual, sabes que puedes pulsar el botón **"Reanudar automático"** para cancelar
    el override. Atributos: `held_position`, `remaining_min` y `reason`.

### Internal
- `DsTempDiffSensor` y `DsControlModeSensor` en `sensor.py` (el de modo, enum
  `auto`/`manual`, siempre presente; el diferencial gateado por ambas temperaturas).
  Traducciones es/en/strings. Tests de integración (diferencial, y auto→manual→auto).

## [0.86.0] — 2026-07-01

### Fixed
- **DW · el sensor de Índice UV ahora muestra la unidad y sin decimales.** El sensor de UV
  de Dynamic Weather se creaba **sin unidad** (mostraba p. ej. `3,0`) mientras que la fuente
  (Google Weather) la muestra como `3 UV Index`. Ahora el sensor lleva la unidad **`UV Index`**
  y **0 decimales** (el índice UV es entero), de modo que coincide con el proveedor.

### Internal
- `_WxValDesc` gana el campo `precision`; `WxValueSensor` fija
  `suggested_display_precision` cuando está definido. `wx_uv` pasa a `unit="UV Index"`,
  `precision=0`. Test que verifica la unidad y la precisión del sensor UV.

## [0.85.0] — 2026-07-01

### Changed
- **DS · el campo de Lluvia también acepta sensores no binarios.** Igual que las alertas
  (v0.83.0), el campo **Lluvia** admite ahora, además del `binary_sensor` de siempre, un
  **sensor numérico de precipitación (mm)** o un sensor de **condición**/`weather`
  (`rainy`/`pouring`/`snowy-rainy`). Así se puede enchufar directamente un sensor de
  Google Weather. Umbral configurable `rain_mm_min` (0.1 mm). Compatible hacia atrás con
  los binarios de Open-Meteo.

### Internal
- `ds_engine.alert_active` gana el `kind="rain"` (numérico = mm, condición =
  `ALERT_RAIN_CONDITIONS`) + `DsConfig.rain_mm_min`. `coordinator_ds` lee la lluvia con
  `_alert_on(CONF_RAIN, "rain", cfg)`. Selector del config flow ampliado a
  `binary_sensor`/`input_boolean`/`sensor`/`weather`. Tests puros + integración.

## [0.84.0] — 2026-07-01

### Added
- **DW · sensor de Condición meteorológica.** Dynamic Weather expone ahora un sensor
  individual con la **condición** (estado tipo `sunny`/`rainy`/`lightning`…), el
  equivalente al sensor de condición de un proveedor (p. ej. Google Weather). Es de
  tipo **enum** (vocabulario estándar de Home Assistant) y, como el resto de sensores
  de DW, sobrevive al **failover** entre proveedores (su atributo `source` indica de
  qué fuente sale). Reutilizable en cualquier tarjeta o automatización, incluidos los
  campos de alerta de DS (v0.83.0).

### Internal
- `WxConditionSensor` en `sensor.py` (lee `WxData.condition`, opciones
  `_WX_CONDITIONS`, atributo `source = active_entity`). Traducciones es/en/strings
  (`wx_condition`). Test de integración (estado primario + failover a la secundaria).

## [0.83.0] — 2026-06-30

### Changed
- **DS · las alertas meteo aceptan sensores de Google Weather (no solo `binary_sensor`).**
  Los tres campos de alerta (meteo / granizo-tormenta / viento) ya admiten también un
  **sensor numérico** o un sensor de **condición**/`weather`, además del `binary_sensor`
  de siempre. Un único intérprete decide si la alerta está activa según la forma del dato:
  binario (`on`/`off`), numérico (umbral: **racha km/h** en la de viento, **probabilidad %**
  en las otras) o texto de condición HA (`lightning`, `hail`, `windy`, `rainy`…). Así se
  pueden enchufar directamente los sensores de Google Weather, que no expone binarios.
  Compatible hacia atrás: los binarios de Open-Meteo siguen funcionando igual.

### Internal
- `ds_engine.alert_active(state, kind, cfg)` puro y testeable + sets de condiciones
  (`ALERT_HAIL/WIND/GENERIC_CONDITIONS`); `DsConfig.alert_gust_kmh` (50) y `alert_prob_pct`
  (70) como umbrales. `coordinator_ds._alert_on()` lee el estado crudo y delega.
  Selectores del config flow ampliados a `binary_sensor`/`input_boolean`/`sensor`/`weather`.
  Tests puros (binario/numérico/condición) + integración (gust + condición).

## [0.82.0] — 2026-06-30

### Added
- **Motivo en texto humano (`_human`) en DC, DS y DV.** Junto a cada sensor de **Motivo**
  (que muestra el código crudo: `cool`, `dawn_ramp`, `dry_mode`…) aparece un sensor gemelo
  cuyo **estado es la frase legible** ("Refrigerando", "Apertura por amanecer", "Modo
  secado"…), para soltarlo en una tarjeta **sin plantillas ni evaluar códigos**. Su
  `entity_id` es el del Motivo con sufijo **`_human`** (p. ej. `sensor.vmc_reason_human`,
  `sensor.persiana_salon_centro_motivo_human`); el código crudo queda en el atributo `code`.

### Internal
- `reason_text.py` (tablas DC/DS/DV código→texto es + `humanize`, fallback al código).
  `ReasonHumanSensor` (clava su `entity_id` al del Motivo vía registro + `_human`). Alta en las
  tres ramas de `sensor.py`. Traducciones es/en/strings. Tests del mapa + integración.

## [0.81.1] — 2026-06-30

### Changed
- **DC · magnitudes de los biases alineadas con el legacy v4.2.** Auditando el YAML original
  contra el port se vio que el port había **inflado casi todos los biases ×2-3** (exterior
  efectivo 0,18→0,5 al perder el factor de aislamiento 0,6→1,0; VMC ×2; fachada ×2; umbrales del
  freno desplazados; `apply_min_delta` 0,2→0 perdido). Se **restauran los valores legacy**
  manteniendo el **signo ya corregido** de 0.81.0 (frío compensa). Resultado, validado en 50
  escenarios simulados: la compensación queda en **±0,5 °C** en extremos (antes ±1,0 tocando el
  cap), con el cap **±0,8** y el freno/tope de tendencia **±0,25** como red de seguridad, no como
  muleta. Todo sigue siendo configurable y el preset Confort estrecha.
- Defaults: exterior 0,5→0,3 / 0,2→0,15; `insulation_factor` 1,0→0,6; `ext_cold_threshold`
  0→5; VMC (0,1;0,2;0,3)→(0,05;0,1;0,15); fachada 0,3→0,15; `forecast_gain` 0,1→0,08 /
  `forecast_cap` 0,5→0,8; `trend_max_shift` 0,25→0,2; freno umbrales (0,3;0,6;1,0)→(0,2;0,3;0,5)
  y biases (0,1;0,2;0,3)→(0,1;0,2;0,4); `apply_min_delta` 0→0,2.

## [0.81.0] — 2026-06-30

### Fixed
- **DC · el bias exterior de frío iba al revés.** En calefacción, cuanto más frío hace fuera
  más calienta (compensa las pérdidas); en refrigeración hacía **lo contrario** — cuanto más
  calor fuera, **enfriaba menos** (subía la consigna), justo cuando más aprieta. Ahora **compensa
  de forma simétrica**: más calor fuera → consigna **baja** → **enfría más**. Esto quita la
  desviación de ~+1 °C que mantenía la sala caldeada en pleno calor.

### Changed
- **DC · el forecast no aplaza el frío si la sala está caliente.** La anticipación por previsión
  (aflojar porque va a refrescar) ya **no actúa mientras la sala está por encima de la base** en
  frío (ni por debajo en calor): primero llegar a consigna, luego anticipar. Antes, en las tardes
  de verano, sumaba al "enfría menos".

### Internal
- `dc_engine.bias_exterior` (rama cool negada, compensación); gate del `forecast_bias` en
  `decide` por `t_int` vs `base`. Tests motor actualizados (signo cool) + gate del forecast.

## [0.80.0] — 2026-06-30

### Changed
- **Mantenimiento: re-publicación limpia.** La v0.79.0 quedó con un tag mal escrito
  (`v.79.0`) que se borró; esta versión vuelve a publicar el mismo trabajo bajo un tag
  correcto y sin ambigüedades para que HACS lo detecte con seguridad. **Sin cambios de
  comportamiento respecto a 0.79.0** — incluye, como aquélla, que las persianas aprovechen
  los datos ricos de Dynamic Weather (ráfagas → protección de viento; probabilidad de
  tormenta/lluvia → alerta anticipada).

## [0.79.0] — 2026-06-30

### Added
- **DS aprovecha los datos ricos de Dynamic Weather (0.78.0).** Lo que antes solo se veía,
  ahora **actúa**:
  - **Ráfagas → protección de viento.** El tope de viento de las persianas reacciona ahora al
    **peor** valor entre el viento medio (sensor local) y la **ráfaga** que publica Dynamic
    Weather. Una ráfaga fuerte protege aunque la media esté por debajo del límite — **y funciona
    aunque no tengas sensor de viento local** (basta la ráfaga de DW).
  - **Probabilidad de tormenta/lluvia → alerta anticipada.** Con probabilidad de **tormenta** ≥
    umbral, la persiana **cierra** (posición de alerta); con probabilidad de **lluvia** ≥ umbral,
    va a la **posición de protección de lluvia** — *antes* de que ocurra, con el mismo *hold* que
    el resto de avisos. Solo en modo automático (si configuras sensores de alerta locales, mandan
    ellos).
- Dos umbrales configurables en DS → Avisos meteo: **Aviso prob. tormenta (%)** (60 por defecto)
  y **Aviso prob. lluvia (%)** (80). 0 = desactivado.

### Internal
- `DsConfig.storm_prob_alert`/`precip_prob_alert`; `DsInputs.gust`; `ds_engine.effective_wind`
  (max viento/ráfaga) en `compute_wind_cap`/`update_wind_cap_active`. `coordinator_ds` lee
  `DATA_WEATHER.values` (gust → cap + habilita weather_protect; storm/precip_prob → `_weather_alert`).
  Opciones `storm_prob_alert`/`precip_prob_alert`. Tests motor (ráfaga capa) + integración
  (probabilidades arman alerta, ráfaga sin sensor local capa).

## [0.78.0] — 2026-06-30

### Added
- **Dynamic Weather · failover POR DATO + campos ricos (agregador real).** Antes los valores
  salían de **una sola** fuente activa, así que si esa no publicaba humedad/presión, salían
  "No disponible" aunque otro proveedor sí los tuviera. Ahora **cada magnitud se resuelve por
  separado**, cogiéndola de la **primera fuente (por prioridad) que realmente la tenga** — y
  cada sensor expone en un atributo **de qué proveedor** salió. Así exprimes a fondo
  proveedores ricos como **Google Weather** o AEMET: la temperatura de uno, la humedad/presión
  de otro.
- **Nuevos sensores** además de los de 0.77.0: **Ráfagas de viento, Índice UV, Cobertura de
  nubes, Punto de rocío** (leídos de los atributos del proveedor), y **Probabilidad de tormenta**
  y **Probabilidad de precipitación** (de sensores que aportes, p. ej. los de Google Weather).
  Los extras quedan bajo **Diagnóstico** para no saturar.
- **Entradas crudas por campo** (opcionales) para enchufar sensores concretos: humedad, presión,
  ráfagas, UV, nubes, punto de rocío, prob. tormenta, prob. precipitación.

### Internal
- 8 `CONF_WX_*` nuevos. `coordinator_weather` refactor: tabla `WX_FIELDS` + `_resolve_field`
  (failover por campo sobre fuentes frescas → sensor crudo); `WxData` pasa a `values`/`sources`
  con accesores de compat. `DATA_WEATHER` publica `values` (para DC/DS futuros). `_WX_VALUES`
  table-driven con `source` por sensor y gating por `requires_conf`. Traducciones es/en/strings.
  Tests: failover por campo (humedad del 2º proveedor) + campos solo-crudos gateados.

### Diferido
- Cablear **ráfagas → protección de viento de DS** y **prob. tormenta/lluvia → alerta
  anticipada de DS** (cambios en la lógica de DS, siguiente ciclo).

## [0.77.0] — 2026-06-30

### Added
- **Dynamic Weather · sensores individuales del proveedor activo.** Además del `weather`,
  la alerta y la fuente activa, DW ahora expone cada dato por separado, tomado del **proveedor
  activo (con failover)**: **Temperatura exterior, Humedad exterior, Presión, Velocidad del
  viento, Dirección del viento** y **Precipitación** (esta última solo si configuras un sensor
  de lluvia). Así puedes usar el dato **directamente** en un dashboard o automatización, y si
  el primer proveedor cae, el sensor sigue dando valor desde el segundo/tercero — sin tener que
  apuntar a la entidad del proveedor concreto. Cada sensor queda "no disponible" si el proveedor
  activo no aporta ese dato.

### Internal
- `WxData` gana `wind_bearing`/`precip`; el coordinador lee `wind_bearing` del proveedor y
  `has_precip()`. `_WX_VALUES` + `WxValueSensor` (CoordinatorEntity, `MEASUREMENT`, device_class
  por magnitud, `available` = dato presente) en la rama `MODULE_WEATHER`. Traducciones es/en/
  strings. Test de integración (sensores presentes, valores del activo, siguen al failover).

## [0.76.0] — 2026-06-30

### Added
- **DS · detección de movimiento externo → override automático.** Hasta ahora solo el botón
  de la propia integración armaba el override manual; si movías la persiana por **otra vía**
  (un botón BLE/inteligente, un interruptor de pared, otra automatización que actúa sobre el
  cover **físico**), Dynamic Home no lo registraba y su lógica de confort podía deshacer tu
  movimiento. Ahora DS **observa la persiana física** y, cuando ésta **acaba** en una posición
  que DH **no ordenó**, lo interpreta como mando manual y **arma el override temporal** (igual
  que su botón; expira solo según `override_hours`). Así **cualquier** movimiento manual pausa
  el confort, sin tener que reapuntar tus automatizaciones a la entidad de DH.
- Nuevo interruptor por persiana **"Seguir movimientos manuales"** (activado por defecto) para
  desactivarlo si en alguna persiana prefieres que DH ignore los movimientos externos.

### Internal
- `DsCoordinator.track_external` (default True, RestoreEntity vía switch). `cover.py`:
  baseline de `_last_pos` en `async_added_to_hass` y `_detect_external_move` (compara la posición
  asentada contra la última ordenada, tolerancia `_EXTERNAL_TOL_PCT=4`, ignora tránsito
  opening/closing → `arm_manual_override`). Traducciones es/en/strings. Test de integración
  (movimiento externo arma override; con el toggle off, se ignora).

## [0.75.1] — 2026-06-30

### Changed
- **DC · honestidad anticondensación sin sensor de suelo** (corrección de 0.75.0). El
  chequeo de condensación por **aire** (cuando no hay Tª de agua/suelo) daba **falsa
  sensación de seguridad** en suelo radiante: el aire suele estar lejísimos del rocío, así
  que marcaba "Seco" mientras la superficie fría podía estar condensando. Ahora, en una
  zona de **superficie fría** (emisor radiante en F26 — suelo/techo radiante/refrescante —
  **o emisor sin declarar**) que refrigera **sin** sensor de Tª de agua/suelo:
  - se levanta un **aviso en Reparaciones** ("refrigerando sin protección anticondensación
    de superficie — añade la Tª de agua/suelo o asume el riesgo");
  - el binario **"Riesgo de condensación"** deja de afirmar "Seco" y pasa a **no disponible**
    (no se puede determinar sin la superficie), con atributos `proteccion`
    (superficie/aire/ninguna) y `sin_proteccion_superficie`.
  - **Zonas no radiantes declaradas** (split/fancoil/conductos) **no** se avisan: ahí el
    chequeo por aire es razonable. Con sensor de agua/suelo, protección real (0.75.0).

### Internal
- `install.is_cold_surface` (+ `COLD_SURFACE_EMITTERS`); `coordinator_dc.cond_protection`,
  `cond_unprotected`, `_update_cond_warning()` (issue `ISSUE_COND_UNPROTECTED`, limpiada en
  unload). `DewRiskBinarySensor.available`/atributos. Traducciones es/en/strings. Tests
  motor + integración (radiante avisa / no-radiante no / con agua limpia).

## [0.75.0] — 2026-06-30

### Added
- **DC · protección de condensación por superficie fría** (suelo radiante refrescante).
  Nueva entrada opcional **"Temperatura de agua/suelo radiante"**: con ella, el riesgo de
  condensación se evalúa contra la **superficie fría real** (el suelo ≈ Tª del agua), no
  contra el aire — que es donde de verdad condensa. Nuevo **margen de seguridad
  configurable** (`Margen de seguridad superficie`, 0,3 °C por defecto) que absorbe el
  error de la fórmula de Magnus (presión) y de los sensores: el riesgo salta cuando
  `(suelo − rocío) < margen`. Tres sensores nuevos para verlo: **Temperatura de suelo**,
  **Desvío real** (suelo − rocío) y **Margen de condensación** (corregido = desvío − margen;
  negativo ⇒ húmedo ⇒ zona parada), este último con el desglose completo en atributos.
- **Compatibilidad**: sin configurar la Tª de suelo, el riesgo sigue como hasta ahora
  (comparación con el aire, `dew_spread_min`).

### Internal
- `CONF_DC_WATER_TEMP`; `DcConfig.cond_margin_c=0.3`; `dew_risk(..., floor_temp)` con rama
  de superficie fría. `coordinator_dc` calcula `floor_temp_c`/`cond_spread_real`/
  `cond_margin_corrected` y `has_water()`. `_DC_COND_SENSORS` (gated). Opción `cond_margin_c`
  en categoría condensación. Traducciones es/en/strings (paridad). Tests motor + integración.

## [0.74.0] — 2026-06-30

### Added
- **Sufijo de marca `- DH-DV`/`- DH-DS`/`- DH-DC`** en el nombre de las entidades
  principales que gestiona Dynamic Home (la VMC `fan`, la persiana `cover` y la zona
  `climate`). Así se distinguen de un vistazo de la entidad **física** que controlan
  (p. ej. "Persiana Salón Centro - DH-DS" vs el cover real) y se agrupan fácil en un
  dashboard. **Es solo el nombre visible**: el `entity_id` se mantiene limpio
  (`cover.persiana_salon_centro`) y estable, y renombrar el dispositivo sigue
  propagándose a todas sus entidades.

### Internal
- `const.MODULE_TAG` (única fuente de verdad del tag, compartida con el prefijo de los
  espejos). `cover`/`climate`/`fan` fijan `entity_id` al slug del dispositivo para que el
  sufijo de nombre no cambie el `entity_id` (sin churn ni rotura para instalaciones
  existentes). Test de friendly_name.

## [0.73.1] — 2026-06-30

### Added
- **DS/DV/DC · desglose de "por qué No disponible"** en el sensor de diagnóstico
  **Estado** (Degradado): nuevos atributos que clasifican **cada fuente** del módulo —
  `ok`, `no disponible` (configurada pero caída/renombrada o `unavailable`) o
  `sin configurar` (rol opcional en blanco, la causa habitual de que una entidad derivada
  no aparezca) — más un `resumen` legible. Así, ante un "No disponible", se ve de un vistazo
  si falta configurar la fuente o si la entidad existe pero está caída, sin adivinar.

### Internal
- `repairs.SOURCE_LABELS` (etiquetas es de todas las fuentes por módulo) +
  `DegradedTracker.health_report()`; `DegradedBinarySensor.extra_state_attributes` lo expone.
  Reusa el mixin F07 (sin entidades nuevas). Test: clasifica ok/no disponible/sin configurar.

## [0.73.0] — 2026-06-30

### Changed
- **DS · el amanecer gradual cede ante el escudo de sol directo** (fachadas al este/refresco):
  en modo refresco, con sol incidiendo en la fachada y el **"Escudo de sol directo"** activado,
  la rampa de amanecer ya **no abre** la persiana — cede al escudo solar, que la protege por
  geometría desde el primer rayo. Evita el ciclo "abre a 100% y vuelve a cerrar" en cuanto el sol
  empieza a calentar. **Invierno (calefacción) intacto**: el amanecer sigue abriendo para ganancia
  solar/luz; sin sol en la fachada o sin el escudo activado, la rampa abre como siempre (legacy).

### Internal
- `ds_engine.decide_cover`: nuevo `sun_protect = is_cool and impact > 0 and sun_gain_shield`
  añadido al gate del `dawn_ramp` (junto a `cool_protect`). Tests: cede con el escudo y sol antes
  de que caliente; sigue abriendo sin el opt-in.

## [0.72.0] — 2026-06-29

### Added
- **DS · configuración de pico de persianas GLOBAL** (en la entrada **Dynamic Home (Zonas)**):
  pones **una vez** los 3 valores (Máx arranques / Presupuesto de potencia / Escalonado) y los usan
  **todas** las persianas con "Limitación de pico" activada. El switch por persiana decide **quién
  participa**; los valores ya no se teclean ventana a ventana. **Fallback**: si no configuras el
  global (o no tienes entrada Zonas), cada persiana usa **sus propios** valores (como hasta ahora) —
  así un usuario solo-persianas no queda excluido (y puede usar "Clonar de otra persiana").

### Internal
- `CONF_DS_PEAK` (dict en options de Zonas); `coordinator_zones` lo publica en `DATA_MODE.ds_peak`.
  `coordinator_ds._peak_params(cfg)` (global > propio) alimenta el `PeakLoadHub`. Paso
  `ds_peak` en `ZonesOptionsFlow`. Tests (global gana sobre propio). Traducciones es/en/strings.

## [0.71.0] — 2026-06-29

### Added
- **Interruptor maestro de pausa** en la entrada **Dynamic Home (Zonas)**: cuatro switches —
  **Pausa Dynamic Home** (global) + **Pausa Clima / Ventilación / Persianas** (por módulo),
  **OFF por defecto**. Un módulo pausado **deja de actuar sobre el hardware** (termostatos /
  relés / persianas) **y deja de influir en el bus** (un DC pausado ya no empuja órdenes solares
  a las persianas). Sigue calculando y con sus sensores vivos. Pausa "total": equivale a un "Solo
  observar" centralizado y por módulo. Ideal para **manejar los termostatos a mano** (Pausa Clima)
  o **apagar Dynamic Home** entero o por módulo.

### Internal
- `modes.is_paused(data, module)`; `coordinator_zones` publica `pause:{all,climate,vmc,shutter}`
  en `DATA_MODE`. Cada coordinator: `_paused()` + `observe_effective` (= observe o pausa), usado
  en los gates de actuación (`climate.py`/`cover.py`/`fan.py`/`_drive_dehumidifier`). DC además
  vacía sus slots del bus (`_publish`) y omite el `request_dry` al estar pausado. `switch.py`:
  `ZonesPauseSwitch` (×4) + `PLATFORMS_ZONES` ya tenía switch. Tests (modes, gating DS).
  Traducciones es/en/strings.

## [0.70.1] — 2026-06-29

### Fixed
- **DC · el campo "Sensor de ventana abierta" (`dc_window`) ya se traduce.** Faltaba la etiqueta
  en strings/en/es, así que en el formulario de alta/edición de un clima salía la clave cruda
  `dc_window`. Añadida en los 3 idiomas.

## [0.70.0] — 2026-06-29

### Added
- **DS · las persianas reaccionan a Sleep y a Eco/Confort** (por ámbito de zona, como DC/DV).
  - **Sleep** → la persiana cierra a `sleep_pct` (**0% por defecto**), motivo `mode_sleep`. Por
    ámbito: pon en Sleep solo las **zonas de dormitorio** (con tu automatización por horario) y
    cierran solo esas. La meteo y lo manual siguen mandando por encima.
  - **Eco / Confort** → escala la **agresividad solar**: `eco` sombrea más (cierra más contra el
    sol → menos AC), `confort` abre más (prioriza luz). `equilibrado` = sin cambios.
  - Nuevo tunable `sleep_pct` (categoría "Posiciones de persiana").

### Internal
- `comfort.apply_ds` (deltas en `summer_min_open_pct`/`heat_shield_pct`). `coordinator_ds`:
  `_mode()`/`_sleep_pos()`, `comfort.apply_ds` en `_cfg()`. `DsConfig.sleep_pct`, `DsInputs.sleep_pos`,
  rama `mode_sleep` en `decide_cover` (bajo seguridad/manual, sobre el confort). Tests de motor,
  comfort e integración. Traducciones es/en/strings.

## [0.69.1] — 2026-06-29

### Fixed
- **Dynamic Home (Zonas) y Dynamic Energy ya no salen como "dispositivo sin nombre".** Sus
  dispositivos heredan el título de la entrada (como ya hacía Dynamic Weather). No pisa el
  nombre que hayas puesto a mano (HA respeta el renombrado del usuario).

## [0.69.0] — 2026-06-29

### Added
- **DS · Simulación de presencia (anti‑okupa) en modo Away.** Con el switch global
  **"Simulación de presencia"** (entrada Zonas, **OFF por defecto**), cuando la casa (o una
  zona) está en **Away** las persianas **imitan a un ocupante**: abren de día y cierran de noche,
  con la transición **aleatorizada ±jitter** (distinta por persiana y por día → escalonada e
  impredecible, estable dentro del día). Solo **2 movimientos/día** (poco motor). La meteo
  (alerta/lluvia/viento) y lo manual **mandan por encima**. Switch **"Excluir de simulación"** por
  persiana para dejar fuera las que quieras.
- **DS · tunables de simulación** (categoría "Simulación de presencia"): `sim_open_pct` (día,
  por defecto **50%** para no forzar motores), `sim_close_pct` (noche, 0%), `sim_jitter_min` (30).

### Internal
- `coordinator_zones.presence_sim` publicado en `DATA_MODE`; `PresenceSimSwitch` (Zonas) y toggle
  `sim_exclude` (DS). `coordinator_ds._sim_step` (latch día/noche con jitter por fecha+persiana
  vía `crc32`) → `DsInputs.sim_pos` → rama `presence_sim` en `decide_cover` (bajo seguridad/manual,
  sobre el confort). `DsConfig.sim_*` + categoría `sim` en `options_spec`. `PLATFORMS_ZONES` += switch.
  Tests de motor e integración (gating por modo/exclusión, latch con jitter). Traducciones es/en/strings.

## [0.68.0] — 2026-06-29

### Changed
- **Nombres de los módulos en el menú de alta** coherentes con la convención de marca:
  *Dynamic Ventilation (VMC)*, *Dynamic Shutter (Persiana)*, *Dynamic Climate (Zona)*,
  *Dynamic Weather (Tiempo)*, *Dynamic Home (Zonas)*, *Dynamic Energy (Energía)*. El paréntesis
  se localiza (es/en). Solo afecta al diálogo "¿Qué módulo añadir?", no a los dispositivos ya
  creados (esos nombres son del usuario y se renombran en la UI).
- **Espejos de hardware (F36): el nombre lleva el tag del módulo** — `DH-DV` (VMC), `DH-DS`
  (persiana), `DH-DC` (clima). P. ej. *"DH-DV CO₂ (espejo)"*. El `unique_id` no cambia (los
  espejos existentes conservan su id; solo cambia el nombre visible).
- **Subtítulo "model"** de los dispositivos de **Energía** y **Zonas**: ahora muestran
  *Dynamic Energy* / *Dynamic Home* (antes sin modelo), para igualar a DV/DS/DC/Weather.

### Internal
- `_MIRROR_TAG` por módulo en `sensor.py`; `DeviceInfo(model=…)` en `HeadroomSensor`/`ZonesSensor`.
  Etiquetas `menu_options` en strings/en/es. Test del prefijo `DH-DV` en el espejo.

## [0.67.0] — 2026-06-29

### Added
- **DV · sensores de punto de rocío** (diagnóstico, solo si hay Tª+HR de cada lado):
  **Punto de rocío interior**, **exterior** y **Δ punto de rocío** (`dp_in − dp_out`). El Δ es la
  señal del gate de secado (F13): cuando supera el margen de secado, ventilar **seca** (el aire de
  fuera está más seco). Reusan el `dew_point` (Magnus) que ya usa el motor; no cambian la lógica.

### Changed
- **DV/DC/DS · los espejos de hardware (F36) redondean por rol.** Concentraciones (CO₂, PM2.5,
  VOC, NOx, viento) se muestran **sin decimales**; temperaturas y humedad con **1 decimal**. Antes
  el espejo copiaba el valor crudo del sensor de origen y arrastraba el ruido de coma flotante de
  32 bits (p. ej. `1.20000004768372 µg/m³`). Ahora redondea (`suggested_display_precision` + valor).

### Internal
- `coordinator_dv`: `dew_point_in/out/diff`, `has_dew_in/out`. `sensor.py`: `DewPointSensor`
  (×3, gated) y `_MIRROR_PRECISION` por rol en `HwMirrorSensor`. Traducciones es/en/strings.
  Tests de integración (presencia/ausencia de los sensores de rocío y redondeo del espejo).

## [0.66.0] — 2026-06-29

### Changed
- **DS · el "Motivo" distingue purga nocturna de aislamiento.** La rama de aislamiento
  nocturno (F16) ahora marca **`night_purge`** cuando **abre** para ventilar la masa térmica
  (noche en `cool` con el exterior más fresco que el interior) y mantiene **`night_insulate`**
  cuando **cierra** para aislar/proteger (invierno, o verano con el exterior más caliente). Antes
  ambos casos compartían `night_insulate`, lo que confundía (parecía que solo cerraba). Solo
  cambia la etiqueta del sensor "Motivo"; el comportamiento de la persiana es idéntico.

### Internal
- `ds_engine.DsInputs.night_purge` (bool); la rama F16 de `decide_cover` elige el reason según
  ese flag. `coordinator_ds` lo calcula (`hvac == cool and t_out <= t_in`) y lo pasa a las
  entradas. Test de motor para `night_purge`.

## [0.65.1] — 2026-06-28

### Changed
- **DS · el campo "Lluvia" vuelve a ser solo `binary_sensor`** (revierte el desvío de la
  0.65.0). El selector vuelve a restringirse a `binary_sensor` y la etiqueta lo indica
  explícitamente: *"Lluvia (binary_sensor, opcional)"*. La aceptación de sensores numéricos
  de mm no aportaba (si llueve, llueve, da igual cuántos mm) y se elimina junto con el tunable
  `rain_mm_threshold`.

### Internal
- Revertido `coordinator_ds._raining` (vuelve a `_is_on(CONF_RAIN)`), `DsConfig.rain_mm_threshold`,
  la entrada de `options_spec` y los bloques de traducción. Test de integración deja la lectura
  binaria. La protección por lluvia se alimenta con un `binary_sensor` (p.ej. derivado de
  Open-Meteo).

## [0.65.0] — 2026-06-28

### Added
- **DS · el campo "Lluvia" admite sensor numérico de mm además de binary_sensor.** Antes solo
  se leía el estado literal `"on"` (binary_sensor), pero el selector ya ofrecía también
  `sensor` → un sensor de precipitación (p.ej. **Open-Meteo Precipitación actual**, en mm)
  quedaba puesto pero **nunca disparaba la protección de lluvia**. Ahora cuenta como lluvia
  cuando los mm superan el umbral, y sigue admitiendo el binary_sensor on/off de siempre.
- **DS · tunable `rain_mm_threshold`** (mm, categoría "Protección de viento"; por defecto 0.0 =
  cualquier precipitación > 0) para ajustar a partir de cuántos mm se considera que llueve
  cuando el campo Lluvia es un sensor numérico.

### Changed
- **Etiqueta del campo "Lluvia"** en el alta/edición de persianas: ahora indica
  *"binary_sensor on/off o sensor de mm"* (antes solo "(opcional)", que inducía a error frente
  a los campos de alerta que sí decían "(binary_sensor)").

### Internal
- `coordinator_ds._raining(cfg)`: nuevo lector que acepta binary (on/off) o numérico (mm >
  `rain_mm_threshold`); sustituye `_is_on(CONF_RAIN)` en la construcción de `DsInputs`.
  `ds_engine.DsConfig.rain_mm_threshold`. Tests de integración (lluvia binaria y numérica,
  incl. unavailable). Paridad de traducciones es/en/strings.

## [0.64.0] — 2026-06-28

### Added
- **DS · switch "Protección meteo" por persiana** (ON por defecto): permite **eximir una
  persiana** de toda la protección por tiempo. Apagado, esa persiana **ignora lluvia, alerta
  meteo (local y la auto de Dynamic Weather) y el tope de viento** — pensado para una **terraza
  cubierta** donde no quieres que se cierre por el tiempo (y no quedarte fuera). La lógica de
  confort y el override manual siguen funcionando.

### Internal
- `coordinator_ds.weather_protect` (switch restaurado, default True). `_weather_alert` corta y
  expone `alert_source = "off"` cuando está apagado; `weather_protect_enabled` (lluvia/viento)
  pasa `False`. `switch.py`: toggle `weather_protect` (translation_key EN/ES). Tests de motor
  (lluvia ignorada) e integración (exime la alerta del módulo).

## [0.63.1] — 2026-06-28

### Added
- **Observabilidad de qué meteo usa cada módulo** (que no sea "cuestión de fe"):
  - **DS**: el sensor *Posición objetivo* añade el atributo **`alert_source`** = `local` /
    `dynamic_weather` / `none`, para ver de dónde sale (o saldría) la alerta de cada persiana.
  - **DC**: el sensor *Bias forecast* añade el atributo **`forecast_source`** = la entidad
    weather que alimenta el bias por previsión (la de la zona o la de Dynamic Weather).

### Internal
- `coordinator_ds.alert_source` (calculado en `_weather_alert`); atributo en `DsTargetSensor`.
  Atributo `forecast_source` en el sensor `bias_forecast` (DC), vía `_forecast_source()`. Tests
  ampliados.

## [0.63.0] — 2026-06-28

### Added
- **Dynamic Weather alimenta DC y DS automáticamente**: en cuanto existe una entrada *Weather*,
  el módulo **publica** su estado (fuente activa + alerta) y:
  - **DC** usa esa fuente para el **bias por previsión** si la zona no tiene *Meteo/weather*
    configurado.
  - **DS** usa la **alerta** del módulo para la protección anticipatoria si la persiana no
    tiene ninguna *Alerta meteo* configurada.
  En ambos casos, **la configuración por módulo sigue mandando** (si la pones, gana). Antes
  había que enchufar el Weather a mano en cada zona/persiana.

### Internal
- `coordinator_weather` publica `DATA_WEATHER = {source, alert}`. `coordinator_dc._forecast_source()`
  (zona o, en su defecto, la fuente publicada). `coordinator_ds._weather_alert` usa la alerta
  publicada cuando no hay sensores de alerta locales. `DATA_WEATHER` se limpia al descargar la
  entrada Weather. Tests (publicación + auto-consumo DC/DS + override por módulo).

## [0.62.0] — 2026-06-28

### Added
- **DS · override manual (no quedarse atrapado)**: al mover la persiana **a mano** (por la
  entidad gestionada de la integración), ahora **mantiene tu posición y pausa el automático**
  para que la lógica de confort (sol/escudo/free-cool/amanecer/noche) **no la vuelva a cerrar**
  detrás de ti. El override se mantiene hasta que:
  - pulses el botón nuevo **«Reanudar automático»**, o
  - pasen las horas configuradas en **«Override manual (h)»** (por defecto **4 h**; `0 = sin
    caducidad`).
  Las **protecciones de seguridad** (bloqueo, alerta meteo, lluvia, tope de viento) **siguen
  mandando** por encima del override. Nuevo sensor **«Override restante»** (minutos).

### Internal
- `ds_engine`: rama `manual_hold` en `decide_cover` (tras override/alerta/lluvia, antes de
  privacidad/amanecer/noche/estacional), añadida a `PROTECTED`; `DsInputs.manual_pos` +
  `DsConfig.override_hours`. `coordinator_ds`: `arm_manual_override`/`clear_manual_override`/
  `override_remaining_min` + caducidad. `cover.py` arma el hold en las órdenes del usuario.
  Nueva plataforma `button` en DS (`ResumeAutoButton`) + `DsOverrideRemainingSensor`. Opción
  `override_hours` (categoría Posiciones) y traducciones EN/ES. Tests de motor + integración.

## [0.61.0] — 2026-06-28

### Changed
- **VMC · detección de bypass por temperatura** (recuperador): el estado del recuperador
  (`recovering` / `bypass` / `idle`) ahora detecta el **free-cooling** con la **regla física
  del fabricante** (manual Siber DF Optima BP §4.2): la compuerta del bypass abre cuando la
  **Tª exterior > umbral** (10 °C por defecto) **y** además es **más fresca que el interior**.
  Antes solo se deducía de forma indirecta (cuando la eficiencia se desplomaba). Así un % de
  rendimiento bajo en una noche de verano se etiqueta correctamente como **bypass** (free-cooling
  intencionado), no como mal rendimiento. La detección por eficiencia se mantiene como respaldo.

### Internal
- `dv_engine.hrv_state`: rama de bypass por temperatura (`intake > hrv_bypass_min_ext_c and
  intake < extract`, con `intake`=T_ext y `extract`=T_int). Nuevo tunable
  `DvConfig.hrv_bypass_min_ext_c = 10.0` + categoría *Recuperador* en opciones (EN/ES). Tests de
  motor (noche de verano→bypass aunque η alta; día caluroso/invierno→recovering).

## [0.60.0] — 2026-06-28

### Changed
- **VMC · refresco inmediato al cambiar de velocidad**: al aplicar una velocidad (manual o
  automática), el ventilador **empuja un refresco del coordinator** (`async_update_listeners`),
  de modo que `sensor.vmc_speed`, potencia y demás reflejan el cambio **al instante** en los
  dashboards, en vez de esperar al siguiente sondeo (~60 s). El `fan.vmc` ya se actualizaba al
  momento; ahora también los sensores que cuelgan del coordinator.

### Internal
- `DvFan._apply_speed`: `self.coordinator.async_update_listeners()` tras fijar `current_speed`
  (en arranque/parada y al fijar V1/V2/V3). Test de integración (cambio de preset → el sensor
  de velocidad se actualiza sin esperar al poll).

## [0.59.0] — 2026-06-28

### Added
- **DS · copiar/clonar configuración entre persianas**: para varias ventanas casi idénticas
  (p. ej. tres del mismo salón) ya no hay que configurarlo todo una a una. Dos vías:
  - **Al crear** una persiana nueva: si ya existe otra, un paso previo permite **elegirla como
    plantilla** → el formulario aparece precargado con todo (orientación, span, climate,
    sensores…) **excepto el cover**, y se **copian sus opciones/tunables**. Solo cambias el
    cover y el nombre.
  - **En una persiana ya creada**: nuevo paso *Clonar de otra persiana* en Configurar → copia
    los datos (excepto el cover) y las opciones del origen sobre esta, y recarga.

### Internal
- `config_flow`: `async_step_shutter` pasa a ser el selector de plantilla (paso `shutter`) y el
  formulario de entidad se mueve a `async_step_shutter_form` (paso `shutter_form`,
  `add_suggested_values_to_schema`); `async_create_entry(..., options=...)` clona los tunables.
  `async_step_clone` en el options flow (menú `clone`, solo si hay otra persiana). Helper
  `_ds_entries`. Traducciones EN/ES (`shutter`/`shutter_form`/`clone`). Tests de flujo
  (copia al crear + clon en existente).

## [0.58.0] — 2026-06-28

### Added
- **DS · escudo de sol directo (opt-in)**: nuevo switch *Escudo de sol directo*. En modo
  refrigeración, cierra ante **sol directo en la fachada aunque fuera haga más fresco** que
  dentro — la ganancia solar a través del cristal calienta la habitación aunque el aire
  exterior esté templado. Por defecto **apagado** (comportamiento anterior: el escudo solar
  solo actúa cuando además hace más calor fuera). Reutiliza el escudo solar existente (fijo o
  geométrico) y respeta los topes; solo cambia **cuándo** se dispara.

### Internal
- `ds_engine`: `DsInputs.sun_gain_shield`; `shield_ok = is_cool and impact > 0 and (hot_out or
  sun_gain_shield)`. `coordinator_ds.sun_shield_enabled` → `DsInputs`. `switch.py`: toggle
  `sun_shield` (translation_key EN/ES). Tests de motor (cool+sol+fresco fuera: opt-in cierra,
  por defecto no) e integración (switch on/off).

## [0.57.0] — 2026-06-28

### Added
- **DS · sensores de contexto de primer nivel en la persiana**: para "atar cabos" de un
  vistazo de por qué actúa la persiana, ahora expone como sensores principales (cada uno solo
  si su fuente está configurada):
  - **Temperatura interior** y **Temperatura exterior** (las que usa el motor, `ds_t_in`/`ds_t_out`).
  - Del **climate** enlazado de la zona: **Modo** (heat/cool/off — lo que gobierna toda la
    cascada), **Consigna** (temp objetivo) y **Temperatura** actual.

### Internal
- `coordinator_ds`: `climate_mode`/`climate_setpoint`/`climate_temp` (lee el `climate` enlazado)
  y `_climate_attr`. `sensor.py`: `DsIndoorTempSensor`/`DsOutdoorTempSensor`/`DsClimateModeSensor`/
  `DsClimateSetpointSensor`/`DsClimateTempSensor` (translation_key EN/ES), creados en la rama
  `MODULE_SHUTTER` según fuentes presentes. Tests de integración (presentes con fuentes /
  ausentes sin ellas).

## [0.56.1] — 2026-06-27

### Fixed
- **VMC · reasentar los relés al arrancar** (corrige V3 pegado tras reiniciar): los relés
  Shelly **conservan su estado físico** al reiniciar/recargar la integración, pero el
  coordinator arranca asumiendo **V1**. Si la primera decisión en auto era también V1 (aire
  limpio), el manejador "solo-al-cambiar" veía `V1 == V1` y **no reasentaba** el hardware →
  un relé V2/V3 que quedó encendido **seguía energizado** (p. ej. 108 W reales) mientras la
  tarjeta mostraba V1. Ahora el ventilador **siempre reaplica** la velocidad lógica
  (restaurada) sobre los relés al añadirse, de modo que el hardware coincide con el estado
  que muestra la integración. (Antes solo se reasentaba en presets manuales.)

### Internal
- `DvFan.async_added_to_hass`: reconcilia siempre vía `_apply_speed(self._logical_speed)`
  (auto incluido), no solo en manual. Test de regresión que espía el driver de relés
  (la captura de servicios no vale aquí: la plataforma `switch` de la integración
  re-registra `switch.turn_on/off` y eclipsa `async_mock_service`).

## [0.56.0] — 2026-06-27

### Changed
- **VMC · razón `iaq_ok` cuando el aire está bien**: cuando el CO₂ y el PM2.5 están **por
  debajo del umbral de V2**, la VMC se mantiene en la velocidad base (V1); la razón ahora es
  **`iaq_ok`** (aire limpio, ventilación base) en lugar de `iaq`. La razón `iaq` queda
  reservada para cuando la calidad del aire **sí** sube la velocidad (V2/V3). Es solo la
  etiqueta de la razón: **no cambia ninguna velocidad ni comportamiento**.

### Internal
- `dv_engine.decide()`: `reason = "iaq" if base >= 2 else "iaq_ok"` en la rama IAQ. Tests de
  motor actualizados (clean-air → `iaq_ok`; CO₂ alto → `iaq`).

## [0.55.0] — 2026-06-27

### Changed
- **VMC · detección de ducha por subida de humedad propia del baño** (corrige falso positivo):
  la ducha se detecta ahora por la **subida de HR del propio baño sobre su línea base**
  (una EMA lenta), no por el **delta con la calle**. Un baño con HR alta pero **estable**
  (p. ej. 55–62 % con exterior seco) ya **no** dispara la velocidad de ducha; solo lo hace
  un **repunte real** de humedad. El **delta con el exterior** pasa a ser únicamente la
  **puerta de efectividad** ("¿merece la pena echar el aire?"): si fuera está más húmedo
  que el baño, hay repunte pero **no se ventila** para expulsar.

### Internal
- `coordinator_dv._shower_signal()` (sustituye a `_rh_delta()`): mantiene `_bath_baseline`
  (EMA por baño, **congelada** mientras la ducha está enganchada), expone `shower_rise` y
  `shower_effective`. Nuevos tunables en `DvConfig`: `shower_rh_delta_on`/`_off` (subida sobre
  base), `shower_baseline_alpha` (velocidad de la línea base), `shower_effective_margin`
  (margen de la puerta de expulsión). Sensor *Subida ducha* y categoría de opciones *Ducha*
  actualizados (EN/ES). Tests de integración reescritos a la nueva semántica + caso de
  "repunte real pero exterior húmedo → no expulsa".

## [0.54.0] — 2026-06-27

### Added
- **VMC · sensor de NOx (índice, observación)**: nuevo campo opcional **Sensor NOx** y su
  sensor, simétrico al de VOC (p. ej. el índice NOx del Sensirion SEN55 de un M5Stack). Es un
  **índice relativo** (~100 nominal, sin unidades) y, como el VOC, **es solo observación**: se
  expone para tablas/histórico pero **no actúa** sobre la ventilación. También disponible como
  mirror (F36).

### Internal
- `CONF_NOX` (en `OPTIONAL_HW`); `coordinator_dv.has_nox()`/`nox_level`; `NoxSensor`
  (`{entry}_nox`, `translation_key` nox, diagnóstico, EN/ES); selector opcional en
  `STEP_USER_SCHEMA` + etiqueta en el paso *Editar entidades*; rol `nox` en los mirrors. Test
  de integración. (NOx/VOC siguen fuera de `decide()` por diseño.)

## [0.53.0] — 2026-06-27

### Added
- **VMC · CO₂ y PM2.5 como sensores de primer nivel**: la VMC expone ahora **CO₂** (ppm) y
  **PM2.5** (µg/m³) como sensores propios (no diagnóstico), con `device_class`
  `carbon_dioxide`/`pm25` → entran bien en tarjetas, histórico y estadísticas. Son el valor en
  vivo de las fuentes que ya tenías configuradas, re-expuesto en el dispositivo de la VMC.

### Internal
- `Co2Sensor`/`Pm25Sensor` (`{entry}_co2` / `{entry}_pm25`, `translation_key` co2/pm25, EN/ES)
  leen `_num(CONF_CO2)`/`_num(CONF_PM25)`; se crean si la fuente está configurada (requerida en
  VMC). Test de integración (valores + device_class + categoría primaria).

## [0.52.0] — 2026-06-27

### Added
- **Persiana · binary_sensor "Al sol"**: por persiana, indica si **el sol directo está
  dando en esa fachada** (on/off). Tiene en cuenta la **orientación** (azimut/span de
  fachada), el **horizonte** y la **sombra del voladizo/alero**, así que es `on` solo cuando
  el sol realmente llega a la ventana (`impact > 0`). Atributo `impact` (0..100). Útil para
  dashboards y automatizaciones ("si el salón está al sol, …").

### Internal
- `coordinator_ds.sun_impact` (calculado con `solar_impact` cada ciclo); `InSunBinarySensor`
  (`{entry}_in_sun`, translation_key `in_sun`, EN/ES). Test de integración (off de noche, on
  con sol en la fachada). Rama DS de `binary_sensor.async_setup_entry` separada de la de VMC.

## [0.51.0] — 2026-06-27

### Changed
- **Persiana · escudo térmico coherente con topes por estación**: el switch *Thermal shield*
  pasa a ser el mando de **prioridad térmica** y unifica sol/sin-sol:
  - **Refrigerando + más calor fuera**: la persiana **no abre más de "Apertura máx.
    refrigerando"** (antes *Escudo térmico %*, sigue **0** = cerrada del todo) **también con sol
    directo** — antes el sombreado geométrico dejaba una rendija (p. ej. 20%) por la que entraba
    el calor; ahora el tope manda y el geométrico solo puede **cerrar más** (deslumbramiento).
  - **Calentando + sol**: nuevo tope **"Apertura máx. calentando"** (def. **100** = ganancia
    plena) para limitar deslumbramiento/sobre-ganancia si se quiere.
  - **Apagado** = comportamiento previo (geométrico deja luz; ganancia plena).

### Internal
- `DsConfig.heat_max_open_pct` (100). `decide_cover`: en `shield_ok` con `heat_shield`,
  `pos = min(pos, heat_shield_pct)` (reason `summer_heat_shield` si el tope manda); en
  `winter_solar_gain` con `heat_shield`, `pos = min(100, heat_max_open_pct)`. Relabel de
  `heat_shield_pct` → "Apertura máx. refrigerando" (mismo campo, sin migración) + nuevo campo en
  la categoría `shield` (EN/ES). Tests motor (cap cool con sol; geo cierra más; cap heat;
  defaults).

## [0.50.0] — 2026-06-27

### Changed
- **i18n de entidades (fase 2: sensores y binary_sensors)**: completa el punto 4. **Todos** los
  sensores (Posición, Posición objetivo, Motivo, Energía, Potencia, Velocidad, Modo, Estado
  operativo, Vida del filtro, Rendimiento recuperador, temperaturas HRV, subida de ducha,
  Margen de red, Tarifa, Consumo/Coste/Potencia de casa, Zonas, sensores DC de diagnóstico…)
  y los **binary_sensors** (Estado, Presencia, Riesgo de condensación, Demanda real, Ventana
  inferida, Alerta meteo, Escasez…) **siguen ahora el idioma de HA** vía `translation_key`. Se
  acaba la mezcla ES/EN en las entidades.

### Internal
- `sensor.py`/`binary_sensor.py`: `_attr_name` → `_attr_translation_key` (estáticos + tablas
  por-descriptor `_HOURS`/`_HRV_TEMPS`/`_DC_SENSORS`/`_DC_LEARN`; `ZoneOccupancy` con
  `translation_placeholders`). Secciones `entity.sensor` (54) + `entity.binary_sensor` (8) en
  strings/en/es. `test_translations.py`: completitud de las tablas + **paridad de claves** entre
  los 3 ficheros. `BusSensor` mantiene el título de la entrada (por diseño); los espejos F36
  (`(espejo)`) quedan para una limpieza futura. `entity_id` intacto en instalaciones existentes.

## [0.49.0] — 2026-06-27

### Changed
- **i18n de entidades (fase 1: interruptores y números)**: los **switches** (Solo observar,
  Privacidad, Bloqueo, Amanecer gradual, Aislamiento nocturno, Sombreado geométrico, Escudo
  térmico, Limitación de pico, Umbrales adaptativos, Programador, Horas de silencio,
  Vacaciones, Lead adaptativo, Anti-ciclado…) y los **números** (Posición privacidad/bloqueo,
  umbrales CO₂/PM, Vida del filtro, Temporizador, Nivel máx. en silencio) **ya siguen el idioma
  de HA** vía `translation_key` — se acabó la mezcla ES/EN en esas entidades. En HA en español
  salen en español; en inglés, en inglés. Sin cambios de `entity_id` en instalaciones
  existentes.

### Internal
- `switch.DsToggle` y `number.ThresholdNumber`/`CoordNumber` pasan de `_attr_name` hardcodeado a
  `_attr_translation_key`. Nuevas secciones `entity.switch` / `entity.number` (name) en
  strings/en/es. Test `test_translations.py` (toda clave de switch/number tiene nombre en los 3
  ficheros). Sensores/binary_sensors quedan para la fase 2.

## [0.48.0] — 2026-06-27

### Changed
- **UX · textos más claros**: el sensor de salud de cada módulo se llama ahora **"Estado"**
  (con `device_class problem` HA muestra **OK / Problema**), en vez del raro **"Degradado: OK"**.
  Y la categoría **"Slew rate"** pasa a **"Movimiento progresivo"** (campos: *Movimiento
  progresivo* y *Paso de movimiento (%)*), con descripción *"limita cuánto puede cambiar la
  posición de la persiana en cada ciclo"*.

### Internal
- `DegradedBinarySensor._attr_name` "Degradado" → "Estado". `options_spec`: categoría `slew`
  relabel + campos `slew_enabled`/`slew_step_pct`. Traducciones `cat_slew` (menú + título +
  descripción + data) en strings/en/es. Sin cambios de lógica (el `unique_id`/entity_id no
  cambia en instalaciones existentes).

## [0.47.0] — 2026-06-27

### Changed
- **Opciones · todas visibles, con niveles (sin necesidad del modo avanzado de HA)**: el menú
  de *Configurar* ya **no oculta** categorías detrás del "modo avanzado" del perfil de HA —
  todo está accesible (quien monta un BMS las necesita). Para no abrumar al principio, cada
  categoría se **etiqueta y ordena por nivel**: **básicas primero**, luego **(Avanzado)** y por
  último **(Experto)**, así sabes que esas zonas tienen más miga y no hay por qué tocarlas el
  primer día. (HA no permite color/punto por ítem de menú, así que se usa el sufijo de texto,
  que es la vía nativa.)

### Internal
- `options_spec`: `category_tier()` + `_CAT_ADVANCED`/`_CAT_EXPERT`; `categories()` muestra todas
  y las ordena por nivel (estable, conserva el orden del SPEC dentro de cada nivel). `config_flow`
  deja de gatear por `show_advanced_options` (menú, dispatcher y schema). Sufijos
  `(Avanzado)`/`(Experto)` / `(Advanced)`/`(Expert)` en las etiquetas de menú (strings/en/es,
  41 categorías). Test de niveles (sin huérfanos, disjuntos, menú ordenado).

## [0.46.0] — 2026-06-27

### Fixed
- **Persiana · el amanecer gradual ya no abre contra el sol/calor en refrigeración**: el
  *Gradual sunrise* (F19) tenía más prioridad que la protección estacional, así que al
  amanecer abría en pasos de 10% **aunque el escudo solar (cool + sol directo + calor)
  quisiera cerrar** — entraba el sol de la mañana. Ahora el amanecer **cede ante la
  protección de refrigeración** (`cool_protect`: en `cool`, más calor fuera y con sol directo
  o con el *Thermal shield* activo): deja que el escudo solar/geométrico o el térmico
  mantengan la persiana protegida. En **calefacción** el amanecer sigue igual (da luz/ganancia
  por la mañana), y si en `cool` no hay amenaza (ni calor ni sol) también rampa normal.

### Internal
- `decide_cover`: `is_cool`/`is_heat`/`temps_ok`/`hot_out` se calculan antes de la cascada y
  la rama del amanecer se gatea con `not cool_protect`. Tests: amanecer cede al escudo solar y
  al térmico; rampa cuando no hay amenaza en cool; rampa en calefacción.

## [0.45.0] — 2026-06-27

### Added
- **VMC · observabilidad para tunear (por qué ventila y por qué no)**: para poder afinar la
  VMC en pruebas sin adivinar los umbrales:
  - **4 temperaturas del recuperador como sensores de primer nivel**: *HRV supply*
    (insuflación), *HRV intake* (admisión), *HRV extract* (extracción) y *HRV exhaust*
    (expulsión) — graficables por separado (además de seguir como atributos del sensor de
    rendimiento). Cada una aparece solo si su sonda está configurada.
  - **Sensor "Shower humidity rise"**: la **subida real** de humedad que dispara el boost de
    ducha = humedad del baño − humedad exterior (%). Como atributos lleva el **umbral de
    disparo** (`trigger_on`/`off`), el baño ganador y si está **habilitado**. Hace tuneable la
    ducha: si nunca llega al umbral —o sale `unknown` porque **falta el sensor de humedad
    exterior**— se ve al instante (el boost exige humedad de baño **y** exterior, y subida ≥ 8%).
  - **Sensor "Reason" enriquecido**: ahora expone como atributos los **valores en vivo junto a
    los umbrales en uso** (CO₂ y su `co2_v2/v3`, PM y `pm_v2/v3`, adaptativos o fijos), la
    subida de ducha y el margen de secado — el *por qué* de la velocidad, en un sitio.

### Internal
- `coordinator_dv` cachea `shower_rise`, `shower_gate` e `iaq_snapshot` por ciclo (umbrales
  efectivos = adaptativos si hay, si no fijos). `sensor.py`: `HrvTempSensor` (×4),
  `ShowerRiseSensor`, atributos en `ReasonSensor`. Tests (4 sondas como sensores; shower rise
  + trigger + enabled; thresholds en Reason). Nombres de sensor hardcodeados (sin cambios de
  traducción).

## [0.44.0] — 2026-06-26

### Added
- **Persiana · observabilidad para observe-only (target + motivo)**: dos sensores nuevos por
  persiana que hacen útil el modo *Observe only* (que calcula la decisión pero no mueve el
  `cover`):
  - **Target position** (`%`): la posición que la cascada **quiere**. En observe-only es el
    dato clave — "lo que habría hecho" — graficable aunque la persiana real no se mueva.
    Lleva como atributos el `reason`, el `peak_reason` y los `details` de la decisión
    (`impact`, `penetration_m`, `t_in`/`t_out`…).
  - **Reason**: el **motivo** (rama ganadora de la cascada: `summer_solar_shield`,
    `winter_cold_shield`, `meteo_rain`, `meteo_alert`…) como **estado graficable**, para
    seguir *por qué* a lo largo del día y validar la lógica antes de soltar el hardware.

### Internal
- `DsTargetSensor` (`{entry}_target`, %, MEASUREMENT, diagnóstico) y `DsReasonSensor`
  (`{entry}_reason`, diagnóstico) en `sensor.py`, leyendo `coordinator.data` (DsDecision).
  Espejo del `ReasonSensor` de la VMC. Test de integración (ambos presentes; target = lo
  comandado aunque el cover real esté a otro %; reason = la rama).

## [0.43.0] — 2026-06-26

### Changed
- **Persiana · el escudo térmico pasa a ser opt-in (switch dedicado)**: el escudo térmico de
  verano e invierno (v0.41/0.42) ahora **se activa con un interruptor** *Thermal shield*
  (**apagado por defecto**), como el resto de funciones de persiana. Nueva categoría de
  opciones **Escudo térmico** que **explica claramente qué hace según el termostato**: en
  **cool** mantiene cerrada si fuera hace más calor y no da el sol; en **heat** de día cierra
  si fuera está más frío y abre si está templado. **Apagado** = comportamiento previo a
  v0.41 (en frío abre sin sol; en calor aísla siempre que no hay sol).

### Internal
- `DsInputs.heat_shield` (gating de `summer_heat_shield` y de la rama día de invierno
  `winter_cold_shield`/`winter_mild_open`); `coordinator_ds.heat_shield_enabled` (RestoreEntity
  vía el switch); `_ToggleDesc("heat_shield", "Thermal shield")` en `switch.py`. `heat_shield_pct`
  y `cold_delta` se mueven de `positions`/`thermal` a la categoría nueva `shield` (con título +
  descripción heat/cool). Tests: motor (on cierra; off abre en verano y aísla siempre en
  invierno) + integración (switch presente; off no protege, on sí). Paridad strings/en/es.

## [0.42.0] — 2026-06-26

### Added
- **Persiana · escudo de frío de invierno (simétrico al de verano)**: en modo **calor**, sin
  sol directo en la fachada, ahora distingue noche y día. **De noche** (sol bajo el horizonte)
  **cierra siempre** para aislar, como hasta ahora. **De día** cierra para aislar
  (`winter_cold_shield`) **solo si fuera está más frío** que dentro (por el nuevo `cold_delta`);
  si fuera está **igual o más templado**, **deja la persiana abierta** para dejar entrar luz
  (`winter_mild_open`) en vez de cerrar a ciegas. Con **sol directo** sigue abriendo para
  ganancia solar (`winter_solar_gain`). Nuevo parámetro **`cold_delta`** (ΔT frío, def. 0.8 °C)
  en *Deltas térmicos*; la posición de cierre reusa `winter_night_pct`.

### Internal
- `DsConfig.cold_delta` (0.8) + rama `is_heat and impact == 0` reescrita en `decide_cover`:
  `sun_elevation > 0` distingue día/noche (el coordinator no rellena `ins.night`); sin sol o
  sin Tª → `winter_night_insulate` (legacy, back-compat); día + `t_out < t_in − cold_delta` →
  `winter_cold_shield`; día templado → `winter_mild_open` (100). Categoría `thermal` (EN/ES,
  paridad). Tests: motor (noche aísla aunque temple; día frío cierra; día templado abre; sin
  Tª aísla) + integración (calor + día + sol fuera + frío → `winter_cold_shield`).

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
