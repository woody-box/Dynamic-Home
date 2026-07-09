# SPEC — Dynamic Shutter (DS)

> El "cerebro" de las persianas de Dynamic Home. Una ventana = una entidad
> `cover`. Comparte el bus **SDHB** (`SdhbHub`) con DV/DC.

Cada ciclo, DS calcula una **posición objetivo** `0..100` (% abierta) y un
**reason code** de trazabilidad, mediante una **cascada de prioridades** y unos
**topes/caps** posteriores. La posición se aplica a la `cover` física a través de
una entidad `cover` gestionada (que además expone la posición real, el objetivo y
el motivo como sensores).

---

## 1. Cascada de decisión

El **primer** caso que aplica fija `pos` y `reason` (de mayor a menor prioridad):

| # | Capa | Condición | Posición | `reason` |
|---|------|-----------|----------|----------|
| **1** | **Override manual** | `manual_pos` armado (mano / botón externo / automatización) | `manual_pos` | `manual_hold` |
| 1b | **Bloqueo / Override** | `lock` / `hold` / `ttl` activos | `override_pos` | `ov_lock` · `ov_hold` · `ov_ttl` |
| 1c | **Alerta meteo** (F17) | sensor de alerta activo | la más protectora | `meteo_alert` |
| 2 | **Lluvia** | `weather_protect` + lloviendo | `rain_close_pct` | `meteo_rain` |
| 2c | **Simulación de presencia** | casa/zona en **Away** + switch global | día abre / noche cierra (jitter) | `presence_sim` |
| 2d | **Sleep** | ámbito de zona en Sleep | `sleep_pct` | `mode_sleep` |
| 3 | **Privacidad** | dentro de la ventana horaria | `privacy_pos_pct` | `privacy_time` |
| 4 | **Amanecer gradual** (F19) | rampa activa **y** sin protección de frío/sol* | paso de apertura | `dawn_ramp` |
| 5 | **Aislamiento nocturno** (F16, opt-in) | switch on + sol bajo horizonte | abrir/cerrar por estación | `night_purge` · `night_insulate` |
| 6a | **Free-cooling** | `cool` + noche + `t_out ≤ t_in − freecool_delta` | `freecool_max_open_pct` | `freecool_night` |
| 6b | **Escudo solar** | `cool` + sol directo + (más calor fuera **o** escudo de sol directo) | geométrico o fijo (+ tope) | `summer_solar_geo` · `summer_solar_shield` |
| 6c | **Escudo térmico (calor)** | `cool` + más calor fuera + **sin** sol directo (shield on) | `heat_shield_pct` | `summer_heat_shield` |
| 6d | **Ganancia solar** | `heat` + sol directo | `100` (o tope `heat_max_open_pct`) | `winter_solar_gain` |
| 6e | **Invierno sin sol** | `heat` + sin sol directo | aislar / abrir según Tª | `winter_night_insulate` · `winter_cold_shield` · `winter_mild_open` |
| 7 | **Default** | nada de lo anterior | `100` (abierta) | `default` |

\* *El amanecer **cede** ante la protección de refrigeración (`cool_protect`:
`cool` + más calor fuera + sol directo **o** escudo térmico) y ante el **escudo de
sol directo** con sol en la fachada (`sun_protect`, F19/v0.73.0). Así no abre
contra el sol/calor de la mañana. En calefacción el amanecer siempre da luz.*

> **⚠️ El override manual manda sobre el bloqueo** (decisión de seguridad
> **v0.94.2**). Lo que acabas de hacer con la mano (o por botón externo, o por una
> automatización, con "Seguir movimientos manuales") gana a **todo**, incluida la
> **Posición de bloqueo** — antes el Lock re-cerraba en ≤60 s una persiana abierta
> a mano, un desenlace de atrapamiento. Al **expirar el hold** (duración
> configurable, **def. 240 min** / `override_hours` 4 h; `0` = sin caducidad) o al
> pulsar **"Reanudar automático"**, el bloqueo (si está armado) **re-impone** su
> posición. Además, el hold manual **sobrevive a reinicios** de Home Assistant: se
> restaura del sensor **"Modo de control"** (`held_position` / `hold_until_ts`) si
> no había caducado, de modo que una actualización de HA con la persiana abierta a
> mano no devuelve el control a la automatización.

---

## 2. Glosario de reason codes

Útil para leer el sensor **Motivo** (`reason`) de cada persiana sin confundir
ramas parecidas:

| `reason` | Significado |
|----------|-------------|
| `manual_hold` | **Override manual** (mano / botón externo / automatización). Manda sobre **todo**, incluido el bloqueo (v0.94.2). Sobrevive a reinicios. El override se arma con la **posición asentada**; mientras un movimiento externo está **en curso** (`opening`/`closing` que DH no inició), el automático **no comanda** la persiana (v0.99.3) — así un tick a mitad de recorrido no invierte la orden del botón de pared. |
| `ov_lock` / `ov_hold` / `ov_ttl` | Bloqueo / override de posición (fijo / temporal / con TTL). La integración solo arma `ov_lock`; `ov_hold`/`ov_ttl` son de motor (paridad YAML). |
| `meteo_alert` | Protección anticipatoria por alerta (viento/granizo/tormenta) (F17). |
| `meteo_rain` | Cerrada por lluvia. |
| `presence_sim` | **Simulación de presencia** (anti-okupa) en modo Away: imita a un ocupante (día abre, noche cierra, con jitter). |
| `mode_sleep` | Cerrada por **Sleep** en el ámbito de la zona (`sleep_pct`). |
| `privacy_time` | Posición de privacidad por horario. |
| `dawn_ramp` | Apertura gradual del amanecer (F19). |
| `night_purge` | **Purga nocturna (F16)** — abre en noche fresca para ventilar la masa térmica (con latch de histéresis). |
| `night_insulate` | **Aislamiento nocturno (F16)** — el **switch opt-in** cierra en la noche para aislar/proteger. |
| `freecool_night` | Purga nocturna: abre para refrescar con aire exterior más fresco. |
| `summer_solar_shield` | Escudo solar **fijo** (refrigerando + sol + calor). |
| `summer_solar_geo` | Escudo solar **geométrico** (F15): cierra lo justo por penetración real del sol. |
| `summer_heat_shield` | **Escudo térmico** refrigerando: tope de apertura por calor (con o sin sol). |
| `winter_solar_gain` | Ganancia solar: abre para captar sol en calefacción. |
| `winter_night_insulate` | **Aislamiento built-in** de calefacción sin sol (siempre, con F16 apagado). |
| `winter_cold_shield` | Día de invierno sin sol y **más frío fuera** → cierra para aislar. |
| `winter_mild_open` | Día de invierno sin sol pero **templado fuera** → abre para dar luz. |
| `default` | Sin criterio térmico → abierta. |
| `meteo_wind_cap` | Cap por viento (tras la cascada). |
| `sdhb_quiet` | Congelada por petición de "silencio" del bus. |
| `sdhb_solar_shield` | Clamp por petición de escudo solar del bus (p. ej. desde DC). |
| `peak_stagger` | Arranque del motor diferido por el anti-pico (F03). |

> **`night_insulate` vs `winter_night_insulate` no son lo mismo:** el primero es
> la feature **F16** (switch *Aislamiento nocturno*, gestiona la noche cuando lo
> activas); el segundo es la rama **built-in** de calefacción sin sol (aísla
> aunque F16 esté apagado). Por eso conviven en el código y en los docs.

---

## 3. Escudo térmico — topes por estación (opt-in)

El switch **Thermal shield** es el mando de **prioridad térmica**. Cuando está
**ON**, aplica un **tope de apertura por estación**:

| Estación | Condición | Tope | Efecto |
|----------|-----------|------|--------|
| **Refrigerando** | `cool` + `t_out ≥ t_in + hot_delta` | `heat_shield_pct` (*Apertura máx. refrigerando*, def. **0**) | No abre más de ese %, **con o sin sol**; `0` = cerrada del todo (reserva el frío). El escudo geométrico solo puede **cerrar más** (deslumbramiento), nunca abrir por encima. |
| **Calentando** | `heat` + sol directo | `heat_max_open_pct` (*Apertura máx. calentando*, def. **100**) | Capta ganancia hasta ese tope; bájalo para limitar deslumbramiento/sobre-ganancia. |
| **Calentando** | `heat` + día sin sol | — | Cierra para aislar **solo si** `t_out < t_in − cold_delta`; si templa, abre (`winter_mild_open`). |

**OFF** = comportamiento previo: el escudo geométrico/solar deja algo de luz
(`summer_min_open_pct`) y la ganancia es plena.

**Histéresis térmica (anti-flapping).** Los umbrales `hot_delta` ("más calor
fuera") y `cold_delta` ("genuinamente más frío fuera") llevan una **banda de
salida** `temp_hyst_c` (def. **0,3 °C**): la condición **entra** al llegar al
umbral y **sale** en `umbral − temp_hyst_c` (calor) / `umbral + temp_hyst_c`
(frío), manteniéndose latcheada en medio. Así la persiana no alterna
abrir/cerrar mientras la temperatura ronda el umbral toda la tarde. La **purga
nocturna F16** tiene su propio **latch**: abre si fuera está genuinamente más
fresco, cierra si está más cálido y **mantiene** en la zona intermedia.

---

## 4. Impacto solar y sombreado geométrico

**`impact` (0..100)** — cuánto sol directo recibe la fachada, según orientación y
sombra del voladizo/alero:
```
diff      = ((sun_az − facade_az + 540) % 360) − 180
in_front  = |diff| ≤ facade_span / 2
si sun_el ≤ 0:  exposed = 0
si no:          shadow  = max(0, overhang_cm·tan(el) − overhang_offset_cm)
                shaded  = clamp(shadow / window_height_cm, 0..1)
                exposed = 1 − shaded
impact = (in_front y sun_effective) ? exposed·100 : 0     # cuantizado a 10%
```

**Sombreado geométrico (F15, opt-in)** — en vez del escudo fijo, calcula la
posición que mantiene la **penetración de sol directo** en el suelo por debajo de
`target_penetration_m`, con la geometría real (alto de ventana, voladizo +
**separación del alero** `overhang_offset_cm`, alféizar, profundidad de sala),
cuantizada a `shade_step_pct` y con suelo `summer_min_open_pct`.

---

## 5. Topes / caps posteriores

Tras la cascada, en orden. **Ninguno pisa una razón `PROTECTED`** — el set es
`{ov_lock, ov_hold, ov_ttl, manual_hold, meteo_rain, meteo_wind_cap,
meteo_alert, privacy_time}` (incluye ya `manual_hold`, v0.94.2): topes de
viento/SDHB/velocidad y el anti-pico respetan **todas** ellas (manual, bloqueo,
alerta, lluvia, privacidad), no solo la lluvia. Recortar una decisión firme
—p. ej. cerrar una persiana abierta a mano— era un camino de atrapamiento.

1. **Cap de viento** (histéresis `wind_limit` / `wind_limit − hyst`): si activo y
   `pos > cap` y la razón **no** está en `PROTECTED`, `pos = cap` (rampa de
   `limit` a `limit+span` bajando hasta `weather_max_open_pct`). Respeta **todas**
   las razones protegidas (no solo `meteo_rain`). Actúa **dentro de su banda de
   histéresis**: mientras el flag está latcheado el cap nunca es un no-op 100
   —dentro de la banda de salida se queda en su primer paso (90)—, para no
   alternar 100↔90 con el viento rondando el límite. Si el **anemómetro se cae**,
   mantiene la última lectura válida **~10 min** (TTL `_WIND_TTL_S = 600 s`) antes
   de soltar la protección. → `meteo_wind_cap`.
2. **SDHB quiet** (`request_quiet` + respeto on): congela en la posición actual
   (no mueve). No pisa razones protegidas ni re-etiqueta sin posición que
   congelar. → `sdhb_quiet`.
3. **SDHB solar_shield** (`request_solar_shield`, p. ej. desde DC):
   `pos = min(pos, sdhb_solar_shield_max_open_pct)`. No pisa `PROTECTED`. →
   `sdhb_solar_shield`.
4. **Slew rate / Movimiento progresivo**: limita el cambio a `slew_step_pct` por
   ciclo desde la posición actual (anti-flapping). No aplica a razones protegidas.
5. **Anti-pico de motores (F03, opt-in)**: el `PeakLoadHub` espacia los arranques
   simultáneos (`peak_stagger_s`); puede diferir un movimiento. **Respeta
   `PROTECTED`**: nunca difiere ni revierte un movimiento protegido (era el
   **tercer camino** de atrapamiento —retener a mitad de recorrido una persiana
   abierta a mano, o diferir un cierre por granizo/lluvia—, corregido en
   v0.94.2). → `peak_stagger`.

**Viento del proveedor (v0.97.1).** Sin sensor de viento local —o con él caído
pasada su ventana de retención de 10 min— el tope de viento usa lo que publica
**Dynamic Weather** (`DATA_WEATHER.values`): la **ráfaga** (`gust`) y, como
respaldo cuando no hay ráfaga, el **viento medio** (`wind`) del proveedor. El cap
reacciona al **peor** valor entre el viento (local o medio) y la ráfaga
(`effective_wind = max(...)`), de modo que el tope proporcional funciona con el
proveedor solo, no únicamente cuando hay ráfaga.

---

## 6. Coordinación por bus (SDHB)

Cada persiana escucha en `ds` (broadcast) y en **su fachada** `ds_f<azimut>`
(p. ej. `ds_f180`). DC dirige intents a una fachada concreta o a todas:
- `request_solar_shield` (refrigerando) → la persiana clampa (`sdhb_solar_shield`).
- `request_quiet` → congela la posición (`sdhb_quiet`).
- Sin `climate` enlazado, la persiana sigue el **changeover de casa** (F37) para
  decidir escudo solar (verano) vs ganancia (invierno).

---

## 7. Sensores que expone

| Entidad | Qué muestra |
|---------|-------------|
| `cover` gestionada | posición **real** (sigue al hardware) + atributos `target_position`, `reason`, `facade`, detalles. |
| **Posición** (`%`) | la posición real, graficable. |
| **Posición objetivo** (`%`) | lo que la cascada **quiere** (clave en *Observe only*). |
| **Motivo** (`reason`) | la rama ganadora (ver glosario). |
| **Energía** (kWh) | estimación por movimiento (F06). |
| **Estado** | salud del módulo (OK / Problema). |

---

## 8. Común e interruptores globales (v0.98.0)

Hay un dispositivo **auto-creado** "**Dynamic Shutter · Común**" (módulo interno
singleton `shutter_common`, sin paso de UI): se **crea solo con la primera
persiana** y se **elimina con la última** — no hay que añadirlo. Los `entity_id`
de sus sensores no cambian (misma `unique_id`), así que no rompe dashboards.

Agrupa:

- **Recuentos de la casa**: **Persianas abiertas / cerradas / entreabiertas**
  (solo las gestionadas por DS, por posición: 100 = abierta, 0 = cerrada,
  intermedio = entreabierta; atributo `total`).
- **Sol compartido**: **Amanecer**, **Anochecer**, **Azimut**, **Elevación** y
  **Día o noche** (leídos de `sun.sun`, una sola vez para toda la casa).

E incluye **interruptores globales** (mandos "a lo bruto") que activan/desactivan
una función en **TODAS** las persianas a la vez:

| Interruptor global | Atributo por persiana |
|--------------------|-----------------------|
| **Solo observar (todas)** | `observe_enabled` (manual/auto global) |
| **Protección meteo** | `weather_protect` |
| **Escudo térmico** | `heat_shield_enabled` |
| **Escudo de sol directo** | `sun_shield_enabled` |
| **Aislamiento nocturno** | `night_iso_enabled` |
| **Amanecer gradual** | `dawn_enabled` |
| **Sombreado geométrico** | `geo_shade_enabled` |
| **Limitación de pico** | `peak_enabled` |

Más un botón **"Reanudar automático (todas)"** (`GlobalResumeAutoButton`) que
cancela el override manual en todas.

**Semántica "a lo bruto".** Cada global es un **mando maestro sin memoria**: al
apagarlo se apaga esa función en **todas**, al encenderlo se enciende en **todas**
— **no recuerda** la mezcla individual previa. Una entidad **"Aviso"** en la
pantalla común lo explica con ejemplo (si el Escudo térmico está ON en 4 persianas
y OFF en otras 4, apagar y volver a encender el global lo deja ON en las 8).

Los ajustes **muy por-persiana** (privacidad, bloqueo, excluir de simulación,
"Seguir movimientos manuales") **siguen solo en cada persiana**, no en el común.

---

## 9. Implementación

| Lógica | Dónde |
|--------|-------|
| Decisión pura (cascada + caps) | `ds_engine.decide_cover()` (testeable) |
| Geometría sol/fachada + penetración | `ds_engine.solar_impact()` / `solar_penetration_m()` / `geo_shade_pos()` |
| Viento efectivo (peor de medio/ráfaga) | `ds_engine.effective_wind()` / `compute_wind_cap()` / `update_wind_cap_active()` |
| Estado, sensores, bus, hardware | `DsCoordinator` sobre el `SdhbHub` |
| Común (recuentos + sol + globales) | `coordinator_shutter_common` (singleton auto-creado) |
| Conducir la persiana | entidad `cover` gestionada |
