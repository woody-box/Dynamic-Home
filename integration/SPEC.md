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
- `0` = apagado (fuera de horario, o cap hostil extremo)
- `1/2/3` = V1/V2/V3

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

1. **No permitida** ⇒ `sw_pwr` OFF, velocidad `0`. Fin.
   `permitida = modo_auto AND (NOT failsafe_lockout) AND (en_horario OR permiso_extra)`
2. **Override manual** (timer activo) ⇒ `3` si `override_v3` else `2`.
3. **Stage 3 / Dry mode** (`dry_mode AND dew_risk AND dp_diff != None`) ⇒
   `3` si `dp_diff >= dry_v3_delta`; `2` si `>= dry_v2_delta`; si no `1`.
   *(Si `dp_diff` es None ⇒ "stage3 ciego": se loguea y se cae a Stage 1/2.)*
4. **Override ducha** (timer activo) ⇒ velocidad según `ducha_nivel` (`v2`/`v3`).
5. **Auto (IAQ)** ⇒ ver §4.1.

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
`co2_hys≈100`, `pm_hys≈5`. *(Los "adaptive thresholds" que recalculan los umbrales
con percentiles 7d quedan fuera del PoC; ver §7.)*

### 4.2 Modificadores sobre el `target` base (en orden)

Aplicados solo en Auto, sin overrides manuales/ducha:

1. **Free-cooling**: si `freecool_active` ⇒ `target = max(target, 2)`.
   `freecool_active` (con histéresis propia):
   ```
   si NOT enabled OR t_in None OR t_ext None OR t_ext < t_ext_min: False
   si activo previamente: delta(t_in - t_ext) >= delta_off
   si no:                 delta(t_in - t_ext) >= delta_on
   ```
2. **Pre-riesgo de rocío** (`dry_mode AND dew_prerisk AND NOT dew_risk`) ⇒ `max(target, 2)`.
3. **SDHB (intent del bus)** — se evalúa **después** de free-cooling y puede forzar/capar:
   - `request_quiet` / `request_eco` / `request_weather_protect` ⇒ `target = 1`
   - `request_boost` ⇒ `target = 3`
   - `request_freecool` ⇒ `max(target, 2)`
   - `request_normal` ⇒ no-op (deja pasar la decisión IAQ)
4. **Hostile outside (AQI exterior)** — cap final por tramos:
   - `aqi >= t3` ⇒ `0` (OFF). *No anula dew_risk: Stage 3 ya ganó antes.*
   - `aqi >= t2` ⇒ `min(target, 1)`
   - `aqi >= t1` ⇒ `min(target, 2)`
5. **Anti-flapping (`allow_raise`)**: subir de velocidad solo se permite si el ciclo
   viene de un cambio de IAQ, o de `request_boost`/`request_freecool`, o de
   dew_risk/dew_prerisk/dry_mode. En otro caso, si `target > v_actual` ⇒ se mantiene `v_actual`.

El `stage_winner` (trazabilidad) refleja qué capa decidió: `hostile_off`,
`hostile_cap_v1/v2`, `sdhb_quiet/boost/freecool`, `freecool`, `dew_prerisk`, `iaq`.

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

- **Sensores vitales KO** (CO₂/PM2.5 sin datos frescos > 120 s): se bloquea Auto y
  se fuerza V1; alerta.
- **Trip counter**: N fallos en ventana H ⇒ `failsafe_lockout` durante M min
  (defaults: `limit=3`, `window=2h`, `lockout=30min`).
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
- ✅ Umbrales adaptativos: el engine los usa cuando `adaptive_enabled` y se aportan.

**Pendiente (siguiente iteración):**
- Cálculo de los percentiles 7d que alimentan los umbrales adaptativos (vía
  estadísticas del recorder); el engine ya sabe consumirlos.
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
| golden tests YAML | `tests/test_engine.py` (pytest) |
