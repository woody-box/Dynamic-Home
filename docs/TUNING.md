# Guía de ajuste por objetivo — Dynamic Home

> Hay **muchos** parámetros, pero no se tocan sueltos. Esta guía los agrupa por **lo que
> quieres conseguir**: qué mando mover, **hacia dónde**, y **qué vigilar junto** (los que
> van de la mano). Cada parámetro tiene además su **ayuda contextual** debajo del control
> en la UI; aquí está el mapa de **cómo interactúan**.

**Antes de tocar nada:**
1. **Aplica un preset** (opciones del módulo → *Aplicar un preset*) para partir de un punto
   coherente — ver [PROFILES.md](PROFILES.md).
2. Valida en **Observe only** y lee los **reason codes** — ver [QUICKSTART.md](QUICKSTART.md).
3. **Modo básico vs avanzado**: HA oculta los parámetros expertos salvo que actives el
   *Modo avanzado* (Tu perfil → Avanzado). Si eres nuevo, quédate en básico.
4. Si te lías, vuelve a un preset, o usa `export_options`/`import_options` para
   restaurar/clonar.

> **La cascada del target (DC), de arriba a abajo:**
> `base → biases (exterior · VMC · fachada · bus) → anticipación (lead) → freno → límites`.
> Mover algo **arriba** se propaga hacia abajo. Por eso, casi siempre que subes la
> **anticipación**, conviene mirar el **freno**; y los **límites** son la red de seguridad
> final pase lo que pase.

---

## DC · Clima

### "Quiero que **anticipe** / precaliente antes"
- **Sube** `lead_base_h`, `lead_per_degree_h`, `trend_lead_h` *(Tendencia)*. Con suelo
  radiante (inercia alta), esto es lo que más se nota.
- **Mejor aún:** activa el switch **Adaptive lead** y deja que aprenda el horizonte solo.
- **Con tarifa:** `tariff_lead_cheap_mult` ↑ precalienta en valle *(Sesgo de tarifa)*.
- **Vigila junto:** el **freno** (`brake_*`) para no pasarte de consigna, y `lead_max_h`
  (tope superior). Demasiada anticipación sin freno = sobrepasar.

### "Que **no oscile** / no se pase de consigna"
- **Sube** `brake_biases_*` y **baja** `brake_thresholds_*` *(Freno)* → frena antes y más.
- **Sube** `apply_min_delta` y `step` *(Límites)* → menos micro-ajustes del relé.
- **Sube** `trend_deadband_cph` *(Tendencia)* → ignora el ruido de la tendencia.
- **Vigila junto:** si subiste la **anticipación**, sube también el **freno**; van en pareja.

### "Que reaccione al **frío/calor de fuera**"
- `bias_ext_heat_strong/mild`, `bias_ext_cool_strong/mild` y los umbrales
  `ext_cold_threshold` / `ext_hot_threshold` *(Bias exterior)*.
- `insulation_factor`: casa **bien aislada** → **bájalo** (el exterior influye menos).

### "Que aproveche el **sol** o compense la **VMC**"
- `facade_gain_heat/cool` *(Fachada)* — empuje por sol en la fachada.
- `vmc_bias_heat/cool_1..3` *(Compensación VMC)* — compensa la ventilación por velocidad.
- `sdhb_bias_*` *(Bus)* — cuánto te auto-sesga el bus solar.

### "Que **ahorre** con tarifa / en punta"
- `tariff_lead_cheap_mult` ↑ (valle) y `tariff_lead_peak_mult` ↓ (punta); `tariff_bias_c`
  para cargar masa térmica en valle *(Sesgo de tarifa)*.
- **Vigila junto:** el **anti-pico** (abajo) y las **consignas de Vacaciones**.

### "Que **respete el ICP** (no saltar el diferencial)"
- **Modo cuenta:** `peak_max_zones` (cuántas zonas eléctricas a la vez). **Modo potencia:**
  `peak_max_power_w` (presupuesto en W) *(Anti-pico)*.
- `peak_stagger_s` espacia arranques; `peak_comfort_bypass_c` deja que una desviación
  severa **salte** el límite (el confort gana; la seguridad sigue por encima).
- *Solo aplica si tu instalación es eléctrica/individual (perfil F26 `peak`).*

### "Que **proteja el compresor** (anti-ciclado)"
- `anticycle_min_on_s` / `anticycle_min_off_s` / `anticycle_max_starts_per_h` *(Ciclo)*.
- **Mejor:** activa **Adaptive anti-cycle** y deja que los dimensione desde lo aprendido.
- **Vigila junto:** el reparto de prioridad entre zonas **no** vive aquí, vive en el
  **anti-pico** (F03).

### Seguridad y casos especiales
- **Condensación:** `dew_spread_min` *(Condensación)*. **Moho:** `mold_*` *(Moho)*.
- **Ventana abierta:** `window_drop_cph` + tiempos `window_*` *(Ventana)*.
- **Límites (red de seguridad):** `target_min/max_heat/cool`, `max_mods_*` *(Límites)* —
  acoten cuánto puede moverse el target pase lo que pase.

---

## DV · Ventilación

### "Aire **más limpio** / más exigente"
- **Baja** `co2_v2/v3` y `pm_v2/v3` *(Calidad de aire)* → sube de velocidad antes.
- **Vigila junto:** `co2_hys` / `pm_hys` (histéresis) para que **no flapee** al rozar el
  umbral.

### "Más **silencio** de noche"
- **Horas de silencio** (entidades de ventana) + `quiet_max_level`.
- **Pero** `quiet_critical_co2` / `quiet_critical_pm` *(Horas de silencio)*: si el aire se
  pone crítico, **la salud gana** e ignora el cap.
- `freecool_quiet_cap` *(Free-cooling)* — en noches de **verano** el free-cool queda **exento**
  del cap de silencio/Sleep hasta este tope (V2 por def., editable 1..3). Ponlo a **1** para
  recuperar el silencio absoluto de noche.

### "**Free-cooling** / no ventilar el calor que pago"
- `freecool_t_ext_min`, `freecool_delta_on/off` *(Free-cooling)*.
- `freecool_t_in_min` *(Free-cooling)* — **temp. interior mínima** para que arranque el
  free-cool (24 °C por def.): por debajo **no** ventila, para no tirar por la ventana el
  calor que pagas en un día templado. Hay además un **switch "Free-cooling"** (ON por def.)
  para apagarlo del todo.
- **Vigila junto:** **configura el changeover** (entrada de Zonas). Sin él, el free-cooling
  va solo por temperatura y puede ventilar calor en invierno (te saldrá un aviso).

### "**Secar** humedad sin meter aire húmedo"
- `dry_v2/v3_delta`, `dry_margin`, `dew_spread_min` *(Anticondensación)* — solo ventila a
  secar cuando el aire de fuera es **de verdad** más seco.

### "Que **no flapee** los sensores"
- `co2_ema_enabled` / `pm_ema_enabled` + `*_ema_alpha` *(Suavizado)* — mayor alpha = más
  reactivo pero más ruido.

### Otros
- **Ducha:** `shower_*` *(Refuerzo de ducha)*. **Anticipación:** `anticip_*`.
- **Failsafe/arranque:** `stale_threshold_s`, `startup_grace_s`, `trip_*` *(Failsafe)* —
  toca con cuidado; protegen contra sensores muertos y rebotes.

---

## DS · Persianas

### "**Sombra** en verano / que no me deslumbre"
- **Baja** `summer_min_open_pct` *(Posiciones)* → cierra más en el escudo solar.
- `hot_delta` *(Deltas térmicos)* — cuánto más caliente fuera que dentro para activar.
- `temp_hyst_c` *(Deltas térmicos)* — **banda de histéresis** de los escudos térmicos: el
  escudo entra a `hot_delta` y **sale** a `hot_delta − temp_hyst_c` (y simétrico con
  `cold_delta` en invierno). **Súbelo** si la persiana oscila abrir/cerrar todo el mediodía
  con la temperatura rondando el umbral (def. 0,3 °C).
- Para el modelo **geométrico** (opt-in): `window_height_cm`, `overhang_cm`,
  `target_penetration_m`… *(Geometría)*.

### "**Ganancia solar** en invierno / aislar de noche"
- `winter_night_pct`, `night_iso_open/close_pct` *(Posiciones / Noche)*.
- **Vigila junto:** la **temporada** — sin termostato por persiana, DS sigue el
  **changeover** de casa para decidir verano (escudo) vs invierno (ganancia).

### "**Protección** de viento / granizo / lluvia"
- `wind_limit_kmh`, `wind_cap_span_kmh`, `wind_cap_hyst_kmh` *(Viento)*.
- `alert_pct` / `alert_hail_pct` / `alert_wind_pct` / `alert_hold_min` *(Alertas)*.
- `rain_close_pct`, `weather_max_open_pct` *(Posiciones)*.
- *La protección meteo es un cap de seguridad **por encima** de la lógica solar.*
- **Sin sensor de viento local** (o con el local caído pasada su ventana de retención), el
  tope proporcional usa el **viento del proveedor Dynamic Weather** como respaldo (ráfaga si
  la publica, si no el viento medio) — la protección de viento funciona aunque no cablees un
  anemómetro.

### "**Amanecer suave**"
- `dawn_step_pct`, `dawn_step_min`, `dawn_target_pct`, `dawn_trigger_elevation` *(Amanecer)*.

### "Que **no vaya a tirones**"
- `slew_enabled` + `slew_step_pct` *(Slew rate)*.

### "No **clavar el inrush** de varios motores"
- `peak_stagger_s` *(Anti-pico)* — espacia los arranques. Canal **separado** del de clima.

### "Mover un ajuste **a toda la casa** de golpe" (v0.98.0)
- La pantalla **"Dynamic Shutter · Común"** (aparece sola al crear la primera persiana) trae
  **interruptores globales**: activan/desactivan una función en **TODAS** las persianas a la
  vez — **Protección meteo**, **Escudo térmico**, **Escudo de sol directo**, **Aislamiento
  nocturno**, **Amanecer gradual**, **Sombreado geométrico**, **Limitación de pico** y
  **Solo observar (todas)** — más un botón **Reanudar automático (todas)**.
- **Aviso — son "a lo bruto":** cada global **no recuerda** el estado individual de cada
  persiana. Si tenías el Escudo térmico ON en 4 y OFF en otras 4, apagar y volver a encender
  el global lo deja **ON en las 8**. Para ajustes finos por persiana, usa el toggle de cada
  una (privacidad, bloqueo, excluir de simulación, seguir movimientos manuales siguen solo
  por persiana).

---

## Cómo validar un cambio (siempre)

1. **Observe only** + el sensor **Reason** (qué rama decide) y el sensor **target** (la
   cascada en sus atributos: `base`, `mods_total`, `lead_h`, `bias_*`…).
2. Mueve **un grupo** afín a la vez, no mandos sueltos por toda la lista.
3. ¿Algo raro? **Descargar diagnósticos** (Ajustes → el dispositivo → ⋮) da un JSON con
   tus valores + el estado vivo, útil para revisar o pedir ayuda.
4. ¿Te has liado? **Aplicar un preset** vuelve a un punto coherente, o `import_options`
   restaura unos valores guardados.

## Más

- **[QUICKSTART.md](QUICKSTART.md)** · **[PROFILES.md](PROFILES.md)** ·
  **[PRESETS.md](PRESETS.md)** (inventario con *"Qué es"* de cada parámetro) ·
  **[REQUIREMENTS.md](REQUIREMENTS.md)** (el detalle de cada feature).
