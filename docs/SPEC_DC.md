# SPEC — Dynamic Climate (DC) · port a integración HA

> Destilación del pipeline de DC (clima) desde los packages YAML (`DC_v4_2/`).
> Una zona = una entidad `climate`. DC es el **cerebro**: publica intenciones al
> bus que DS/DV consumen.

---

## 1. Qué hace DC

Calcula la **consigna objetivo** (target, °C) de una zona y decide el modo
(heat/cool/off), y **publica al bus** para coordinar persianas/ventilación.

## 2. Pipeline del target

```
target_final = quantize( clamp( base + clamp(Σ biases, ±lim) + sdhb_bias,
                                [min, max] ),
                          step )
```

- **base** (`base_active`): consigna base según modo y día/noche
  (noche = elevación solar ≤ −3°; en calor baja `delta_night`, en frío sube).
  Variantes de vacaciones.
- **Σ biases**: suma de correcciones en °C, **limitada** a `±max_mods` (0.8 def):
  - `bias_exterior` — compensación por temperatura exterior. ✅
  - `bias_vmc` — compensación por la VMC (velocidad + delta T). ✅
  - `trend` (tendencia) — anticipa por la deriva de T interior (°C/h). ✅
  - `brake` (freno) — frena el overshoot cuando la tendencia ya ayuda al modo. ✅
  - `forecast` — anticipa por la previsión (cableado a un `weather` opcional vía
    `weather.get_forecasts`; extremo en la ventana de N horas). ✅
  - `fachadas` — ganancia solar por fachada: la apertura de las persianas
    soleadas modula la demanda (el sol entrando alivia calefacción/refrigeración). ✅
- **sdhb_bias**: corrección por consumir una intención dirigida a DC
  (`solar_gain` en calor → −0.5; `solar_shield` en frío → +0.5).
- **clamp** a `[min, max]` (heat/cool, variantes vacaciones).
- **quantize** a `step` (0.5 °C).

### bias_exterior (compensación por temperatura exterior)
```
heat:  t_ext ≤ u_frio        → +strong
       t_ext ≤ u_frio + 5    → +mild
cool:  t_ext ≥ u_calor       → +strong
       t_ext ≥ u_calor − 5   → +mild
```

## 3. Decisión de modo (rama)

Precedencia: **override** → **dew_risk** (rocío real, Magnus; OFF) → **window_lockout** (OFF) →
**heat/cool** (según demanda) → **off**. Override fija el target manual.

## 4. Publicación al bus (lo que hace de DC el cerebro)

Según el modo activo, DC publica a su `target` de persianas (`ds` por defecto):

| Modo DC | Intención publicada | Efecto en DS |
|---|---|---|
| `heat` | `request_solar_gain` | abrir para ganar sol |
| `cool` | `request_solar_shield` | cerrar para bloquear sol |
| `off`  | *(clear)* | sin intención |

DV también respeta intenciones del bus (`request_quiet`, etc.). Así un solo
`DcCoordinator` coordina los tres módulos.

### 4.1 Targeting solar dinámico

En vez de un target fijo, DC calcula con `sunlit_facades(sun_az, sun_el,
facades)` qué fachadas ilumina el sol (sol sobre el horizonte y dentro del span
de la fachada) y publica la intención **solo a esas fachadas**. Cada persiana
registra su fachada (`ds_fXXX`) en `hass.data`. Al moverse el sol, DC reconcilia
los slots del bus: limpia las fachadas que dejan de estar soleadas (se reabren)
y publica en las nuevas. Sin datos de sol/fachadas, hace fallback al target
configurado.

Cada persiana aporta su **ángulo de aceptación** (`facade_span_deg`): el sol
ilumina la fachada solo si está dentro de `span/2` de su orientación. Una
fachada estrecha (p.ej. 60°) solo reacciona cuando el sol está casi de frente;
una amplia (180°) durante medio día.

## 5. Implementación

| Hoy (YAML) | Integración |
|---|---|
| `dc_zoneXX_target_final` (cascada de sensores) | `dc_engine.assemble_target()` + `decide()` |
| `bias_exterior_raw`, `base_activa` | funciones puras del engine |
| `dc_zoneXX_sdhb_export_*` (publish) | `DcCoordinator` → `SdhbHub.publish()` |
| ~344 helpers `input_*` por zona | config entry + estado del coordinator |
| termostato virtual | entidad `climate` gestionada |

## 5.1 Actuación

Si se configura un termostato real (`dc_climate`), la entidad `climate`
gestionada lo conduce: aplica el modo (heat/cool/off) y la consigna calculada
vía `climate.set_hvac_mode` / `climate.set_temperature`, solo cuando cambian (sin
re-emitir cada ciclo). Sin termostato configurado, DC es *advisory* (solo publica
al bus y muestra la consigna). El modo de la zona se restaura tras reiniciar HA
(`RestoreEntity`).

## 6. Estado / pendiente

- ✅ Pipeline base + bias_exterior + límites + clamp + quantize (con tests).
- ✅ Publicación al bus (heat→gain / cool→shield) y consumo (self-bias).
- ✅ **Triángulo completo** verificado en HA: DC(cool) → bus → DS clampa.
- ⏳ Biases restantes (fachadas/forecast/tendencia/lead) con sus fórmulas,
  dew-risk a partir de punto de rocío real, ventana/override por UI,
  y multi-zona (`zone02..zone08`).
