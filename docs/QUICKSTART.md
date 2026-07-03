# Quickstart — Dynamic Home en 10 minutos (sin tocar hardware)

> Objetivo: instalar la integración, crear **una zona de clima (DC) ficticia**
> sobre helpers, activar **Observe only** y leer los **reason codes** que explican
> cada decisión. **No se actúa sobre ningún relé real** en ningún momento.

**Necesitas:** Home Assistant ≥ 2024.3 y HACS instalado. Tiempo: ~10 min.

Esta guía usa el módulo **Climate (DC)** como ejemplo porque es el que más decisiones
toma. El mismo patrón —entidades ficticias → Observe only → leer reason codes → entidades
reales— vale igual para **DV** (ventilación) y **DS** (persianas). Para recetas por tipo
de instalación real, ver **[PROFILES.md](PROFILES.md)**.

---

## 0 · Instalar (2 min)

1. HACS → Integraciones → ⋮ → **Custom repositories**.
2. Añade `https://github.com/woody-box/Dynamic-Home`, categoría **Integration**.
3. Instala **Dynamic Home** y **reinicia** Home Assistant.

---

## 1 · Crear los helpers ficticios (2 min)

Ajustes → Dispositivos y servicios → **Helpers** → *Crear helper*. Crea estos
cuatro (o pega el YAML de abajo en `configuration.yaml` y reinicia):

| Helper | Tipo | Para qué |
|---|---|---|
| `input_number.dummy_t_int` | Número (10–35, paso 0.1) | Temperatura interior simulada |
| `input_number.dummy_t_ext` | Número (-5–40, paso 0.1) | Temperatura exterior simulada |
| `input_boolean.dummy_rele_calor` | Interruptor | "Relé" de calor (no conectado a nada) |
| `input_boolean.dummy_ventana` | Interruptor | Sensor de ventana simulado (opcional) |

```yaml
# configuration.yaml — opción rápida
input_number:
  dummy_t_int:
    name: Dummy Tint
    min: 10
    max: 35
    step: 0.1
    unit_of_measurement: "°C"
  dummy_t_ext:
    name: Dummy Text
    min: -5
    max: 40
    step: 0.1
    unit_of_measurement: "°C"

input_boolean:
  dummy_rele_calor:
    name: Dummy relé calor
  dummy_ventana:
    name: Dummy ventana
```

> ⚠️ El campo de temperatura interior (`dc_t_int`) exige un sensor con
> `device_class: temperature`. Un `input_number` con `unit_of_measurement: "°C"`
> suele servir; si tu HA no lo acepta en el selector, crea un `template sensor` que
> copie el `input_number` y declare `device_class: temperature`:
>
> ```yaml
> template:
>   - sensor:
>       - name: Dummy Tint sensor
>         unit_of_measurement: "°C"
>         device_class: temperature
>         state: "{{ states('input_number.dummy_t_int') }}"
> ```

---

## 2 · Añadir una zona DC apuntando a los dummies (3 min)

Ajustes → Dispositivos y servicios → **Añadir integración** → *Dynamic Home*.

1. En "qué módulo añadir", elige **Climate (DC)**. (Los otros módulos son **VMC**,
   **Shutter**, **Energy** y **Zones**.)
2. Rellena **solo lo mínimo**:
   - **Temperatura interior** (`dc_t_int`) → **dummy_t_int** (o su `template sensor`).
   - **Temperatura exterior** (`dc_t_ext`, opcional pero recomendable) → **dummy_t_ext**.
   - **Relé / termostato**: deja el termostato real **vacío**. En su lugar usa el
     **relé de demanda de calor** (`dc_demand_heat`) → **dummy_rele_calor**, para ver el
     pipeline sin un `climate` real. (También existe `dc_demand_cool` para frío.)
   - **Ventana** (`dc_window`, opcional) → **dummy_ventana** para probar el lockout.
3. Termina el asistente. Aún **no actúa sobre nada**: el siguiente paso es ponerlo en
   observación.

> 💡 **Atajo por perfil:** en el menú de opciones de la zona, **Aplicar un preset** carga
> de golpe un punto de partida coherente (p. ej. *Salón · suelo radiante comunitario* o
> *Aerotermia individual · tarifa + anti-pico*). Ver [PROFILES.md](PROFILES.md).

---

## 3 · Activar Observe only (30 s)

Busca el dispositivo **Dynamic Home – (tu zona DC)** y enciende el interruptor
**"Observe only"** (`switch.*_observe`, icono de ojo).

Con esto el motor **calcula y publica al bus**, pero **no toca el `dc_demand_heat`
ni ningún relé**. Es el modo seguro para validar comportamiento durante días.

> El switch *Observe only* lo comparten todos los módulos (DC/DV/DS): es el mismo
> `_observe` en `switch.py`. Puedes dejar toda la casa en observación a la vez. También
> se puede conmutar por servicio: `dynamic_home.set_observe`.
>
> En **persianas** hay un atajo global: la pantalla **"Dynamic Shutter · Común"** —que
> aparece **sola** al crear la primera persiana, con los **recuentos** (abiertas/cerradas/
> entreabiertas), los **datos de sol** y los **interruptores globales**— trae **"Solo
> observar (todas)"**, un modo **manual/automático global de la casa** que pone en
> observación todas las persianas de golpe (v0.98.0).

---

## 4 · Leer los reason codes (2 min) — la parte divertida

Cada zona expone un sensor diagnóstico **"Reason"** (`sensor.*_reason`, *Rama de
decisión*) y un sensor de **target** con todo el desglose del pipeline en sus
atributos (`base`, `mods_total`, `bias_*`, `lead_h`, `lead_source`...).

Añade ambos a un dashboard (o míralos en *Herramientas para desarrolladores →
Estados*) y **mueve los dummies** para provocar decisiones:

| Qué haces | Reason esperado | Qué demuestra |
|---|---|---|
| `dummy_t_int` muy por debajo de consigna, modo heat | `heat` | Pipeline normal; mira `target` y `mods_total` |
| Subes `dummy_t_int` rápido (varios pasos seguidos) | `bias_brake` ≠ 0 en atributos | El **freno** de tendencia actúa |
| Enciendes `dummy_ventana` | `off_window` | Gate de seguridad → OFF e intent borrado |
| Modo cool con humedad alta y T cerca del rocío | `off_dew` | Protección de condensación (Magnus) |
| Activas override manual | `override` | El override gana a todo |

Cada cambio se refleja en el reason code **antes** de que nada toque hardware —
esa es la trazabilidad "qué decidió, cuándo y por qué".

### Reason codes que verás por módulo

- **DC (clima):** `heat` / `cool` (pipeline normal), `off_window` / `off_dew` (gates de
  seguridad), `override` (manual), y en el compresor `anticycle_min_off_hold` /
  `anticycle_max_starts_hold` / `anticycle_safety_off`. En atributos: `bias_brake`,
  `bias_tariff`, `lead_source: adaptive`.
- **DV (ventilación):** `iaq` (CO₂/PM), `shower_rh` (boost por ducha), `dry_mode` (secado
  por rocío), `freecool` (free-cooling), `quiet_cap` (horas de silencio),
  `failsafe_vital_ko` (fuente vital obsoleta), `hold_antiflap`.
- **DS (persianas):** `manual_hold` (movimiento manual respetado — por encima de
  meteo/lluvia y del bloqueo), `presence_sim` (simulación de presencia en Away), `mode_sleep`
  (Sleep de la zona), `summer_solar_shield` / `summer_solar_geo` (escudo solar fijo o
  geométrico), `summer_heat_shield` (tope por calor refrigerando), `winter_solar_gain`
  (ganancia), `winter_cold_shield` / `winter_mild_open` (día de invierno sin sol),
  `night_purge` (ventilación nocturna) / `freecool_night` (free-cooling nocturno de verano),
  `dawn_ramp` (amanecer), `meteo_rain` / `meteo_alert` y los caps de viento. **Ojo:**
  `night_insulate` = el switch **F16** (aislamiento nocturno), distinto de
  `winter_night_insulate` = la rama **built-in** de calefacción sin sol. Glosario completo en
  [`SPEC_DS.md`](SPEC_DS.md).

---

## 5 · Pasar a producción (cuando estés listo)

1. Valida el comportamiento durante varios días en Observe only.
2. Sustituye `dummy_rele_calor` por el **relé/termostato real** en las opciones.
3. **Apaga Observe only**.
4. Mantén siempre una ruta de **override manual** disponible.

> Repite este mismo patrón para **DV** (ventilación) y **DS** (persianas):
> entidades dummy → Observe only → leer reason codes → entidades reales.

---

## Resolución de problemas

| Síntoma | Causa probable | Qué hacer |
|---|---|---|
| El selector no acepta tu sensor de temperatura | falta `device_class: temperature` | usa un `template sensor` (ver paso 1) |
| El reason se queda en `failsafe_vital_ko` / aparece un aviso en **Reparaciones** | una fuente requerida está `unavailable`/renombrada | revisa la entidad (Ajustes → Configurar); el aviso se borra solo al recuperarse |
| Nada cambia al mover los dummies | sigues en Observe only (correcto) o el módulo está en grace de arranque | espera el grace; mira el reason, no el relé |
| Quieres compartir tu configuración para pedir ayuda | — | Ajustes → el dispositivo → ⋮ → **Descargar diagnósticos** (JSON con opciones + estado, sin secretos) |

---

## Siguiente paso

- **[PROFILES.md](PROFILES.md)** — recetas por tipo de instalación real (radiante
  comunitario, VMC de 3 velocidades, persianas multi-fachada, aerotermia con tarifa).
- **[REQUIREMENTS.md](REQUIREMENTS.md)** — el detalle de cada feature (F01–F37).
