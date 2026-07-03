# Recetas por perfil real — Dynamic Home

> Un ejemplo por **caso de instalación**, no por módulo. Cada receta dice qué
> módulos activar, qué declarar en el **perfil de instalación (F26)**, qué **preset**
> aplicar como punto de partida y qué reason codes vigilar. Todas asumen que primero
> validas en **Observe only** (ver [QUICKSTART.md](QUICKSTART.md)).

Recordatorio del perfil F26 — la terna **(generador, distribución, emisión)** deriva el
comportamiento:
- **`peak`** (se aplica F03 anti-pico): carga eléctrica bajo tu control → eléctrica
  directa, o bomba de calor **individual**.
- Las calderas de combustión (gas/gasoil/pellet/leña) solo mueven una bomba → **nunca**
  disparan el ICP, así que F03 no aplica.
- Distribución **central/comunitaria** → F37 (changeover de comunidad) gobierna la
  dirección estacional, y la zona no puede pedir frío si el anillo va en calor.

> **Aplicar un preset:** en el menú de opciones de cada módulo → **Aplicar un preset**.
> Carga de golpe un punto de partida coherente (solo números; tus entidades no se tocan).
> Luego afina a tu gusto. Inventario completo en [PRESETS.md](PRESETS.md).
>
> **Exportar tu configuración:** Ajustes → el dispositivo → ⋮ → **Descargar diagnósticos**
> da un JSON con tus opciones + el estado vivo, útil para guardar o pedir ayuda.

---

## Perfil 1 · Piso con suelo radiante comunitario

**Escenario:** edificio con caldera central y agua compartida a 2 tubos (changeover).
Tú no decides si el anillo va en calor o frío; lo decide el edificio.

**Perfil F26:** generador `gas_boiler` (o el que tenga la comunidad) · distribución
**`central_shared`** · emisión **`underfloor`** (inercia alta).

**Módulos:** DC (una zona por estancia con sonda) + entrada de **Zones** con el
**changeover de comunidad**. Opcional: DV (la VMC) y DS (persianas), que **también
siguen el changeover** (ver más abajo).

**Preset:** DC → *Salón · suelo radiante (fuente comunitaria)* (`salon_radiant_communal`).

**Configuración clave:**
- En la entrada de **Zones**, define el **sensor de changeover** (`changeover_sensor`) →
  la **sonda de temperatura del agua de impulsión**. De ahí se resuelve si la casa está en
  `heat`/`cool`, y las zonas `central_shared` se gatean a esa dirección (no puedes pedir
  frío si el anillo va en calor). El selector **«Changeover {zona}»** permite forzar la
  dirección por zona (colectores independientes); en `auto` hereda la de casa.
- Inercia alta → deja que el **lead adaptativo** aprenda: la anticipación grande es
  precisamente lo que necesita el suelo radiante (precalienta con horas de margen).
- **No hay anti-pico** (F03 off): la carga es térmica de la comunidad, no eléctrica tuya.
  El ICP de tu piso no lo ve.
- **DS y DV siguen la temporada del edificio:** sin termostato por persiana, cada DS
  adopta el changeover de casa (escudo solar/free-cooling en verano, ganancia/aislamiento
  en invierno); y DV **suprime el free-cooling en temporada de calor** para no ventilar el
  calor comunitario que pagas en el reparto.

**Reason codes a vigilar:** `heat`/`cool` con `lead_source: adaptive`; en DS
`summer_solar_shield` / `winter_solar_gain`; en DV el `freecool` **suprimido** en calor.

> ⚠️ Si activas free-cooling en DV pero **no** configuras el changeover y hay calefacción,
> Dynamic Home te avisa en **Reparaciones** (podría ventilar el calor que pagas). Configura
> el changeover o desactiva el free-cooling.

---

## Perfil 2 · Casa con VMC de 3 velocidades

**Escenario:** unifamiliar con recuperador de doble flujo (VMC) accionado por relés
(V1/V2/V3) y sensores de CO₂, PM2.5 y humedad. El protagonista es **DV**.

**Perfil F26:** irrelevante para DV (DV no es carga eléctrica de pico); declara el clima
aparte si lo tienes.

**Módulos:** DV (la VMC) + opcionalmente DC para que el bus coordine.

**Preset:** DV → *VMC doble flujo (casa)* (`home_vmc`).

**Configuración clave:**
- Mapea **CO₂**, **PM2.5** y los tres relés de velocidad. Activa **EMA** (suaviza picos) y
  revisa la histéresis (`co2_hys`, `pm_hys`) para que no flapee.
- **Horas de silencio (F12):** `quiet_enabled` con ventana nocturna y `quiet_max_level: 1`.
  La salud gana al silencio: si CO₂/PM superan el umbral crítico, el cap se ignora y sube.
- **Punto de rocío (F13):** si tienes humedad interior/exterior, activa `dry_mode`. Solo
  ventila para secar cuando el aire de fuera es **de verdad más seco** (`dp_diff` supera
  `dry_margin`), no por humedad absoluta.
- **Ducha (ΔRH):** boost a V3 al detectar el salto de humedad del baño, con hold.
  **Varios baños:** opciones de la VMC → **Baños** → añade hasta 6 (nombre + sensor de
  humedad). Cualquier ducha en cualquier baño dispara el boost (gana la mayor subida) y el
  atributo `shower_bathroom` del ventilador dice **qué baño** fue.
- **Free-cooling:** tiene **switch propio** ("Free-cooling", ON por defecto) — ya no lo
  fuerza la mera presencia de sondas, puedes apagarlo. Solo se engancha con el interior
  **genuinamente caluroso** (número "Temp. int. mínima", 24 °C por defecto, editable), así
  no ventila tu calefacción. En noches de verano puede saltarse el cap de silencio/Sleep
  hasta el "Tope nocturno free-cool" (V2 por defecto; ponlo a 1 para silencio absoluto).
  Con changeover en calor se **suprime** (F37); sin changeover se rige solo por temperatura
  (y verás el aviso de Reparaciones si hay calefacción).

**Reason codes a vigilar:** `iaq`, `shower_rh`, `dry_mode`, `freecool`, `quiet_cap`,
`failsafe_vital_ko` (si un sensor se queda obsoleto), `hold_antiflap`.

---

## Perfil 3 · Vivienda con persianas motorizadas

**Escenario:** persianas motorizadas integradas en HA, varias fachadas con orientaciones
distintas. El protagonista es **DS**, coordinado por **DC** (el cerebro).

**Perfil F26:** según tu clima; aquí lo relevante es la geometría de fachadas.

**Módulos:** DS (una entrada por persiana/fachada) + DC (para que pida ganancia o escudo
solar).

**Preset:** DS → *Persianas motorizadas · multi-fachada* (`motorized_facades`).

**Configuración clave:**
- Asigna cada persiana a su **fachada** por azimut (`facade_azimuth_deg`). DC, al calentar,
  publica `request_solar_gain`; al refrigerar, `request_solar_shield`. Cada persiana solo
  reacciona si **su** fachada está al sol → sombreas la cara soleada y dejas el resto
  quieto.
- Activa **avisos meteo** (`ds_alert_wind`, `ds_alert_hail`) → la persiana sube/protege
  ante viento o granizo (cap de seguridad por encima de la lógica solar).
- **Anti-pico de motores (F03, canal transitorio):** si varias persianas arrancan a la
  vez, el `PeakLoadHub` espacia los arranques (`peak_stagger_s`) para no clavar el inrush
  de varios motores simultáneos. Es un canal **separado** del de clima.
- **Temporada:** sin un `climate` enlazado por persiana, DS sigue el **changeover de casa**
  (F37) para decidir escudo solar (verano) vs ganancia (invierno).
- **El override manual manda sobre todo, incluso el bloqueo.** Si mueves una persiana a mano,
  esa orden gana sobre la lógica solar, el escalonado anti-pico **y el bloqueo** (el Lock ya
  no re-cierra en ≤60 s lo que acabas de abrir); persiste incluso a un reinicio de HA (se
  restaura desde el sensor "Modo de control" si no ha caducado el hold). Al expirar el hold —o
  al pulsar "Volver a automático"— la automatización (y el bloqueo) reimponen su posición.
- **Aplicar un perfil a toda la casa:** la pantalla **"Dynamic Shutter · Común"** (dispositivo
  propio, se crea sola con la primera persiana) trae **interruptores globales "a lo bruto"**
  —**Solo observar (todas)**, protección meteo, escudo térmico, escudo de sol, aislamiento
  nocturno, amanecer gradual, sombreado geométrico y limitación de pico— más **"Reanudar
  automático (todas)"**. Encienden/apagan la función en **todas** las persianas de golpe; ojo,
  **no recuerdan** el estado individual (lo explica la entidad "Aviso"). Lo íntimo de cada
  hueco (privacidad, bloqueo, seguir movimientos manuales) sigue **por persiana**.

**Reason codes a vigilar:** posición por `summer_solar_shield` / `winter_solar_gain`,
`freecool_night`, cap por `alert_wind` / `alert_hail` y `meteo_rain`, y en el bus el
`peak_stagger` cuando reparte arranques.

---

## Perfil 4 · Instalación con tarifa eléctrica y anti-pico

**Escenario:** bomba de calor **individual** (o eléctrica directa) con tarifa por tramos
(valle/normal/punta) y un ICP que no quieres hacer saltar. Aquí entran **los tres**
mecanismos: tarifa (F34), anti-pico (F03) y anticiclado (F09).

**Perfil F26:** generador `heatpump_air_water` (o `electric_direct`) · distribución
**`individual`** · emisión la que toque. Esto activa `peak = True` → **F03 aplica**.

**Módulos:** DC (zonas) + módulo **Energy** (publica el estado de tarifa
`cheap|normal|peak`) + opcionalmente un medidor de potencia real.

**Preset:** DC → *Aerotermia individual · tarifa por tramos + anti-pico*
(`heatpump_individual_tariff`).

**Configuración clave:**
- **Tarifa → lead (F34):** con la tarifa publicando estado, DC modula la anticipación:
  `tariff_lead_cheap_mult: 1.5` (precalienta/preenfría cuando es barato, cargando masa
  térmica) y `tariff_lead_peak_mult: 0.6` (rampa menos en punta). Opcional `tariff_bias_c
  > 0` para empujar también la base en valle.
- **Anti-pico (F03):** elige **modo cuenta** (`peak_max_zones`) o **modo potencia**
  (`peak_max_power_w > 0`, presupuesto en vatios con medidor real o `est_w_on`). El hub
  espacia arranques (`peak_stagger_s`) y **cede por prioridad**: la zona más desviada de
  consigna arranca primero (`peak_yield`).
- **Bypass de confort:** `peak_comfort_bypass_c: 2.5` → una desviación severa salta el gate
  de pico entero. El ahorro nunca te congela; la seguridad sigue por encima.
- **Anticiclado (F09):** `anticycle_min_on_s` / `min_off_s` / `max_starts_per_h` protegen
  el compresor. Es **agregado**: una zona que flapea no cuenta como arranque si otra
  mantiene el compresor despierto. La seguridad (ventana/rocío) puede pararlo antes del
  min-ON. El reparto de **prioridad** entre zonas vive en F03, no aquí.

**Reason codes a vigilar:** `bias_tariff` en los atributos del target, `peak_over_budget`
/ `peak_stagger` / `peak_yield` en el arbitraje, y `anticycle_min_off_hold` /
`anticycle_max_starts_hold` / `anticycle_safety_off` en el compresor.

> **Topología multi-equipo:** si tienes dos bombas de calor, declara `compressor_id`
> distinto por grupo (en el editor de emisores) → el `AntiCycleHub` corre un estado por
> canal y no se estorban. Igual con el `PeakLoadHub`: clima y motores de persiana van en
> canales separados.

---

## Perfil 5 · Terraza acristalada (efecto invernadero)

**Escenario:** una persiana en la puerta de la cocina que da a una **terraza
acristalada**, orientada al **este (~90°)**, así que recibe el sol del amanecer.
La terraza, al estar acristalada, hace **efecto invernadero** en verano: se
calienta mucho y ese calor acaba entrando a la cocina/salón (que están abiertos).

**Módulos:** DS (la persiana de la cocina) + DC del salón como referencia de
temporada.

**La idea clave — usar la terraza como "exterior" de esa persiana:**
- `facade_azimuth_deg: 90` (este).
- `ds_t_out: sensor.terraza` → la Tª **de la terraza**, no la de la calle (es el
  aire que realmente entra).
- `climate: climate.salon` → como cocina y salón están abiertos, el salón es la
  referencia. Su modo da la **temporada** a DS: `heat` (invierno) / `off`
  (neutro) / `cool` (verano).

> **¿No tienes refrigeración real?** Crea un **`climate` dummy** en `cool`. No
> enfría nada, pero le dice a DS *"estoy en modo verano, protege del calor"* → el
> **escudo térmico** se activa igual.

**Configuración clave:**
- Activa **Sombreado geométrico** (ajusta la posición a la incidencia real del sol
  en esa fachada) y, sobre todo, **Thermal shield** (tiene prioridad).
- **Apertura máx. refrigerando**: el tope cuando refrigeras y la terraza está más
  caliente que dentro.
  - `20%` → se queda lo justo abierta para algo de luz natural.
  - `0%` → **"modo cueva"**: máxima protección térmica, sin luz.
- Si la terraza está **más fresca** que el interior, la persiana puede abrir para
  aprovechar luz o **free-cooling**; si está **más caliente** y estás en `cool`,
  **limita la apertura** para que no entre el calor.

**Por fachada:** cada persiana lleva su orientación y su tope. En el salón, una
persiana **norte** (poca carga solar) puede abrir un 20% para tener luz, mientras
las de más sol se mantienen más cerradas.

**De noche:** si la Tª exterior baja por debajo de la del salón/cocina, DS puede
**subir** las persianas para facilitar el free-cooling (lo ideal sería abrir
también las ventanas, pero eso aún no está motorizado 😄).

**Reason codes a vigilar:** `summer_heat_shield` (tope por calor refrigerando),
`summer_solar_geo` (sombreado geométrico), `freecool_night` (purga nocturna),
`dawn_ramp` (amanecer) y `winter_solar_gain` en invierno.

> En resumen: no es "bajar si hace sol". Es usar **cada persiana** según su
> orientación, Tª exterior/interior, estación y modo de climatización para
> equilibrar **luz natural, confort y protección térmica**.

---

## Más

- **[QUICKSTART.md](QUICKSTART.md)** — montar una zona ficticia y leer reason codes en 10 min.
- **[PRESETS.md](PRESETS.md)** — inventario completo de valores ajustables y presets.
- **[REQUIREMENTS.md](REQUIREMENTS.md)** — el detalle de cada feature (F01–F37).
