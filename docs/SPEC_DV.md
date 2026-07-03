# SPEC — Dynamic Ventilation (DV) · port a integración HA

> Destilación del algoritmo DV tal y como está implementado hoy en los packages
> YAML (`DV_v4_2/`), para servir de **especificación única** del port a una
> integración (`custom_components/dynamic_home`). Este documento es la fuente de
> verdad: el código Python debe comportarse igual que el YAML descrito aquí.
>
> Alcance de esta primera entrega: **un VMC de doble flujo** (la instancia
> `dv_vmc`). Multi-VMC (`dv_2`, `dv_3`) queda como extensión futura.

---

## 1. Qué hace DV

Controla la velocidad de una VMC de doble flujo (3 velocidades físicas: **V1/V2/V3**)
en función de la **calidad de aire interior** (CO₂ y PM2.5), con una serie de
capas que pueden forzar o capar la velocidad por encima de esa decisión base.

El resultado de cada ciclo es una **velocidad lógica** `0..3`:
- `0` = apagado (fuera de horario **sin** aire crítico/boost/manual, o cap hostil extremo)
- `1/2/3` = V1/V2/V3

El estado seguro de una vivienda **no es apagar**: el lockout por sensores
intermitentes deja la VMC en **V1**, no en `0` (ver §6).

Esa velocidad se traduce a **3 relés** físicos (`sw_pwr`, `sw_v2`, `sw_v3`).

---

## 2. Mapa de hardware (HAL)

Hoy es el sensor `dv_vmc_hw_map` con placeholders `REPLACE_*`. En la integración
pasa a ser la **configuración del config entry** (asistente UI). Claves:

| Clave | Tipo | Obligatorio | Uso |
|-------|------|:-:|-----|
| `sw_pwr` | switch | ✅ | Encendido general |
| `sw_v2` | switch | ✅ | Relé velocidad 2 |
| `sw_v3` | switch | ✅ | Relé velocidad 3 (V1 = v2 y v3 a OFF) |
| `co2` | sensor (ppm) | ✅ | IAQ CO₂ |
| `pm25` | sensor (µg/m³) | ✅ | IAQ PM2.5 |
| `t_in` | sensor (°C) | ⬜ | Free-cooling (temp interior) |
| `t_ext` | sensor (°C) | ⬜ | Free-cooling (temp exterior) |
| `outdoor_aqi_entity` | sensor (AQI) | ⬜ | Cap "hostile outside" |
| `dp_casa` / `dp_exterior` | sensor | ⬜ | Dry mode (punto de rocío) |
| `pwr_power` / `pwr_energy` | sensor | ⬜ | Telemetría/consumo |

**Validación de rango (safe sensors):** CO₂ válido en `[0, 5000]`, PM2.5 en
`[0, 500]`. Fuera de rango o no numérico ⇒ valor `None` (se ignora ese ciclo).

---

## 3. Filtrado EMA (suavizado de IAQ)

Para CO₂ y PM2.5, opcional (toggles `*_ema_enabled`). Se recalcula cada **1 min**:

```
ema = x                       si prev <= 0   (bootstrap)
ema = a*x + (1-a)*prev        en otro caso
```

- `x` = lectura "safe" actual; `a` = alpha (`0.05..0.5`, default `0.2`).
- La decisión usa el EMA **solo si** `ema_enabled and ema > 0`; si no, usa el valor crudo.

---

## 4. Decisión de velocidad (pipeline `control_principal`)

Se evalúa al arrancar, cada **5 min**, y ante cambios de IAQ/estado relevantes.
Precedencia de **modos** (de mayor a menor; el primero que aplica, gana):

1. **No permitida** (gate de horario/failsafe). Fin. Dos desenlaces:
   - Si es **lockout** de failsafe ⇒ velocidad `1` (V1), motivo `lockout`.
   - Si no ⇒ `sw_pwr` OFF, velocidad `0`, motivo `not_permitted`.

   `permitida = modo_auto AND (NOT failsafe_lockout) AND (en_horario OR permiso_extra)`

   **Escape de seguridad del horario (v0.94.2)** — la ventana de horario ya
   **no** puede asfixiar la casa: fuera de la ventana (o en el tramo `0` del
   programador semanal) el `permiso_extra` deja pasar de todos modos el **aire
   crítico**, el **Boost** y el **override manual**. En el motor:
   ```
   critical_air = co2 >= quiet_critical_co2 OR pm >= quiet_critical_pm
   permiso_extra = permiso_extra_in OR critical_air OR boost_active OR manual_override
   ```
   (`quiet_critical_co2 ≈ 1500 ppm`, `quiet_critical_pm ≈ 50 µg/m³`.) `co2`/`pm`
   son los valores efectivos ya suavizados (EMA si procede).
2. **Override manual** (timer activo) ⇒ `3` si `override_v3` else `2`.
3. **Boost (F14)** (timer activo) ⇒ `3`, pero pasa por el **cap hostil** (ni el
   boost aspira humo a plena potencia; ver §4.2.4).
4. **Dry mode** (`(dry_mode AND dew_risk) OR dry_requested`, y `dp_diff != None`)
   ⇒ secado escalonado con histéresis (v0.97.0): engancha con `dp_diff > dry_margin`
   y suelta con `dp_diff <= dry_margin - dry_hys`. Con el latch activo:
   `3` si `dp_diff >= dry_v3_delta`; `2` si `>= dry_v2_delta`; si no `1`.
   El resultado pasa por los caps **hostil**, **horas de silencio** y **house-mode**
   con **piso V1** (una petición de secado por moho se ralentiza, nunca se silencia).
   *(Si `dp_diff` es None ⇒ no engancha: se cae al camino Auto/IAQ.)*
5. **Override ducha** (`shower_rh`, derivado de ΔRH) ⇒ velocidad `shower_level`.
6. **Auto (IAQ)** ⇒ ver §4.1.

### 4.1 Cálculo base por histéresis (solo modo Auto)

Selección de la fuente: `co2 = co2_ema si procede, si no co2_raw` (idem `pm`).

Ajuste de histéresis anti-rebote: si hubo override hace `< 300 s` **y** `v_actual == 3`,
la histéresis se reduce a la mitad (`hys *= 0.5`).

Máquina de estados (con histéresis para **bajar**, nunca para subir):

```
need3 = co2 >= co2_v3  OR  pm >= pm_v3
if need3: target = 3
elif v_actual == 3:
    can_drop = (co2 < co2_v3 - hys) AND (pm < pm_v3 - hys)
    if can_drop:  target = 2 si (co2>=co2_v2 OR pm>=pm_v2) else 1
    else:         target = 3
else:
    need2 = co2 >= co2_v2 OR pm >= pm_v2
    if need2: target = 2
    elif v_actual == 2:
        can_drop2 = (co2 < co2_v2 - hys) AND (pm < pm_v2 - hys)
        target = 1 si can_drop2 else 2
    else: target = 1
```

Umbrales por defecto: `co2_v2≈900`, `co2_v3≈1300`, `pm_v2≈15`, `pm_v3≈40`,
`co2_hys≈100`, `pm_hys≈5`. Con `adaptive_enabled` estos umbrales se sustituyen por
los aprendidos (percentiles p90/p95 del histórico), **acotados a ±30 %** de los
fijos y maduros solo con **~1 día** de muestras (ver §7).

### 4.2 Modificadores sobre el `target` base (en orden)

Aplicados solo en Auto, sin overrides manuales/ducha. El cap hostil (AQI) ya **no**
es un cap intermedio: se ha movido al **final** (paso 6) como última autoridad.

0. **Base del programador semanal**: si el tramo activo `schedule_speed > 0`, actúa
   como suelo (`target = max(target, schedule_speed)`).
0'. **Anticipación (F11)**: una subida brusca de CO₂/PM (pendiente EMA) sube a
   `anticip_level` antes de cruzar el umbral absoluto (nunca baja).
1. **Free-cooling (v0.95.0)**: si `freecool_active` ⇒ `target = max(target, 2)`.
   Ahora tiene **switch propio** (`freecool_enabled`, **ON por defecto**) — antes la
   mera presencia de sondas lo forzaba y no se podía apagar — y un umbral nuevo de
   **temperatura interior mínima** (`freecool_t_in_min`, def. **24 °C**): solo se
   engancha con el interior genuinamente caluroso, no con un día templado de invierno
   (19–21 °C dentro) donde ventilaría el calor que estás pagando.
   `freecool_active` (con histéresis propia, y suprimido en temporada de calefacción):
   ```
   si NOT freecool_enabled OR t_in None OR t_ext None: False
   si heating_season: False
   si t_in < (t_in_min - 0.5·activo_prev): False    # banda de salida
   si t_ext < t_ext_min: False
   si activo previamente: delta(t_in - t_ext) >= delta_off
   si no:                 delta(t_in - t_ext) >= delta_on
   ```
2. **SDHB (intent del bus)** — se evalúa **después** de free-cooling y puede forzar/capar:
   - `request_quiet` / `request_eco` / `request_weather_protect` ⇒ `target = 1`,
     **salvo aire crítico** (v0.95.0): una petición de silencio del bus ya **no**
     silencia si `critical_air` (la salud gana al deseo de silencio de otro módulo).
   - `request_boost` ⇒ `target = 3`
   - `request_freecool` ⇒ `max(target, 2)`
   - `request_normal` ⇒ no-op (deja pasar la decisión IAQ)
3. **Anti-flapping (`allow_raise`)**: subir de velocidad solo se permite si el ciclo
   viene de un cambio de IAQ, o de `request_boost`/`request_freecool`, o de
   `freecool_active`/`dew_risk`/`dry_mode`/anticipación. En otro caso, si
   `target > v_actual` ⇒ se mantiene `max(v_actual, schedule_speed)` (el suelo del
   programador nunca se pisa).
4. **Horas de silencio (F12)**: dentro de la ventana nocturna, `target = min(target,
   quiet_max_level)`, **salvo aire crítico**. En **noches de verano** el free-cool
   está **exento** de este cap hasta un tope configurable (`freecool_quiet_cap`,
   def. **V2**): el suelo sube a ese tope (poner 1 restaura el silencio absoluto).
   Un cap a `0` con demanda IAQ real deja piso **V1** (evita un bang-bang `0↔V3`).
5. **House mode (F01)**: `mode_boost` ⇒ `3`; si no, `mode_cap` capa el auto salvo
   aire crítico (y con la misma exención del free-cool de verano).
6. **Hostile outside (AQI exterior) — ÚLTIMA autoridad (v0.95.0)**: se aplica al
   **final**, después de Boost/`mode_boost`, para que nada pueda re-subir por encima
   (ni el Boost puede aspirar humo a plena potencia). Por tramos:
   - `aqi >= t3` ⇒ `0` (OFF), o piso **V1** si `critical_air` (mejor V1 con CO₂
     subiendo que nada).
   - `aqi >= t2` ⇒ `min(target, 1)`
   - `aqi >= t1` ⇒ `min(target, 2)`

El `stage_winner` (trazabilidad) refleja qué capa decidió: `hostile_off`,
`hostile_cap_v1/v2`, `sdhb_quiet/boost/freecool`, `freecool`, `anticipatory`,
`schedule_base`, `quiet_cap`, `mode_cap/mode_boost`, `hold_antiflap`, `iaq`/`iaq_ok`.

---

## 5. Driver físico (velocidad lógica → relés)

```
V1: sw_v2 OFF, sw_v3 OFF
V2: sw_v2 ON,  sw_v3 OFF
V3: sw_v3 ON,  sw_v2 OFF
0 : sw_pwr OFF
```

Reglas: nunca V2 y V3 a la vez (watchdog). En el primer arranque (`bootstrap`)
se hace un pulso de `sw_v2` (~800 ms) para "despertar" el motor. Flag
`driver_busy` evita solapes; si sigue ocupado > 10 s el ciclo se aborta.

---

## 6. Failsafe / guardrails

- **Sensores vitales KO** (CO₂/PM2.5 inválido, o sin datos frescos > 120 s): se
  bloquea Auto y se fuerza **V1**; alerta.
- **Trip counter**: N fallos en ventana H ⇒ `failsafe_lockout` durante M min
  (defaults: `limit=3`, `window=2h`, `lockout=30min`).
- **Estado seguro del lockout = V1, no OFF (v0.96.0)**: mientras el lockout está
  activo la VMC se deja en **V1** (motivo `lockout`), nunca apagada — el estado
  seguro de una vivienda es ventilación base, no cortar el aire. Solo el `0` de
  "fuera de horario sin escape" (`not_permitted`) apaga.
- **Antigüedad del dato = `last_reported`, no `last_updated` (v0.96.0)**: la
  frescura se mide con `last_reported` (avanza aunque el sensor reenvíe el **mismo**
  valor). `last_updated` solo se mueve en un **cambio**, así que una lectura plana de
  CO₂ en una noche tranquila parecía "rancia" y disparaba **falsos lockouts**.
- **Suelo de cordura de CO₂** (`co2_sanity_floor ≈ 250 ppm`): una lectura por debajo
  es físicamente imposible (basal atmosférica ~410 ppm) ⇒ se trata como fallo de
  sensor (ruta al KO vital, no envenena el EMA). El PM **no** tiene suelo (~0 es real).
- **Startup grace** (`120 s`): ventana de arranque en la que no se considera KO el
  contrato de hardware (evita falsos negativos mientras resuelven entidades).

---

## 7. Estado de las extensiones

**Implementado en `engine.py` (con tests):**
- ✅ Programación semanal por día (`in_schedule`, con wrap nocturno) → gate `permitida`.
- ✅ `permitida = auto AND (NOT lockout) AND (en_horario OR permiso_extra)`.
- ✅ Failsafe: sensores vitales KO (stale/invalid) → fuerza V1; trip-counter en
  ventana → `lockout` durante M min; `startup_grace` suprime falsos KO al arrancar.
- ✅ Boost por ducha vía ΔRH (`update_shower`, con histéresis on/off + hold).
- ✅ Umbrales adaptativos (v0.97.0): el coordinator mantiene el histórico y calcula
  p90/p95; el engine los usa cuando `adaptive_enabled`. **Acotados a ±30 %** de los
  umbrales fijos (una casa mal ventilada no "aprende" complacencia; una limpia, no
  paranoia) y **maduros con ~1 día** de muestras (`adaptive_min_samples = 1440`
  ≈ 1/min, antes ~1,7 h) para que un par de horas raras no fije lo "normal".
- ✅ Secado (`dry`) **escalonado** (v0.97.0): entra en **V2** y solo sube a **V3**
  con el exterior mucho más seco (`dry_v3_delta` def. **2.0** > `dry_margin` **1.0**);
  antes V3 era la única entrada alcanzable. Pasa por los caps de silencio/hostil con
  piso V1 (ver §4, precedencia #4).

**Pendiente (siguiente iteración):**
- Telemetría: utility_meter de horas por velocidad, consumo, aviso de filtros.
- Self-test, backup/restore (innecesario: el config entry persiste solo).
- Multi-VMC (`dv_2`, `dv_3`).

---

## 8. Mapa a entidades de la integración

| Hoy (YAML) | Integración |
|---|---|
| `dv_vmc_hw_map` + `REPLACE_*` | Config entry (config flow UI) |
| ~122 helpers `input_*` | Estado interno del coordinator + un puñado de `number`/`switch` |
| `control_principal` (automation) | `engine.decide()` (Python puro, testeable) |
| relés vía `apply_hardware_speed` | método `_apply_speed()` de la entidad `fan` |
| `sensor.dv_vmc_velocidad_real` | estado de la entidad `fan` |
| `sdhb_intent_matched` + bus YAML | hub SDHB en memoria (coordinator compartido) |
| golden tests YAML | `tests/test_dv_engine.py` (pytest) |
