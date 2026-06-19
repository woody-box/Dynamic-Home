# SPEC — Dynamic Shutter (DS) · port a integración HA

> Destilación del algoritmo DS (persianas) desde los packages YAML (`DS_v4_2/`).
> Una ventana = una entidad `cover`. Comparte el `SdhbHub` con DV/DC.

---

## 1. Qué hace DS

Calcula una **posición objetivo de persiana** `0..100` (% abierta) y un **reason
code** de trazabilidad, mediante una **cascada de prioridades** y unos **caps**
posteriores. La posición se aplica a la `cover` física.

## 2. Cascada de decisión (de mayor a menor prioridad)

El primer caso que aplica fija `pos` y `reason`:

1. **Override** — `lock` (permanente) / `hold` (hasta `hold_until`) / `ttl`
   (hasta `override_until`) ⇒ `pos = override_pos`. reasons `ov_lock/ov_hold/ov_ttl`.
2. **Meteo lluvia** (`weather_protect` + lloviendo) ⇒ `pos = rain_close_pct` (0). `meteo_rain`.
3. **Privacidad horaria** (ventana `from..until`, con wrap de medianoche) ⇒ `pos = privacy_pos_pct`. `privacy_time`.
4. **Free-cooling verano** (`cool` + noche + `t_out ≤ t_in − free_delta` + no sleep) ⇒ `pos = freecool_max_open_pct`. `freecool_night`.
5. **Solar shield verano** (`cool` + `impact>0` + `t_out ≥ t_in + hot_delta`) ⇒
   `pos = max(100 − impact, summer_min)` cuantizado a 10. `summer_solar_shield`.
6. **Ganancia solar invierno** (`heat` + `impact>0`) ⇒ `pos = 100`. `winter_solar_gain`.
7. **Aislamiento nocturno invierno** (`heat` + `impact==0`) ⇒ `pos = winter_night_pct`. `winter_night_insulate`.
8. **Default** ⇒ `pos = 100`.

## 3. Impacto solar (modelo geométrico)

`impact` 0..100 según orientación de fachada y sombra del voladizo:
```
diff = ((sun_az − facade_az + 540) % 360) − 180
in_front = |diff| ≤ facade_span/2
si sun_el ≤ 0:  exposed = 0
si no:          shaded = clamp(overhang·tan(el) / window_height, 0..1); exposed = 1 − shaded
impact = (in_front y sun_effective) ? exposed : 0   → cuantizado a 10%
```

## 4. Caps posteriores (tras la cascada)

1. **Wind cap** (con histéresis `limit` / `limit−hyst`): si activo y `pos > cap`,
   `pos = cap` (rampa de `limit` a `limit+span` bajando hasta `weather_max_open`).
   No pisa `meteo_rain`. reason `meteo_wind_cap`.
2. **SDHB quiet** (`request_quiet` + respeto activado): congela en la posición
   actual (no mueve). reason `sdhb_quiet`. No pisa razones críticas.
3. **SDHB solar_shield** (`request_solar_shield`): `pos = min(pos, shield_max)`. `sdhb_solar_shield`.
4. **Slew rate**: limita el movimiento a `slew_step` por ciclo desde la posición
   actual (anti-flapping). No aplica a razones críticas
   (`ov_*`, `meteo_rain`, `meteo_wind_cap`, `privacy_time`).

## 5. Implementación

| Hoy (YAML) | Integración |
|---|---|
| `ds_wX_target_decision_json` (template gigante) | `ds_engine.decide_cover()` (puro, testeable) |
| `ds_solar_impact_pct` (geometría sol/fachada) | `ds_engine.solar_impact()` |
| ~714 helpers `input_*` por ventana | config entry + estado del coordinator |
| `ds_wX_sdhb_*` (consumo del bus) | `DsCoordinator` sobre el `SdhbHub` compartido |
| aplicar a `cover.xxx` | entidad `cover` gestionada que conduce la real |

## 6. Estado / pendiente

- ✅ Cascada completa + caps + slew + impacto solar (con tests).
- ✅ Consumo del bus compartido (demo cross-módulo: DC→`request_solar_shield`→DS clampa).
- ✅ Multi-instancia con targeting por fachada: cada persiana escucha en `ds`
  (broadcast) y en su fachada `ds_fXXX`; DC dirige intents a una fachada concreta.
- ⏳ Override (lock) y privacidad por UI (switch + number, con RestoreEntity); pendiente hold/ttl con timers y voladizo en el flow;
  detección de lluvia por umbral analógico.
