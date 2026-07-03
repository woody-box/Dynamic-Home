# SPEC — Dynamic Climate (DC) · port a integración HA

> Destilación del pipeline de DC (clima) tal y como está implementado hoy en
> `custom_components/dynamic_home` (`dc_engine.py` = motor puro; `coordinator_dc.py`
> = orquestación en HA). **Fuente de verdad:** el código Python; este documento
> debe describir lo que hace `decide()` y el coordinator, no la inversa.
>
> Una zona DC = una entidad `climate`. DC es el **cerebro** de la suite: además de
> calcular su propia consigna, **publica intenciones al bus** (SDHB) que DS/DV
> consumen, y consume las dirigidas a sí mismo (self-bias).

---

## 1. Qué hace DC

Por cada ciclo, y para una zona:

1. Resuelve la **dirección efectiva** (heat/cool/off) — el modo del usuario
   gateado por el changeover comunitario (§4).
2. Calcula la **consigna objetivo** (target, °C) = consigna base + biases (§2).
3. **Decide el modo** con una precedencia de seguridad (§3): override, rocío,
   ventana, y solo entonces heat/cool/off.
4. **Publica al bus** la intención solar (heat→ganancia, cool→escudo), con
   targeting por fachada soleada (§10).
5. Ejecuta las capas periféricas que NO alteran el target pero sí la actuación o
   la observabilidad: ventana inferida (§5), índice de moho (§6), demanda real
   (§7), anti-ciclado (§8), anti-pico (§9), multi-emisor/conducto (§10),
   aprendizaje adaptativo (§11), energía (§12).

**Regla transversal (v0.95.0):** todo lo anterior evalúa con la **dirección
efectiva** (`_effective_hvac`), nunca con el modo que el usuario dejó en el
termostato. Condensación, ventana inferida, bias de fachada, forecast,
aprendizaje, energía y conducto compartido comparten esa misma dirección real.

## 2. Consigna base + biases (pipeline del target)

```
target_final = quantize( clamp( base + clamp(Σ biases, ±lim) + sdhb_bias,
                                [min, max] ),
                          step )
```

- **base** (`base_active`): consigna base según modo y día/noche (noche =
  elevación solar ≤ −3°; en calor baja `delta_night`, en frío sube). Variantes de
  vacaciones (bases y límites propios). **F21 (programador semanal):** si hay un
  tramo activo, su valor fija la BASE absoluta (`base_source="schedule"`, sin
  atenuación noche); vacaciones sigue ganando.
- **Σ biases**: suma de correcciones en °C, **limitada** a `±max_mods` (0.8 def):
  - `bias_exterior` — compensación por Tª exterior (amortiguada por
    `insulation_factor`). En frío la rama es **negativa** (más calor entra → baja
    la consigna de refrigeración; nunca la sube justo cuando más aprieta).
  - `bias_vmc` — compensación por la VMC (velocidad 1/2/3 + signo de ΔT ext−int).
  - `trend` (tendencia) — anticipa por la deriva de T interior (°C/h,
    EMA-suavizada con deadband), escalada por el **lead** (§11).
  - `brake` (freno) — frena el overshoot solo cuando la tendencia ya ayuda al
    modo, por umbrales graduados.
  - `forecast` — anticipa por la previsión (`weather.get_forecasts`; extremo en
    la ventana de N h). **Solo alivia**: se anula si la sala aún no ha alcanzado
    la base (no "coast" con la sala fría en calor / caliente en frío).
  - `tariff` (F34) — empuje de base por tarifa (barata→precarga masa;
    pico→coast). Off por defecto (`tariff_bias_c=0`).
  - `fachadas` (`extra_bias`) — ganancia solar por fachada soleada: la apertura
    de las persianas al sol alivia la demanda (heat y cool). Ver §10.
- **sdhb_bias**: corrección por consumir una intención dirigida a DC
  (`solar_gain` en calor → −0.5; `solar_shield` en frío → +0.5).
- **clamp** a `[min, max]` (heat/cool, variantes vacaciones) y **quantize** a
  `step` (0.5 °C, half-up).

### bias_exterior
```
heat:  t_ext ≤ u_frio        → +strong·ais
       t_ext ≤ u_frio + 5    → +mild·ais
cool:  t_ext ≥ u_calor       → −strong·ais
       t_ext ≥ u_calor − 5   → −mild·ais
```

El desglose de cada bias se expone en `DcDecision.details` (observabilidad:
`base`, `base_source`, `target_raw`, `mods_total`, `lead_h`, `lead_source`,
`night`, y cada `bias_*`).

## 3. Precedencia de la decisión de modo

`decide()` resuelve en este orden (la **dirección** heat/cool se toma del **modo
efectivo**, ya gateado por el changeover):

| # | Guarda | Resultado | reason |
|---|--------|-----------|--------|
| 1 | override activo + temp | fija target manual, modo = efectivo | `override` |
| 2 | `dew_risk` (rocío real, Magnus) | **OFF**, limpia intención | `off_dew` |
| 3 | `window_lockout` (sensor real) | **OFF** | `off_window` |
| 4 | `window_inferred` (§5) | **OFF** | `off_window_inferred` |
| 5 | modo efectivo ∉ {heat,cool} | **OFF** | `off` |
| 6 | resto | **heat/cool** + target + intención | `heat`/`cool` |

Es decir: **override → dew_risk (OFF) → window_lockout/inferida (OFF) →
heat/cool → off**. Toda guarda OFF limpia la intención publicada al bus.

### 3.1 · Rocío / condensación (dew_risk)
Solo en `cool`. Con **temp. de agua/suelo** configurada, el chequeo es contra la
**superficie fría real** donde condensa: riesgo si `(suelo − punto_rocío) <
cond_margin_c`. Sin ella, cae al chequeo por aire (`t_int − dp < dew_spread_min`).
El coordinator expone el desglose (`dew_point_c`, `cond_spread_real`,
`cond_margin_corrected`) y niveles de protección `surface/air/none`
(`cond_protection`); levanta un *repair* si una zona enfría una superficie fría
sin protección de superficie (`cond_unprotected`).

## 4. Changeover comunitario y modo efectivo (F37)

En zonas **comunitarias** (perfil F26 `community` = distribución central
compartida: solo se abre la válvula, el agua la marca el edificio) la **dirección
efectiva** la fija el **changeover de casa** (`heat`/`cool`/`off`), no el modo del
termostato. `_effective_hvac()`:

- Zona no comunitaria, o sin changeover configurado (`None`) → mantiene su modo
  (back-compat exacto).
- Comunitaria con changeover:
  - modo del usuario `off`, o changeover `off`/desconocido → **off** (temporada).
  - changeover **coincide** con el modo → corre en esa dirección.
  - changeover **contradice** al modo (pides **Calor con agua fría** circulando) →
    la zona **reposa (off)**, marcando `changeover_conflict = True`. **Nunca
    invierte en silencio** la orden del usuario; para "seguir al edificio" existe
    el switch dedicado (`follow_changeover`, que resuelve el modo desde el
    changeover *antes* del motor).

**Atributos nuevos** en la entidad climate: `hvac_effective` (la dirección real
de este ciclo) y `changeover_conflict`. El changeover admite **override por
zona** (además del de casa) vía la entrada de Zonas.

**Clave (arreglo v0.95.0):** el **modo efectivo gobierna TODO el pipeline**. Antes
la condensación, la ventana inferida, el bias de fachada, el forecast, el
aprendizaje, la energía y el conducto compartido evaluaban con el modo de la UI
mientras el motor corría con el del edificio; ahora todos usan `eff`.

## 5. Ventana abierta: sensor real + inferencia (F20)

- **Sensor real** (`window_lockout`) — preferente cuando existe; OFF directo
  (`off_window`), sin cálculo.
- **Inferencia por temperatura** — solo **sin sensor** (`has_window_infer`).
  Detecta la firma de ventana abierta: la zona **acondiciona** y la T interior se
  mueve **en contra** de la demanda más rápido que `window_drop_cph` (cae mientras
  calientas / sube mientras enfrías). Con **debounce**: arma tras
  `window_confirm_min`, desarma por estabilización (`window_release_min`) **o**
  por timeout de seguridad (`window_max_lockout_min`). Latch → OFF
  (`off_window_inferred`) + `binary_sensor` + evento `dynamic_home_window`.
- **Fallback de demanda (v0.96.0):** sin señal de demanda real (F27), la "válvula
  abierta" se infiere de `t_int` vs la última consigna (no de "el modo está
  encendido"), para que un **golpe de sol con el aire ya saciado** no bloquee la
  zona 30 min por un falso positivo.

Una ventana (real o inferida) también **aborta el aprendizaje** del ciclo.

## 6. Índice de moho (F22)

Modelo simple: **horas por encima de un umbral de HR con decaimiento**
(`mold_index_step`). Por encima de `mold_rh_threshold` el índice crece con las
horas transcurridas; por debajo **decae** exponencialmente (`mold_decay_h`);
acotado a `[0, mold_cap_h]`. Latch con **histéresis** (`mold_on_h`/`mold_off_h`).

Al armarse (`_mold_step`): levanta *repair* + evento `dynamic_home_mold`, y
**dispara secado**:
- **por bus** → `hub.publish("request_dry", target="dv", prio 60, ttl 1800)`; DV
  aplica su propio gate `dp_diff` (solo seca si el exterior está más seco).
- **deshumidificador** opcional (`_drive_dehumidifier`).

**Decaimiento con sensor caído (v0.96.0):** con la fuente de HR en None el índice
**decae** en vez de congelarse; quitar la fuente o descargar la entrada apaga el
deshumidificador y limpia el request (un latch armado dejaba el deshumidificador
encendido para siempre).

## 7. Demanda real de válvula (F27)

`_real_valve_open` resuelve la demanda con prioridad **c > b > a**:

- **(c)** relé/potencia real (Shelly): numérico → umbral `valve_power_min` (W);
  si no, on/off. La más fiable — también ve el **termostato analógico de backup**.
- **(b)** helpers explícitos de demanda calor/frío para el modo activo.
- **(a)** `hvac_action` del `climate` (heating/cooling → True; idle/off → False).

`_valve_demand` prefiere esta señal real; si no hay ninguna, **cae a inferir**
`t_int` vs `target` (comportamiento legacy). Diagnóstico: `has_real_demand`,
`real_demand_source` (`valve`/`helper`/`hvac_action`/`inferred`),
`real_demand_open` + `binary_sensor` "Demanda real". Esta señal alimenta el
Adaptive Lead (§11), la energía (§12) y la ventana inferida (§5).

## 8. Anti-ciclado de compresor (F09)

Protege el compresor con **min ON**, **min OFF** y **máx arranques/hora**
(default 6) sobre el **agregado del compresor compartido** (`_anticycle` en
`hass.data`: cualquier zona ON lo despierta; el flap de una zona no cuenta como
arranque). `_anticycle_step` conduce la zona a OFF mientras retiene
(`anticycle_hold`/`anticycle_reason`).

- **Gated por F26:** solo con **compresor no comunitario**
  (`profile.compressor`); en gas/eléctrico/aerotermia comunitaria no participa.
- **La seguridad cede:** si DC quería correr pero una guarda (condensación/
  ventana) forzó OFF (`safety_off`), el guard **cede** el min-ON.
- **Registro de la parada en el min-ON (v0.96.0):** si la demanda cae dentro del
  min-ON, la parada **se registra** y el rearranque respeta min-OFF y el contador
  (antes el hub mantenía "encendido" un compresor ya parado y el rearranque se
  saltaba el min-OFF). Una zona retenida por el anti-pico ya no mantiene
  "despierto" el agregado.
- **Autosize opcional:** con learning maduro, dimensiona min ON/OFF desde el lag
  térmico aprendido (`anticycle_bounds`, acotado por seguridad).
- **Canal por emisor (F25):** una zona conduce un canal de compresor por emisor
  heat-pump distinto (`compressor_id`); el hold F09 gatea solo esos emisores.

## 9. Anti-pico eléctrico (F03)

`PeakLoadHub` (`_peak_dc`) escalona los arranques de calefacción eléctrica bajo
un presupuesto de casa. `_peak_step`:

- **Gated por F26:** solo con carga **eléctrica no comunitaria**
  (`profile.peak`). Una zona ya retenida por F09 no consume hueco de pico.
- **Modo del límite:** por **vatios** (medidor real de red vía Energía F34, o
  `peak_max_power_w`, o `est_w_on` estimado) o, si no, por **N zonas**
  (`peak_max_zones`). Un medidor de red da headroom que **aprieta** cualquier cap
  estático, nunca lo afloja.
- **Prioridad por desviación:** las zonas en cola se ordenan por la desviación de
  temperatura (`staging.deviation`); `peak_stagger_s` separa los arranques.
- **Bypass de confort:** una desviación severa (`peak_comfort_bypass_c`) se salta
  el gate — el confort gana al peak-shaving. **Reserva su hueco (v0.96.0):** el
  bypass **ocupa** su presupuesto (`force_grant`) en vez de desaparecer de la
  contabilidad (o el total dispararía el ICP igual). Una carga pequeña que cabe ya
  no cede indefinidamente ante una grande que nunca cabrá; y el hueco de una zona
  en marcha sigue al **contador real** en vez de congelarse en la foto del
  arranque.

## 10. Multi-emisor, staging y conducto compartido (F25)

Una zona tiene **1..N emisores** (`emitters.py`); lista vacía = ruta legacy de un
solo dispositivo (la entidad climate lo conduce). `_build_emitter_commands` mapea
la única decisión sobre cada emisor:

- **Primario** (seleccionable por modo) → lleva la consigna del motor.
- **Apoyo (staging, `staging.py`):** arma cuando el primario **va por detrás**
  (`support_dev_on` sostenido `support_confirm_min`) y se retira con histéresis
  (`support_dev_off`/`support_release_min`).
- **Gating:** un OFF/seguridad o el hold de **pico** apagan TODOS los emisores; el
  hold de **F09** solo los heat-pump. Un emisor switch/válvula sin termostato
  propio sigue la **demanda real** (§7).
- **Farewell:** un emisor borrado del editor recibe un OFF de despedida y su latch
  de staging se poda (quedaba congelado en su último estado).

### 10.1 · Conducto compartido (Fase B)
`_shared_emitter_step` reconcilia un conducto que sirve a varias zonas del grupo
(`SharedEmitterHub`). Cada hermana reporta su demanda; el **owner** conduce la
unidad desde la orden reconciliada (agregación ponderada por `zone_demand_weight`,
o peor-parada/prioridad/media); las no-owner sueltan la unidad.

**Guarda de sobre-acondicionamiento (corregida v0.96.0):** corta la unidad cuando
la zona **más satisfecha** llega a `consigna + shared_undershoot_margin` (lado de
sobre-acondicionado), **nunca** en `consigna − margen` (que dejaba al salón sin
calor para siempre porque un dormitorio ya caliente cruzaba su consigna), y
**nunca mientras otra zona siga genuinamente rezagada**. Si el **owner está
apagado**, el conducto sigue la dirección que piden las **hermanas** en vez de
apagarse para todas. No aplica con **rejillas motorizadas** (control real por
zona).

### 10.2 · Perfil de instalación (F26)
`install.profile(generador, distribución, emisión)` deriva la inercia (defaults de
lead/anti-ciclado) y tres flags que gatean lo anterior:
- **`community`** — distribución central compartida (solo válvula) → F37 gatea la
  dirección; **sin F09 ni F03**.
- **`compressor`** — habilita F09.
- **`peak`** — habilita F03 (eléctrica directa o aerotermia individual).

En zona multi-emisor el perfil sale de la terna del emisor primario.

## 11. Aprendizaje adaptativo (Adaptive Lead)

Opt-in. Aprende por zona la **tasa** de calentamiento/enfriamiento (°C/h), el
**overshoot** más allá de consigna y el **lag térmico** OFF→pico, vía una máquina
de ciclos ON→settling→pico (`_learn_step`/`_finalize_cycle`). De ahí sale el
**horizonte de anticipación** (`lead_gain_adaptive`) que sustituye al modelo
físico (`compute_lead`, que crece con el gap int/ext y el viento).

- **Alimenta el motor** solo si está habilitado, sano y con ≥1 ciclo completado;
  si no, el motor usa el lead físico. Pausa el aprendizaje si degradado o con
  ventana abierta.
- **Normalización por dirección (v0.96.0):** las muestras de rate y overshoot se
  **normalizan por signo** heat/cool antes de la EMA (los ciclos de frío,
  negativos, cancelaban los de calor y el lead aprendido era basura).
- **Clamp tarifario (v0.97.0):** la modulación por tarifa (`tariff_lead_mult`:
  barata amplifica, pico atenúa) se acota a los **límites del modelo fuente** —
  adaptativo (`lead_adaptive_*`) o físico (`lead_*`) —; antes clampar un lead
  adaptativo a los límites físicos recortaba en silencio un lead aprendido de 4 h
  a 3 h en un suelo radiante.
- Servicio `reset_learning` para descartar un modelo envenenado (p.ej. tras
  cambiar la aerotermia) sin borrar la entrada.

## 12. Energía (F06)

`_accumulate_energy` integra kWh mientras la zona pide calor/frío: **medidor real**
preferente (`CONF_POWER_METER`), o **estimación** `est_w_on` mientras la demanda
(real F27 o inferida, en la dirección **efectiva**) está activa. Expone
`energy_kwh` (sensor `energy`/`total_increasing`, entra en el panel de Energía) y
`power_w` instantáneo.

## 13. Bus (lo que hace de DC el cerebro)

Según el modo **activo** de la decisión, DC publica a su target de persianas:

| Modo DC | Intención publicada | Efecto en DS |
|---|---|---|
| `heat` | `request_solar_gain` | abrir para ganar sol |
| `cool` | `request_solar_shield` | cerrar para bloquear sol |
| `off`  | *(clear)* | sin intención |

### 13.1 · Targeting solar dinámico
En vez de un target fijo, DC calcula con `sunlit_facades(sun_az, sun_el, facades,
spans)` qué fachadas ilumina el sol (sobre el horizonte y dentro del `span/2` de la
fachada) y publica **solo a esas fachadas** (`ds_fXXX` registradas en
`hass.data`). Al moverse el sol reconcilia los slots (limpia las que dejan de estar
soleadas → se reabren, publica en las nuevas). Cada fachada aporta su ángulo de
aceptación (`facade_span_deg`): estrecha (60°) solo reacciona de frente; amplia
(180°) medio día. **Sin datos de sol pero con fachadas registradas → no publica
nada** (un broadcast a prio 70 clamparía persianas de noche); sin fachadas →
fallback al target configurado (`ds` por defecto).

DC también **consume** la intención dirigida a sí mismo (self-bias, §2) y expone el
explicador de conflictos del bus (`bus_explain`, evento `dynamic_home_conflict`).
En pausa deja de influir en el bus (limpia sus slots).

## 14. Actuación e implementación

| Concepto | Implementación |
|---|---|
| pipeline del target | `dc_engine.assemble_target()` + `decide()` (motor puro) |
| orquestación / capas | `coordinator_dc.DcCoordinator._async_update_data()` |
| biases, dew, lead, mold, staging… | funciones puras del engine + módulos (`install`/`emitters`/`staging`/`shared_emitter`/`schedule`/`comfort`/`energy`) |
| publicación al bus | `DcCoordinator._publish()` → `SdhbHub` |
| termostato virtual/real | entidad `climate` gestionada (`RestoreEntity`) |

Con termostato real (`dc_climate`) la entidad aplica modo y consigna
(`set_hvac_mode`/`set_temperature`) **solo al cambiar** (anti-jitter
`apply_min_delta`); la conducción va **serializada** y solo se da por aplicada tras
el éxito del servicio (v0.97.0). Sin termostato, DC es *advisory* (solo publica al
bus y muestra la consigna). En **observar/pausa** no actúa hardware (ni
deshumidificador, ni emisores, ni bus).

## 15. Estado

- ✅ Consigna base + biases (exterior, VMC, tendencia, freno, forecast, tarifa,
  fachadas) + límites/clamp/quantize, con dew-risk real (Magnus) y lead
  físico/adaptativo.
- ✅ Changeover comunitario (F37) + modo efectivo gobernando todo el pipeline.
- ✅ Ventana real + inferida (F20), índice de moho (F22), demanda real (F27).
- ✅ Anti-ciclado (F09), anti-pico (F03), multi-emisor/staging/conducto (F25),
  perfil de instalación (F26).
- ✅ Aprendizaje adaptativo normalizado por dirección + clamp tarifario.
- ✅ Publicación al bus con targeting solar por fachada; energía (F06).
</content>
</invoke>
