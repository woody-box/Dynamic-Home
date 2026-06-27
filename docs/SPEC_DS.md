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
| 1 | **Override** | `lock` / `hold` / `ttl` activos | `override_pos` | `ov_lock` · `ov_hold` · `ov_ttl` |
| 2 | **Alerta meteo** (F17) | binary_sensor de alerta activo | la más protectora | `meteo_alert` |
| 3 | **Lluvia** | `weather_protect` + lloviendo | `rain_close_pct` | `meteo_rain` |
| 4 | **Privacidad** | dentro de la ventana horaria | `privacy_pos_pct` | `privacy_time` |
| 5 | **Amanecer gradual** (F19) | rampa activa **y** sin protección de frío* | paso de apertura | `dawn_ramp` |
| 6 | **Aislamiento nocturno** (F16, opt-in) | switch on + sol bajo horizonte | abrir/cerrar por estación | `night_insulate` |
| 7a | **Free-cooling** | `cool` + noche + `t_out ≤ t_in − freecool_delta` | `freecool_max_open_pct` | `freecool_night` |
| 7b | **Escudo solar** | `cool` + sol directo + `t_out ≥ t_in + hot_delta` | geométrico o fijo (+ tope) | `summer_solar_geo` · `summer_solar_shield` |
| 7c | **Escudo térmico (calor)** | `cool` + más calor fuera + **sin** sol directo (shield on) | `heat_shield_pct` | `summer_heat_shield` |
| 7d | **Ganancia solar** | `heat` + sol directo | `100` (o tope `heat_max_open_pct`) | `winter_solar_gain` |
| 7e | **Invierno sin sol** | `heat` + sin sol directo | aislar / abrir según Tª | `winter_night_insulate` · `winter_cold_shield` · `winter_mild_open` |
| 8 | **Default** | nada de lo anterior | `100` (abierta) | `default` |

\* *El amanecer **cede** ante la protección de refrigeración (`cool_protect`):
`cool` + más calor fuera + (sol directo **o** escudo térmico activo). Así no abre
contra el sol/calor de la mañana. En calefacción el amanecer siempre da luz.*

---

## 2. Glosario de reason codes

Útil para leer el sensor **Motivo** (`reason`) de cada persiana sin confundir
ramas parecidas:

| `reason` | Significado |
|----------|-------------|
| `ov_lock` / `ov_hold` / `ov_ttl` | Override manual (fijo / temporal / con TTL). |
| `meteo_alert` | Protección anticipatoria por alerta (viento/granizo/tormenta) (F17). |
| `meteo_rain` | Cerrada por lluvia. |
| `privacy_time` | Posición de privacidad por horario. |
| `dawn_ramp` | Apertura gradual del amanecer (F19). |
| `night_insulate` | **Aislamiento nocturno (F16)** — el **switch opt-in** manda en la noche. |
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

Tras la cascada, en orden:

1. **Cap de viento** (histéresis `wind_limit` / `wind_limit − hyst`): si activo y
   `pos > cap`, `pos = cap` (rampa de `limit` a `limit+span` bajando hasta
   `weather_max_open_pct`). No pisa `meteo_rain`. → `meteo_wind_cap`.
2. **SDHB quiet** (`request_quiet` + respeto on): congela en la posición actual
   (no mueve). No pisa razones protegidas. → `sdhb_quiet`.
3. **SDHB solar_shield** (`request_solar_shield`, p. ej. desde DC):
   `pos = min(pos, sdhb_solar_shield_max_open_pct)`. → `sdhb_solar_shield`.
4. **Slew rate / Movimiento progresivo**: limita el cambio a `slew_step_pct` por
   ciclo desde la posición actual (anti-flapping). No aplica a razones protegidas
   (`ov_*`, `meteo_rain`, `meteo_wind_cap`, `meteo_alert`, `privacy_time`).
5. **Anti-pico de motores (F03, opt-in)**: el `PeakLoadHub` espacia los arranques
   simultáneos (`peak_stagger_s`); puede diferir un movimiento. → `peak_stagger`.

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

## 8. Implementación

| Lógica | Dónde |
|--------|-------|
| Decisión pura (cascada + caps) | `ds_engine.decide_cover()` (testeable) |
| Geometría sol/fachada + penetración | `ds_engine.solar_impact()` / `solar_penetration_m()` / `geo_shade_pos()` |
| Estado, sensores, bus, hardware | `DsCoordinator` sobre el `SdhbHub` |
| Conducir la persiana | entidad `cover` gestionada |
