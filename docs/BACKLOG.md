# Dynamic Home — Backlog de ideas (exploración)

> Documento vivo. **No es compromiso de implementación.** Vamos revisando cada
> idea una a una; al cerrar la opinión se marca *Revisada* y se rellena
> *Perfilado*. Cuando estén perfiladas, se redactará un documento de requisitos
> y se implementarán en una fase posterior.

**Leyenda de estado:** ☐ pendiente · 🔄 en discusión · ☑ revisada (perfilada) · ❄️ congelada

## Pendientes para el próximo release
- **PR a `home-assistant/brands`** con `docs/brand/icon.png` + `icon@2x.png` (icono en HA/HACS).
- **Bump de versión + notas** al cortar el release (incluir iconos y lo que entre).

**Valor:** Alta / Media / Baja · **Esfuerzo:** S (pequeño) / M (medio) / L (grande)

---

## Cross-módulo (bus SDHB)

### F01 · Modo global de la casa ⭐
- **Estado:** ☑ revisada · **Módulos:** DV·DS·DC (y futuros) · **Valor:** Alta · **Esfuerzo:** L
- **Idea:** un control de "modo" (`Home/Away/Sleep/Boost/Eco`) que publica al bus y sesga todos los módulos a la vez.
- **Perfilado:**
  - **Modos base** `Home/Away/Sleep/Boost/Eco` válidos, pero el **comportamiento por modo es configurable** (no hardcodeado). Caso de uso clave: en `Sleep`, la VMC baja a velocidad baja por **ruido (WAF)**. Mínimo configurable por modo: cap de velocidad VMC; ideal: un "perfil" por módulo y modo.
  - **Vive en el BUS**, no en DC: el modo (incl. `Away`/vacaciones) existe aunque DC no esté instalado. El **modo vacaciones del bus sustituye** al toggle `vacation` de DC.
  - **Por grupos de zona**, no solo global (ver F24): p.ej. `salón-cocina`, `habitaciones`, `baños`; cada persona puede gestionar su grupo con su preset. Probable "modo casa" global + override por grupo.
  - **Extensible** a módulos futuros (Dynamic AC, F25): un módulo nuevo solo tiene que leer el modo del bus.
  - **Jerarquía de autoridad (de más a menos):**
    1. **Override manual** (explícito, temporizado) — única forma de saltarse el horario.
    2. **Horario / schedule** — si dice OFF a las 21:00, se apaga.
    3. **Manual** (preset normal del usuario) — gana al modo.
    4. **Modo** (global / de grupo) — capa base.
    > Nota: un preset manual normal NO se salta el horario; solo el override manual sí (como en el YAML).

### F02 · Explicador de conflictos del bus ⭐ — ✅ implementada
- **Estado:** ☑ revisada · **Módulos:** DV·DS·DC · **Valor:** Alta · **Esfuerzo:** S
- **Idea:** sensor que expone "quién ganó y por qué" cuando hay intents en conflicto (p.ej. DC pide abrir por ganancia solar y DS quiere cerrar por viento).
- **Perfilado:**
  - **Una entidad por consumidor** del bus (cada VMC, cada persiana; y DC en su self-bias) — la que muestra qué intents le llegan y cuál gana sobre él.
  - **Agrupadas bajo un dispositivo nuevo central** "Dynamic Home · Bus" (no cuelgan de cada módulo). Implementación: device con identificador propio `(DOMAIN, "bus")`; el hub registra una entidad por consumidor.
  - **Contenido: ganador + motivo** (intent ganador como estado, motivo como atributo: prioridad/TTL). Sin la lista completa de descartados.
  - **Solo estado actual** del sensor; **sin** registro en logbook/historial de conflictos.
  - Encaje: el `SdhbHub` ya tiene `source/intent/target/priority/ttl`; basta añadir un `explain(targets)` que devuelva ganador + motivo.
  - **Implementado:** `BusSensor` por consumidor (DV/DS/DC) bajo el dispositivo central "Dynamic Home · Bus" (`(DOMAIN, "bus")`); estado = intent ganador; atributos `source`/`priority`/`candidates`/`reason`/`target`/`ttl_remaining_s` + **aspirante** (`runner_up`/`runner_up_priority`, sin la lista completa). `hub.explain()` devuelve todo (incluido TTL restante y runner-up, orden estable = `winner()`). Evento `dynamic_home_conflict` al cambiar el ganador; solo estado actual.

### F03 · Anti-pico / reparto de cargas
- **Estado:** ☑ revisada · **Módulos:** DC (vía bus) · **Valor:** Media (alta solo en eléctricas) · **Esfuerzo:** M
- **Idea:** evitar que todas las zonas DC arranquen a la vez; escalonar demanda.
- **Perfilado:**
  - **Depende del tipo de instalación** (prerrequisito **F26**). Solo es realmente necesaria/activa en **calefacción eléctrica**; en aerotermia (central compartida o individual) y gas el pico no es problema → **off por defecto**.
  - **Modo de límite según hardware:**
    - Si hay **medidor(es) de potencia** → límite por **amperios/kW** (cada zona con su potencia asignada).
    - Si no → límite por **N zonas activas** simultáneas (sobre las zonas actuables).
  - **Escalonado temporal** (para eléctricas): no encender una zona hasta que la anterior lleve, p.ej., **10 s** en marcha (suaviza arranques/inrush). Delay configurable.
  - **Pendiente de detallar en implementación:** prioridad entre zonas en cola (por desviación de temperatura vs prioridad manual) y un posible **bypass de confort** si hay mucho frío.
  - El bus ya conoce todas las zonas → el árbitro de cargas vive en el hub.
  - **Aplica también a DS (persianas):** el pico de arranque de varios motores a la vez (≈2000 W con 12 persianas) puede saltar el ICP → escalonar también el bajado/subido masivo, no solo el clima eléctrico.

## Energía y coste

### F04 · Precio de electricidad → Adaptive Lead ⭐
- **Estado:** ❄️ congelada · **Módulos:** DC · **Valor:** Alta · **Esfuerzo:** M
- **Idea:** input de precio (PVPC/Nordpool) para desplazar el pre-calentamiento/enfriamiento del Adaptive Lead a horas baratas.
- **Perfilado:** _Congelada por decisión del usuario — retomar cuando madure la idea._

### F05 · Compensación por curva exterior (outdoor reset)
- **Estado:** ❄️ congelada · **Módulos:** DC · **Valor:** Media · **Esfuerzo:** M
- **Idea:** curva clásica de calefacción que ajusta la consigna de la fuente según la temperatura exterior.
- **Perfilado:** _Congelada — para la instalación objetivo (aerotermia central, sin control de impulsión) se solapa con `bias_exterior`; reconsiderar para usuarios con caldera/aerotermia individual._

### F06 · Sensor de coste/consumo/energía — ✅ implementada (solo energía)
- **Estado:** ✅ implementada (energía; coste pendiente) · **Módulos:** DV·DS·DC · **Valor:** Media-Alta · **Esfuerzo:** M
- **Idea:** energía/coste por módulo, con medidor real si lo hay o estimación por horas si no.
- **Perfilado:**
  - **Potencia: medidor real preferente.** Si el módulo tiene un sensor de potencia (Shelly) → se usa ese. Si no, **estimación** por potencia configurable por estado/velocidad.
  - **Energía (kWh)** como sensor `device_class: energy`, `state_class: total_increasing` → **entra en el panel de Energía de HA**.
  - **Coste (€) opcional:** vía **sensor de precio** (tarifa plana que el usuario mete, o integración externa para variable) o un precio fijo configurable.
  - **Módulos:** VMC y Persianas (suelen tener Shelly). **DC opcional** y ligado a **F26**: en aerotermia comunitaria no aporta; en eléctrico/AC sí, si hay medidor. (El usuario ya calcula horas de frío/calor por el helper del climate; portarlo es interesante para él, opcional para otros.)
  - **Potencia instantánea / pico:** exponer la potencia total instantánea. **Cruza con F03**: aunque las persianas consumen poco, su **pico de arranque** importa (12 persianas bajando a la vez ≈ 2000 W → puede saltar el ICP), así que el anti-pico debe considerar también DS.
  - **Implementado:** sensor de **energía (kWh)** (`device_class: energy`, `state_class: total_increasing`, `RestoreSensor`) en **VMC, DC y persianas** → entra en el **panel de Energía** de HA. **Medidor real** preferente (campo opcional `power_meter` en los tres asistentes); si no, **estimación**: VMC integra W por velocidad (tunables `est_w_v1/v2/v3`), DC integra `est_w_on` mientras pide calor/frío (reaprovecha la señal de demanda de F27), DS estima la energía marginal por movimiento del motor (`est_w_motor` × `full_travel_s` × Δ%). Helper puro `energy.py`. **Diferido:** coste (€) por sensor de precio/tarifa fija; potencia instantánea/pico (cruza F03); medidor real en DS (el muestreo a 60 s no captura un movimiento de segundos).

## Robustez y mantenimiento

### F07 · HA Repairs sobre `degraded` ⭐ — ✅ implementada
- **Estado:** ☑ revisada · **Módulos:** DV·DS·DC · **Valor:** Alta · **Esfuerzo:** S
- **Idea:** cuando un sensor configurado desaparece o lleva obsoleto, emitir un *issue* accionable en Ajustes→Reparaciones (se apoya en el `binary_sensor degraded` ya existente).
- **Perfilado:**
  - **Disparo:** entidad **ausente/renombrada** Y **obsoleta** (`unavailable`/`unknown` > X min, p.ej. 5 min) — igual que su YAML actual.
  - **Solo fuentes requeridas** (las opcionales se ignoran).
  - **Acción del botón:** **reabrir el config flow** del módulo para corregir el mapeo.
  - **Un issue por módulo**, listando las fuentes que faltan (como su Telegram "DV HW MAP / SENSORES REQUERIDOS KO ... Missing (2): ...").
  - **Extra opcional:** emitir además un **evento** (`dynamic_home_degraded`) para que quien quiera lo enrute a Telegram/notify (como hace hoy). Lo nativo es el *issue* de Reparaciones; el evento es para power-users.
  - Se borra el issue al recuperarse la fuente (`async_delete_issue`).
  - **Implementado:** mixin `DegradedTracker` (`repairs.py`) compartido por DV/DS/DC; issue por módulo con la lista de fuentes requeridas ausentes/obsoletas (DV `sw_pwr/v2/v3`+`co2`/`pm25`; DS `cover`; DC Tª interior), evento al instante, issue tras `ISSUE_STALE_S` (no-fixable + `learn_more_url`), borrado al recuperar/descargar; `binary_sensor` "Degradado" en los tres. **Botón que reabre el config flow → diferido** (decisión del usuario: no-fixable + enlace).

### F08 · Vida del filtro VMC — ✅ implementada
- **Estado:** ☑ revisada · **Módulos:** DV · **Valor:** Media · **Esfuerzo:** S
- **Idea:** % de vida del filtro + recordatorio al umbral, sobre `filter_hours` ya contabilizadas.
- **Perfilado:** (réplica nativa de su sección "7) Filtros")
  - **Intervalo configurable** `number` "Vida del filtro (h)", default **3650 h** (su valor de fábrica). Horas **totales simples** (no ponderadas por velocidad; ponderación queda como posible mejora futura).
  - **Sensor "% de vida del filtro"** = 100·(1 − filter_hours/intervalo). Reset = el **botón existente** (mecanismo offset, como su `dv_filtros_horas_offset`).
  - **Umbral único** (al 100% del intervalo). Pre-aviso al 90% queda opcional.
  - **Aviso:** issue de **Repairs** (sistema de F07) + opción de notificación persistente / evento para Telegram (como sus toggles "Notificaciones persistentes / Telegram").
  - Fecha/contador de último cambio: opcional, no por defecto.
  - **Implementado:** número "Vida del filtro (h)" (3650) + `FilterLifeSensor` (%) + botón/servicio `reset_filter`; evento `dynamic_home_filter_due` con histéresis y, ahora, **issue de Repairs `filter_due`** (no-fixable + enlace) creado al cruzar el umbral y borrado al resetear/descargar. Fecha de último cambio → no.

### F09 · Anti-ciclado corto (DC) — ✅ implementada
- **Estado:** ✅ implementada · **Módulos:** DC · **Valor:** Media (alta con compresor) · **Esfuerzo:** M
- **Idea:** tiempos mínimos ON/OFF para proteger compresores; el aprendizaje ya mide la tasa, así que hay datos.
- **Perfilado:**
  - **Protege con:** `min ON`, `min OFF` **y** `máx arranques/hora` (default **6/h**).
  - **Gated por F26:** **oculto** en gas, eléctrico y aerotermia comunitaria; **visible/activo** con **compresor** (aerotermia o AC individual). El **sistema de emisión** (suelo radiante / radiadores / fancoil / conductos…) también influye en los valores por inercia.
  - **La seguridad manda:** ante riesgo de condensación u orden de seguridad, el anti-ciclado **cede** (apaga aunque no se cumpla el min ON).
  - Contexto: hoy el usuario solo protege por seguridad (anticondensación); el ciclado de compresor no lo gestiona en su aerotermia comunitaria, pero es relevante para instalaciones individuales.
  - **Implementado:** switch opt-in "Anti short-cycle" por zona; modelo puro `anticycle.py` (min ON/OFF + máx arranques/h, default 6) sobre el **agregado del compresor compartido** (hub único en `hass.data`: cualquier zona ON lo despierta; el flap de una zona no cuenta como arranque). Vigila el ON/OFF que DC manda al termostato (lo conduce a OFF mientras retiene); la seguridad cede. Gating F26 y agrupación por compresor F25 diferidos.

### F10 · Servicios y eventos nativos — ✅ implementada
- **Estado:** ☑ revisada · **Módulos:** DV·DS·DC · **Valor:** Media · **Esfuerzo:** S
- **Idea:** capa de acciones (servicios) + eventos propios para automatizar/dashboards.
- **Perfilado:** (aceptado tal cual)
  - **Ambos:** servicios (comodidad) + eventos (enganche para replicar su Telegram/notify).
  - **Servicios:** `reset_learning` (Adaptive Lead), `boost` (módulo, minutos), `set_observe` (on/off), `reset_filter`, `recalibrate`/`refresh`.
  - **Eventos:** `dynamic_home_degraded` (F07), `dynamic_home_conflict` (bus, F02), `dynamic_home_filter_due` (F08), `dynamic_home_mode_changed` (F01).
  - **Implementado:** 5 servicios (`reset_learning`/`set_observe`/`reset_filter`/`recalibrate`/`boost`) registrados una vez por integración, resolución de destino por entidad/dispositivo/área (`async_extract_config_entry_ids`), `services.yaml` + traducciones EN/ES; los 4 eventos emitiéndose en transición (degraded/conflict/filter_due/mode_changed, + mold/window/adjacent).
  - **Prioridad:** *nice to have*; los **eventos primero** (para mantener el Telegram), los servicios después. No bloqueante.

## DV (ventilación)

### F11 · Ventilación anticipatoria (derivada CO₂/PM)
- **Estado:** ☑ revisada · **Módulos:** DV · **Valor:** Media · **Esfuerzo:** M
- **Idea:** pre-ventilar cuando CO₂/PM suben rápido (ya hay EMAs; falta la derivada), análogo al lead de DC.
- **Perfilado:** (modelado como el **refuerzo de ducha/humedad**, pero con calidad de aire)
  - Disparo por la **derivada** (pendiente) de **CO₂ y PM** (EMA-suavizada), con **umbral on/off** y **hold** (anti-transitorio), igual que `shower_rh_delta_on/off` + `shower_hold_s`.
  - **Anticipación suave:** la pendiente fuerte adelanta el salto de velocidad (V2/V3) antes de cruzar el umbral de nivel.
  - Ambos contaminantes; ampliable a VOC/NOx vía F30.

### F12 · Horas de silencio (cap nocturno / off)
- **Estado:** ☑ revisada · **Módulos:** DV · **Valor:** Media · **Esfuerzo:** S
- **Idea:** franja en la que la VMC no supera cierta velocidad por ruido (WAF), distinto del schedule de encendido.
- **Perfilado:**
  - **Nivel máximo seleccionable en la franja: `OFF / V1 / V2`** (V3 = sin cap). El `OFF` cubre el "apagar la máquina a ciertas horas".
  - **Franja propia** (hora inicio/fin + nivel máx) **y** reutilizable por el **modo Sleep (F01)** (Sleep aplica el cap configurado). Ambos.
  - **Excepción de seguridad:** un umbral **crítico** de CO₂/PM **cede** el cap y sube igual (salud > silencio).
  - **Por día** opcional (enlaza con F29).

### F13 · Intercambio por humedad absoluta ⭐
- **Estado:** ☑ revisada · **Módulos:** DV · **Valor:** Alta · **Esfuerzo:** M
- **Idea:** ventilar para secar **solo si el aire exterior es más seco** (comparar puntos de rocío), no por HR relativa.
- **Perfilado:**
  - **Criterio: punto de rocío** (`dp_out < dp_in − margen`). Es la medida más correcta (proxy de presión de vapor; evita la dependencia de densidad de los g/m³) y **ya se calcula** (`dp_diff = dp_in − dp_out` existe en el coordinator).
  - **Es una mejora del `dry_mode` actual** (mismo objetivo: secar el ambiente con la VMC para salir del punto de rocío en refrigeración); pasa a **gatear por `dp_diff`**.
  - **Margen ("corta ventaja") configurable**: no ventilar por diferencias mínimas.
  - **Histéresis on/off regulable** para no encender/apagar en el límite.

### F14 · Boost (V3 temporizado)
- **Estado:** ☑ revisada · **Módulos:** DV · **Valor:** Baja · **Esfuerzo:** S
- **Idea:** forzar V3 N minutos con auto-reversión (reutiliza el timer de override de F#8).
- **Perfilado:**
  - **Duración configurable** (`number` "minutos de boost") — nada hardcodeado.
  - **Solo V3.**
  - Se expone como **servicio** `dynamic_home.boost` (parte de F10). Un `button` queda como azúcar opcional.
  - **Re-disparar reinicia** el temporizador.

## DS (persianas)

### F15 · Sombreado geométrico real ⭐ — ✅ implementada
- **Estado:** ✅ implementada · **Módulos:** DS · **Valor:** Alta · **Esfuerzo:** L
- **Idea:** calcular la penetración solar por geometría y cerrar solo lo necesario, no todo/nada.
- **Perfilado:**
  - **Objetivo de control: "proteger X metros de suelo"** (no dejar que el sol directo entre más de X m). Configurable.
  - **Más geometría (config opcional):** además de `window_height_cm` + `overhang_cm`, añadir **altura de alféizar** (suelo→ventana) y **profundidad útil de la sala**. Mejoran el cálculo de penetración.
  - **Cálculo:** penetración = f(elevación y azimut del sol, geometría, voladizo); de ahí el % de cierre que tapa justo esa penetración hasta el objetivo de metros.
  - **Por pasos** (p.ej. 25/50/75), no continuo (el slew ya suaviza, y evita mover la persiana cada poco).
  - **Fallback:** si faltan datos de geometría → comportamiento actual (% fijo de solar shield).
  - **Implementado:** switch opt-in **"Geometric shading"** por persiana. Cuando está activo, la rama solar de verano usa `geo_shade_pos`/`solar_penetration_m` (alféizar, alto de ventana, voladizo, azimut, profundidad de sala) para bajar la persiana **por pasos** (`shade_step_pct`) solo hasta proteger `target_penetration_m`, con suelo en `summer_min_open_pct` (`reason: summer_solar_geo`). Con el switch apagado (por defecto) o cuando el sol no procede, **fallback** al escudo fijo `summer_solar_shield`. Helper puro en `ds_engine`.

### F16 · Aislamiento nocturno estacional
- **Estado:** ☑ revisada · **Módulos:** DS · **Valor:** Media · **Esfuerzo:** S
- **Idea:** cerrar en noche de invierno (aislar) / abrir en noche de verano (refrescar); ampliar `winter_night_pct`.
- **Perfilado:**
  - **Estación por el MODO del climatizador de la zona:** `heat` → cara invierno (**cerrar para aislar**); `cool` → cara verano (**abrir/purga nocturna**).
  - **Activable por zona.**
  - **No duplicar free-cooling:** la cara de verano se **coordina** con el free-cooling existente. Lo distintivo es la **estrategia de inercia**: en cool, abrir de noche para **pre-acondicionar la masa** y empezar el día siguiente con ventaja, incluso en condiciones marginales (zona en/por encima de consigna). _Condiciones térmicas exactas (ext vs int, consigna) a detallar en implementación._
  - **Noche = sol bajo horizonte.**
  - **Seguridad manda** (viento/lluvia/override por encima del aislamiento).
  - **Implementado:** switch "Night insulation" (opt-in); por modo del climate (heat→cerrar, cool→abrir si exterior más fresco / cerrar si más cálido); noche = sol bajo horizonte; rama `night_insulate` (cede a override/lluvia/privacidad). Autocontenido (no toca el free-cooling latente).

### F17 · Avisos meteo (tormenta/granizo) — ✅ implementada
- **Estado:** ☑ revisada · **Módulos:** DS · **Valor:** Media · **Esfuerzo:** M
- **Idea:** alerta meteo → cierre/protección preventiva (anticipa el granizo, no reacciona cuando ya cae).
- **Perfilado:**
  - **Fuente genérica, agnóstica de proveedor:** el usuario enchufa un `binary_sensor` de "alerta meteo" (de Open-Meteo/OWM/met.no/AEMET/template…). Motivo: AEMET es poco fiable ("se desconecta cada poco"); el usuario ya se monta sus fuentes REST con `availability`. **No atarse a un proveedor.**
  - **Tipos:** un disparo genérico "alerta → proteger" + **opcional** entradas separadas (p.ej. granizo/tormenta vs viento) con **posiciones de protección distintas**.
  - **Posición de protección configurable** (no siempre cerrar del todo; a veces media protege mejor las lamas).
  - **Hold configurable** tras levantarse la alerta (mantener protegido X min).
  - Complementa la protección por **viento/lluvia actuales** ya existentes (esto es la capa anticipatoria).
  - **Implementado:** 3 binary_sensor opcionales (genérico/granizo/viento) con posiciones distintas; gana la más protectora; rama `meteo_alert` (PROTECTED, tras override y antes de lluvia); hold configurable. El dato meteo lo provee el usuario (Meteoalarm/Open-Meteo/template) o F33 — sin APIs en la integración.

### F18 · Protección anti-helada
- **Estado:** ❄️ congelada · **Módulos:** DS · **Valor:** Baja · **Esfuerzo:** S
- **Idea:** no mover lamas con riesgo de hielo.
- **Perfilado:** _Congelada — marginal para el clima español y persianas enrollables. Reconsiderar para climas fríos / lamas exteriores (venecianas)._

### F19 · Apertura gradual al amanecer
- **Estado:** ☑ revisada · **Módulos:** DS · **Valor:** Baja · **Esfuerzo:** M
- **Idea:** subir la persiana poco a poco al amanecer (despertar natural).
- **Perfilado:**
  - **Opt-in por zona** (a unos les gusta en el dormitorio, a otros no; en su caso el **salón** por las mañanas).
  - **Rampa por pasos de % + duración entre pasos**, configurable por zona.
  - **Disparo por amanecer** (sol).
  - **Coordinación:** si la persiana **ya está abierta** (p.ej. free-cooling en verano), la rampa **no hace nada**; no pelea con el resto de lógica DS. Seguridad manda.
  - **Implementado:** switch "Gradual sunrise" (opt-in), rampa `dawn_step_pct`/`dawn_step_min`→`dawn_target_pct` disparada por elevación del sol; rama `dawn_ramp` en la cascada (cede a override/lluvia/privacidad), floor creciente (no cierra), respeta ya-abierta.

## DC (clima)

### F20 · Detección de ventana abierta
- **Estado:** ☑ revisada · **Módulos:** DC · **Valor:** Media · **Esfuerzo:** M
- **Idea:** pausar el clima si se abre una ventana (no calentar/enfriar a la calle).
- **Perfilado:**
  - **Sensor de ventana real primero:** mantener el `window_lockout` por `binary_sensor` (detección directa, sin cálculo) — opción preferente cuando existe.
  - **Inferencia por caída de temperatura** como **fallback/red extra** (con o sin sensor): derivada brusca **+ coherencia con la demanda** (cae mientras calientas / sube mientras enfrías = sospechoso) para evitar falsos positivos.
  - **Recuperación:** al estabilizarse/recuperar la temperatura **o** por timeout, lo que ocurra antes.
  - **Activable por zona**, sensibilidad configurable.
  - **Implementado:** sensor real (previo) + inferencia por temperatura **solo sin sensor** (caída coherente con la demanda), con confirm/release/timeout; OFF (`off_window_inferred`) + binary_sensor + evento. Por entrada DC.

### F21 · Programador semanal (consigna/velocidad) — ✅ implementada
- **Estado:** ✅ implementada · **Módulos:** DC + DV · **Valor:** Media · **Esfuerzo:** M
- **Idea:** consignas/velocidad por franja y día de la semana (equivalente a su "Programador Semanal").
- **Perfilado:**
  - **Editor/estética común** reutilizable por **DC** (consigna) y **DV** (velocidad/encendido), pero **perfil independiente por entrada** (no un perfil único compartido). **Fusiona F29.**
  - **Máximo 4 tramos por día**, por día de la semana.
  - **DC:** el perfil fija la **consigna BASE**; DC **modula encima** con sus biases (como su "Flujo de Consigna": Base → biases → TARGET). **Consigna absoluta**, no offset.
  - **DV:** el perfil fija velocidad/encendido base por tramo.
  - **Presencia prevista:** arquitectura preparada para que, más adelante, la **presencia** (away/home) ajuste sobre el "plan" del perfil. Dejar el hook.
  - **Implementado:** modelo puro `schedule.py` (4 tramos/día/día, valor activo con continuidad en medianoche); editor en opciones (menú de 7 días → tramos + copiar-a-días) por entrada; DC `scheduled_base` absoluto (biases encima, vacaciones ganan); DV velocidad base/suelo (0=off, 1/2/3 suelo, cede a silencio/modo); switch "Programador" (DV reusa el de horario; perfil vacío → on/off legacy); sensor "Programación". Hook de presencia (F32) diferido.

### F22 · Índice de moho
- **Estado:** ☑ revisada · **Módulos:** DC · **Valor:** Media · **Esfuerzo:** S
- **Idea:** riesgo de moho sostenido (no solo punto de rocío puntual) como alerta de salud.
- **Perfilado:**
  - **Aviso (sensor + alerta)** y **dispara secado (F13) solo si es efectivo** (gateado por `dp_diff`: no ventilar si el exterior no está más seco).
  - **Modelo simple y configurable:** "horas por encima de HR umbral con decaimiento" (no el VTT completo).
  - **Activable por zona** (baños/dormitorios sí, salón quizá no).
  - **Umbral de HR y ventana/decaimiento configurables.**
  - **Implementado:** índice (horas con decaimiento) + Repairs/evento + secado por bus (DV/`dp_diff`) **y** deshumidificador opcional. Por entrada DC.

### F23 · Confort ↔ economía (presets) — ✅ implementada
- **Estado:** ✅ implementada · **Módulos:** DC (y DV) · **Valor:** Media-Alta (UX) · **Esfuerzo:** M
- **Idea:** un único mando que escala la agresividad del sistema entre confort y ahorro.
- **Perfilado:**
  - **Con presets** (no slider continuo): p.ej. **Eco / Equilibrado / Confort** (más predecible).
  - **Mueve a la vez de forma coherente:** bandas/histéresis, atenuación nocturna, agresividad del lead y márgenes/límites.
  - **Global con override por zona** (como el modo F01).
  - **Ligado al modo F01:** el modo `Eco` puede fijar el preset de economía; también seleccionable de forma independiente.
  - **Implementado:** modelo puro `comfort.py` (resolución por ámbito calcando `modes.py` + deltas DC/DV integrados y predecibles); dos `select` en la entrada de Zonas (global + override por zona) publicados en el blob `DATA_MODE`; aplicado en `coordinator_*._cfg()` tras `apply_options`; enlace F01 (modo Eco → preset eco con el mando en neutro). `Equilibrado` = identidad. Deltas editables y efecto en DS diferidos.

## Fundacionales (emergentes de la revisión)

### F24 · Agrupación de zonas + presets por persona
- **Estado:** ☑ revisada · **Módulos:** núcleo/bus · **Valor:** Alta · **Esfuerzo:** L
- **Idea:** agrupar entidades en zonas lógicas y que cada ámbito tenga su modo/perfil propio. Prerrequisito de F01/F21/F23 "por grupos".
- **Perfilado:**
  - **Tres niveles: zona → grupo de zonas → casa** (p.ej. *Habitación principal → Habitaciones → Casa*; o *Habitación niños → Planta 1 → Chalet*).
  - **Configuración dedicada** para definir **zonas y grupos** (qué módulos pertenecen a cada zona, qué zonas forman cada grupo) — no solo un campo por módulo.
  - **Modo/perfil independiente por ámbito:** F01 (modo) y F21 (perfil) se aplican **por zona/grupo**, no solo global (p.ej. una habitación en "Sleep" sin afectar al resto). _(Esto es lo que se entendía por "presets por persona"; el "quién" lo gestiona HA con sus usuarios/dashboards.)_
  - **Zonas propias** (no reutilizar las Areas nativas de HA) para máximo control.
  - **Implementado (estructura):** entrada singleton "Dynamic Home · Zonas" con editor de árbol (options flow); modelo `zones.py` (zona→grupo, 1 módulo→1 zona, 1 zona→1 grupo, `scope_for_module`); árbol publicado en `hass.data[DATA_ZONES]` + sensor diagnóstico. **Modo/perfil por ámbito → F01** (consumirá esta estructura).

### F25 · Dynamic AC = emisor (no módulo aparte) + multi-emisor por zona
- **Estado:** ✅ implementada (v0.18.0) · **Módulos:** DC (+ F26) · **Valor:** Alta · **Esfuerzo:** L
- **Idea:** integrar AC sin crear un cerebro competidor; resolver zonas con varios emisores (radiante + AC).
- **Implementado (v0.18.0):** modelo puro `emitters.py` (lista 1..N por zona; cada emisor con su terna F26, dispositivo `climate` y/o `switch`, rol por modo, ámbito/owner/política); **Fase A** staging primario/apoyo `staging.py` (arma con lag sostenido, retira con histéresis) + dispatch multi-emisor en `coordinator_dc`/`climate.py` (legacy single-device intacto, REQ-EMI-7); **Fase B** `shared_emitter.py` + `SharedEmitterHub` (agregación ponderada default, guarda de undershoot, caso rejillas; dueño por declaración o fallback determinista). Editor de emisores en el options-flow. **Diferido:** canal de compresor por-emisor en F09; prioridad de cola/bypass de confort.
- **Perfilado:**
  - **AC = un *tipo de emisor*** de la zona (encaja en F26 "emisión"), **no un módulo/clon que compite**. Un solo cerebro DC por zona evita "dos cerebros peleando".
  - **Multi-emisor por zona con primario + apoyo (staging):** el primario lleva la consigna; el apoyo (p.ej. AC) entra cuando el primario **va por detrás** (desviación > umbral durante X tiempo) y se retira con histéresis.
  - **Primario seleccionable por zona y por modo** (típico: radiante primario en `heat`, AC primario/apoyo en `cool` —rápido y deshumidifica, útil para F13).
  - **Ámbito del emisor: zona / grupo / casa** (F24):
    - **Split** → emisor de **zona**.
    - **Conductos SIN zonificar** → emisor **compartido** de grupo/casa que sirve a varias zonas (sin control por habitación).
    - **Conductos ZONIFICADOS con rejillas motorizadas** → **fuente compartida + actuador por zona**: la **rejilla** hace de "válvula de aire" (análogo a la válvula de zona del radiante + panel que abre la general). DC abre/cierra la rejilla por zona; la unidad central corre con su consigna.
  - **Reconciliación del emisor compartido:**
    - *Sin zonificar:* una sola orden con **agregación ponderada** de la demanda (peso por zona). Políticas: **ponderada (default)** / peor parada / prioridad / media. La "peor parada" **no** es el default por el péndulo/undershoot que provoca en estancias pequeñas (un caudal no cortable por zona las sobre-acondiciona).
    - **Guarda de undershoot/overshoot:** la unidad corta/modula a la baja cuando la zona **más satisfecha** llega a su límite (`consigna ∓ shared_undershoot_margin`), aunque la peor parada no haya llegado. Acota el sobre-acondicionamiento de las habitaciones pequeñas. No aplica con rejillas.
    - **Parámetros del catálogo:** `zone_demand_weight` (por zona, default 1.0; derivable de volumen/masa) y `shared_undershoot_margin` (°C).
    - *Con rejillas:* control real por zona vía rejilla (como el radiante); la consigna de la unidad se fija eficiente / a la peor zona mientras las rejillas modulan el reparto.
  - **Casos:** solo AC → AC emisor único; solo radiante → como hoy; ambos → primario/apoyo.
  - Reutiliza todo el pipeline DC (consigna/biases/lead/anti-ciclado); el AC aporta lo suyo (dry nativo, fan, swing).

### F26 · Tipo de instalación / fuente de calor (config)
- **Estado:** 🟡 parcial (v0.16.0: declaración + defaults + flags; gating F09/F03 y F25 pendientes) · **Módulos:** DC (config) · **Valor:** Alta · **Esfuerzo:** M-L
- **Idea:** declarar la instalación (fuente + emisión) para activar/ocultar comportamientos y cargar presets. Base de F03, F09, F25.
- **Implementado (v0.16.0):** modelo de **3 dimensiones** `install.py` — **Generador** (aerotermia aire-agua, geotérmica, aire-aire/AC, calderas gas/gasoil/biomasa/leña, eléctrica directa) × **Distribución** (individual / central compartida; eléctrica y aire-aire siempre individuales) × **Emisión** (inercia). El central/individual es **dimensión aparte** del generador (gas/pellets/gasoil/aerotermia pueden ser centrales o individuales; la eléctrica siempre individual). Asistente de 3 pasos en el options-flow de clima (omite distribución si el generador es forzado individual), precarga **defaults por inercia** (lead/anti-ciclado, solo claves válidas de `options_spec`), expone un **perfil** (`community`/`compressor`/`peak`) vía `coordinator.install_profile` + sensor diagnóstico "Instalación". **Diferido (orden del usuario):** cablear F09 al perfil → F03 → F25 (emisores) → "personalizado".
- **Perfilado:**
  - **Asistente de instalación**, flujo: **Fuente → Sistema de emisión → evaluar características → mostrar/ocultar features + cargar presets** (defaults sensatos, editables luego en las opciones por categoría).
  - **Defaults + gating duro:** además de precargar valores, **oculta de verdad** lo que no aplica.
  - **Incluye la config de emisores de F25:** **primario + stage 2** (apoyo), su ámbito (zona/grupo/casa) y reconciliación.
  - **Dos dimensiones:** *Fuente* (aerotermia central compartida / aerotermia individual / radiante eléctrico / caldera gas / AC…) y *Emisión* (suelo radiante / radiadores / convectores / conductos en calor; radiante refrescante / fancoil / conductos-split en frío). La emisión define la **inercia**.
  - **Por zona** (radiante en salón, split en dormitorio…), **tratable global** si es una calefacción/AC sin zonificar.
  - **Catálogo cerrado:** cada combinación fuente+emisión se **valida** (tiene dependencias a configurar antes de producción); no vale "meter cualquier cosa" sin evaluarla. *(Quizá un "personalizado" muy avanzado, pero por defecto cerrado.)*
  - **Fuente comunitaria:** siempre circula fluido caliente/frío → **solo abrir la válvula** → **sin anti-ciclado (F09) ni anti-pico (F03)** (ambos OFF automáticamente).

### F27 · Señal de demanda/válvula real opcional (DC)
- **Estado:** ☑ revisada · **Módulos:** DC · **Valor:** Media-Alta · **Esfuerzo:** S
- **Idea:** entrada opcional por zona con la **demanda real** (no inferida de `t_int` vs `target`), que mejora la precisión del **Adaptive Lead** y da **horas de frío/calor exactas** (F06).
- **Perfilado:**
  - **Tres fuentes admitidas** (el usuario elige): (a) `hvac_action` del `climate` (heating/cooling/idle); (b) **helpers explícitos** de demanda frío/calor (como sus `Salón frío` / `Salón calor`); (c) **estado real del relé/potencia** (Shelly) — la más fiable.
  - **Por qué (c) es la mejor:** captura también la actuación del **termostato analógico de backup** (vía entrada SW del Shelly), que el `hvac_action` del climate **no ve**. Es la "verdad de campo" de si la válvula está abierta.
  - Si se aporta, el motor usa esta señal como `valve_open` en lugar de inferirla; si no, sigue infiriéndola (comportamiento actual).
  - **Coexistencia con backup hardware:** Dynamic Home controla por el relé normalmente, pero debe **convivir** con que el termostato analógico pueda actuar el relé por la entrada SW si cae la domótica (no pelearse; detectar el estado real).
  - **Implementado:** señal real c/b/a con *fallback* a inferencia + `binary_sensor` "Demanda real" (gated). Horas exactas pendientes de F06.

## Emergentes de dashboards (por perfilar)

### F28 · Eficiencia del recuperador (VMC)
- **Estado:** ☑ revisada · **Módulos:** DV · **Valor:** Media · **Esfuerzo:** S
- **Idea:** sensor de rendimiento del recuperador + inferencia de bypass.
- **Perfilado:**
  - **η = (T_insuflación − T_absorción_aire_nuevo) / (T_extracción_viciado − T_absorción_aire_nuevo)** — rendimiento de impulsión, **3 sondas** (la de **expulsión NO interviene**). Válida en ambos sentidos (recupera calor o frescor).
  - **Detección de bypass/fallo:** η cae a ~0 con ΔT significativo → recuperación no ocurre. Exponer estado **"recuperación activa / bypass"**; **avisar solo si el desplome es inesperado/sostenido** (no se distingue siempre bypass intencionado de suciedad/fallo solo con temperaturas → evitar falsas alarmas).
  - Entradas (3 sondas) opcionales; si faltan, no se expone.

### F29 · Programación por día (DV)
- **Estado:** ☑ revisada (fusionada en F21) · **Módulos:** DV · **Valor:** Media · **Esfuerzo:** S
- **Idea:** schedule por día de la semana (general + override por día).
- **Perfilado:** **Fusionada en F21** (programador semanal común DC+DV, 4 tramos/día, por día). Ver F21.

### F30 · IAQ extendido (más contaminantes)
- **Estado:** ☑ revisada · **Módulos:** DV · **Valor:** Media · **Esfuerzo:** M
- **Idea:** aceptar más contaminantes además de CO2/PM2.5.
- **Perfilado:**
  - **Actúan (suben velocidad): solo CO₂ y PM2.5** (como hoy).
  - **VOC (COV): informativo/observación** (no actúa).
  - **NOx:** descartado de momento (caso del usuario no tiene).
  - **Contaminantes exteriores** (CO/PM10/NO2/SO2/O3/índice): **solo observación**, y alimentan el **"exterior hostil"** para no ventilar en días muy malos.
  - **Implementado:** VOC observación (sensor diagnóstico, no actúa) + tests de contrato; el exterior hostil ya operaba sobre `CONF_AQI`. Exterior multi-contaminante y NOx **pendientes de F33**.

### F31 · Aviso/aprovechamiento de espacio adyacente (terraza/galería)
- **Estado:** ☑ revisada · **Módulos:** DC · **Valor:** Media · **Esfuerzo:** M
- **Idea:** usar la temperatura de un **espacio adyacente** (terraza acristalada, galería) con una **puerta** que comunica, para avisar/aprovechar.
- **Perfilado:** (advisory; requiere sensor de temperatura del espacio adyacente)
  - **En `heat`:** si el adyacente está mucho **más caliente** (p.ej. salón 20 °C, terraza al sol 50 °C) → **avisar para abrir la puerta** y calentar gratis (ganancia solar gratuita).
  - **En `cool`:** si el adyacente está mucho más caliente (interior 26 °C, terraza 50 °C) → **avisar/alarma si se abre la puerta** (no meter ese calor mientras enfrías).
  - Por defecto **advisory** (notificación/evento); actuación automática no aplica (no se puede abrir/cerrar una puerta), aunque podría sesgar decisiones vía bus.
  - Umbrales de ΔT configurables; por zona.
  - **Implementado:** advisory (evento `dynamic_home_adjacent` + sensor enum `open_gain`/`close_alarm`); heat→abrir (puerta cerrada), cool→alarma (puerta abierta). Umbrales ΔT por entrada DC. Sesgo por bus (REQ-ADY-4) diferido.

### F36 · Espejos de hardware para dashboards (HAL de salida)
- **Estado:** ☑ revisada · **Módulos:** transversal (DC/DV/DS) · **Valor:** Media · **Esfuerzo:** S-M
- **Idea:** la integración ya es el **mapa de hardware** para la lógica (el config entry mapea rol→`entity_id`; el motor nunca usa `entity_id` crudos — ver `SPEC_DV.md §2`). El hueco son los **dashboards/automatizaciones que apuntan al `entity_id` del sensor físico**, que se rompen al reemplazar hardware.
- **Solución elegida (opción 3):** que la integración **exponga sensores "espejo" estables por rol** (p.ej. `sensor.salon_temperatura_interior` que republica lo que apunte `CONF_DC_T_INT`). Los dashboards apuntan **siempre** a las entidades de la integración (`unique_id` por `(entry_id, rol)`, estables para siempre); **reemplazar un sensor = solo reconfigurar la entrada**, sin tocar dashboards ni código. Así los dashboards quedan auto-configurados.
- **Perfilado:**
  - **Solo entradas crudas** (t_int, t_ext, RH, viento, CO₂, PM2.5, potencia…); las **salidas** ya son estables (target, biases, etc.).
  - **Fidelidad:** el espejo copia `unit`/`device_class`/`state_class` por rol (historial y tarjetas se comportan igual que el original).
  - **Anti-bloat:** detrás de un toggle ("Exponer espejos de entrada", *off* por defecto).
  - **Apaño inmediato sin código:** al sustituir un sensor, reasignar al nuevo el mismo `entity_id` del viejo en el registro de entidades.
  - **Implementado:** `HwMirrorSensor` por rol de entrada numérico (DC/DV/DS), `unique_id` estable `(entry, rol)`, copia valor/unidad/device_class/state_class y sigue al origen; toggle `expose_mirrors` por entrada (off por defecto) con recarga al cambiar.

---

## Módulos futuros (candidatos de la "suite")
> De una lluvia de 15 iconos, estos son los que encajan con el ADN de Dynamic Home
> (coordinación por bus + control predictivo/adaptativo). El resto (Music, Robot,
> Unraid, Network, TV, Office) quedan fuera; Suite = el paraguas (= Dynamic Home).

### F32 · Dynamic Presence (enabler transversal)
- **Estado:** 🟡 parcial (v0.19.0: fusión PIR+mmWave+móvil+puerta + Durmiendo; BLE/identidad y puerta direccional diferidos) · **Módulos:** núcleo/zonas · **Valor:** Alta · **Esfuerzo:** L
- **Idea:** detección de presencia (away/home/sleep, por zona) que alimenta modos (F01), perfiles (F21), setback de DC/DV y coordinación con luces/persianas. Transversal, como las zonas (F24).
- **Implementado (v0.19.0):** vive en la entrada de Zonas; modelo puro `presence.py` (fusión por zona PIR/mmWave/puerta con timeouts por fuente + anti-flapping; casa `occupied`/`away`/`sleeping`); `ZonesCoordinator` con listeners+sondeo publica `DATA_PRESENCE` + evento, y **auto-pilota el modo de la casa** (opt-in, sin pisar Boost/Eco); binary_sensor de ocupación por zona + presencia de casa; editor en opciones; funciona con subconjuntos. **Diferido:** identidad BLE/Bermuda ("quién"), puerta direccional por orden de eventos, publicación por bus / setback directo por zona.
- **Perfilado:**
  - **Fusión de fuentes** (el valor real, no consumir un solo sensor): **PIR** (reacción rápida) + **mmWave** (presencia sostenida/quieto) + **BLE tipo Bermuda con beacons dedicados** (identidad + habitación, sin gastar batería del móvil) + **móvil GPS/WiFi** (Casa/Fuera).
  - **Estados:** por zona `Ocupada/Vacía`; global `Casa/Fuera/Durmiendo`. Anti-flapping (no marcar vacía por estar quieto).
  - **Máquina de ocupación direccional en la puerta:** combinar **contacto de puerta + movimiento interior por orden de eventos** (movimiento→puerta = salió; puerta→movimiento = entró) + BLE (quién queda/se va). Estado: Ocupada mientras haya presencia interior; Vacía cuando se apaga la última + hubo apertura reciente.
  - **Dormido:** franja horaria + sin movimiento, o zona "cama" del mmWave, o modo manual.
  - **Hardware recomendado (genérico):** PIR en zonas de paso; mmWave en estancias de estar/dormir; BLE (Bermuda + beacons) para identidad; móvil para casa/fuera.
  - **Salida:** publica estado por zona al bus; cada módulo decide (setback, persianas…). Opción de disparos directos configurables.

### F33 · Dynamic Weather (proveedor de datos)
- **Estado:** ☑ revisada · **Módulos:** núcleo · **Valor:** Alta · **Esfuerzo:** M
- **Idea:** capa meteo **resiliente y agnóstica** (Open-Meteo/OWM/…), con `availability`, que sirve forecast/alertas a DC (forecast bias), DS (F17 avisos) y free-cooling. Evita depender de integraciones inestables (AEMET).
- **Perfilado:**
  - **No depende de placas solares** (eso es F34/Energy): F33 da **forecast + alertas**, todo testable sin FV. Consumidores: **DC** (forecast bias), **DS** (F17 avisos), **free-cooling** (previsión para purga nocturna).
  - **Multi-fuente con fallback** (lo que motiva la feature): el problema real es que **AEMET se desconecta ~5 min de cada 4** → no atarse a un proveedor. Varias fuentes en cascada (p.ej. Open-Meteo libre como primaria + OWM/met.no/AEMET como respaldo); si la activa cae (sin `availability` o datos viejos), pasa a la siguiente.
  - **Configuración tipo `meteo_sources.yaml` compartido:** lista priorizada de fuentes (igual que el usuario ya se monta sus REST con `availability`). Reutilizable por todos los nodos/zonas para no duplicar lógica.
  - **Agnóstico (RNF-6):** el usuario puede **enchufar su propio `weather`/sensores** en vez de (o además de) las fuentes integradas. La feature **no obliga** a usar las integradas.
  - **Forecast** expuesto (temp, precip, viento, nubosidad…) consumible por DC y free-cooling; **alertas** genéricas consumibles por DS (F17, "alerta → proteger").
  - **lat/lon configurables**; **sin claves obligatorias** para la fuente libre, **clave opcional** para la de pago.
  - **Resiliencia/observabilidad:** exponer qué fuente está activa y desde cuándo (para depurar caídas); marcar `unavailable` solo si **todas** las fuentes fallan (degradación, RNF-7).
  - **Fuera de alcance F33:** nada de energía/FV (eso es F34).
  - **Implementado:** módulo `weather` (entidad `weather` proxy con fallback + reenvío de `get_forecasts`; `binary_sensor` de alerta derivada para F17; sensor de fuente activa). Fuentes: hasta 3 `weather.*` priorizadas + sensores crudos de respaldo; caducidad/umbral de alerta configurables. Forecast solo si la activa es `weather`. Sin APIs en la integración.

### F34 · Dynamic Energy (módulo)
- **Estado:** ☑ revisada · **Módulos:** nuevo (Energy) · **Valor:** Alta · **Esfuerzo:** L
- **Idea:** cerebro de energía: FV/batería/red/autoconsumo + **carga inteligente del VE** (garaje). Consolida F03 (anti-pico), F04 (precio), F06 (coste). Coordina a los grandes consumidores (DC/DV/AC) vía bus.
- **⚠️ Testabilidad:** el autor **no tiene placas solares** (probablemente tampoco batería/wallbox) → la parte **FV/batería/excedente/VE no es testable por el autor**: queda **pendiente de validación externa**. Sí testable por el autor: **anti-pico de red, coste/consumo, precio/tarifa** y la **mecánica del bus** con entradas simuladas.
- **Perfilado:**
  - **Es un MÓDULO** (cerebro de energía) al nivel de DC/DV/DS: coordinator propio + publica al bus. **No actúa directamente** sobre otros módulos; publica **contexto energético** y cada módulo decide (RNF-3 seguridad/autoridad, RNF-4 bus). Nada de "comandar" DC/DV.
  - **Agnóstico (RNF-6):** el usuario enchufa sus sensores (producción FV, SoC batería, import/export de red, consumo total). Funciona con **subconjuntos**: sin FV/batería → solo **red + precio + anti-pico**.
  - **Gating (F26-style):** componentes FV / batería / VE **ocultos** si no se aportan sus entidades.
  - **Consolida tres ideas previas:**
    - **F06 (coste/consumo):** Energy **agrega** lo que cada módulo ya expone (consumo total, coste total, balance casa). Reutiliza el panel de Energía de HA.
    - **F03 (anti-pico):** proteger el **ICP / potencia contratada** limitando el import; escalonar/recortar (shed) cargas. **Testable sin placas** (solo límite de red).
    - **F04 (precio):** tramos barato/normal/pico (PVPC/Nordpool o tarifa plana) → estado de tarifa al bus. **Testable con sensor de precio** sin placas. (F04 estaba congelada; Energy es su hogar natural.)
  - **Contexto energético publicado al bus** (lo que consumen DC/DV/AC/DS):
    - `surplus_w` — excedente FV disponible → permite **pre-acondicionar agresivo** (lead de DC, boost DV, carga VE) cuando sobra sol.
    - `import_headroom_w` — margen hasta el ICP → alimenta el anti-pico (F03).
    - `tariff_state` (barato/normal/pico) → desplazar cargas flexibles a horas baratas.
    - `scarcity` (caro + sin excedente) → aflojar la agresividad.
  - **Optimización de autoconsumo (advisory/sesgo, no comando):** desplazar cargas **flexibles** (pre-heat/cool de DC vía Adaptive Lead, boost DV, VE, ACS si la hay) a ventanas de excedente/baratas, **vía bus**; cada módulo sigue mandando sobre sí mismo y la seguridad prevalece.
  - **Carga inteligente del VE (garaje), opt-in:** cargar de **excedente FV** o en **horas baratas**, con **mínimo garantizado + deadline** ("salir con X% a las HH:MM"). Requiere **wallbox controlable**; oculto si no se aporta.
  - **Resiliencia (RNF-7):** si faltan fuentes clave, degrada a lo disponible (p.ej. sin medidor de red, no hay anti-pico por kW → cae a "N cargas").
  - **Encaje arquitectónico:** reutiliza el patrón motor puro (`energy_engine.py`) + coordinator + publisher de bus; el bus ya arbitra por prioridad/TTL.

### F35 · Campana extractora coordinada (cocina → DV)
- **Estado:** ☑ revisada · **Módulos:** DV · **Valor:** Media · **Esfuerzo:** S
- **Idea:** sinergia de cocina (no módulo aparte): cuando el **PM interior sube** (air fryer / cocinar) y la **campana extractora** (domotizada) está **apagada/baja**, **encenderla/subirla** para limpiar el aire. La campana = actuador extra de calidad de aire, complementario a la VMC.
- **Perfilado:**
  - Entrada: entidad de la campana (`fan`/`switch`) + nivel objetivo.
  - Disparo por **PM interior** (nivel y/o derivada, reusa F11) por encima de umbral; retira al normalizar (histéresis/hold).
  - Opcional: subir también la VMC en paralelo.
  - **Implementado:** entidad `fan` "Campana" (auto + manual) para **3 relés (uno por velocidad)**; auto por PM2.5 interior con histéresis (`hood_speed`); driver **break-before-make** + **vigilante de interlock** (corrige dos relés a la vez) + observe. Recomendado interlock hardware. _(Caso fan/switch simple queda para ampliar si se necesita.)_
| ID | Estado | Decisión resumida |
|----|--------|-------------------|
| **F01** | ✅ implementada (DS/horario→futuro) | Modos Home/Away/Sleep/Boost/Eco; casa + override por zona (F24); DV cap por modo, DC vacación en Away; select + caps configurables. Horario→F21, efecto DS pendiente. |
| **F02** | ✅ implementada | `BusSensor` por consumidor (DV/DS/DC) bajo el dispositivo central "Dynamic Home · Bus"; estado=ganador, atributos origen/prioridad/candidatos/motivo/target/TTL + aspirante (runner-up); evento `dynamic_home_conflict`; solo estado actual. |
| **F03** | ✅ implementada | Anti-pico opt-in: árbitro de casa `peak.py` (`PeakLoadHub`), canales separados clima/persianas; límite por N cargas o kW + escalonado (~10 s); clima gateado por `peak`/`community` del perfil F26; persianas escalonan arranques masivos. Prioridad de cola/bypass de confort (REQ-PIC-5) y presupuesto único de casa diferidos. |
| **F04** | ❄️ congelada | Precio luz → Adaptive Lead. Aparcada hasta madurar la idea. |
| **F05** | ❄️ congelada | Outdoor reset. Se solapa con `bias_exterior` en la instalación objetivo. |
| **F06** | ✅ implementada (energía) | Sensor de energía (kWh) en VMC/DC/DS: medidor real o estimación; panel de Energía. Coste (€) y pico instantáneo diferidos. |
| **F07** | ✅ implementada (botón→futuro) | Repairs transversal DV/DS/DC (mixin `DegradedTracker`): issue por módulo con fuentes requeridas ausentes/obsoletas >5min + evento `dynamic_home_degraded` + binary_sensor "Degradado". No-fixable + enlace; botón que reabre config flow diferido. |
| **F08** | ✅ implementada | Vida del filtro: número (3650 h) + sensor %, reset (botón/servicio), evento `filter_due` + **issue de Repairs `filter_due`** (creado al cruzar el umbral, borrado al resetear/descargar). |
| **F09** | ✅ implementada | Anti-ciclado opt-in: min ON/OFF + máx 6 arranques/h sobre el agregado del compresor compartido; vigila el ON/OFF que manda DC; la seguridad cede. **Gating F26 cableado (v0.17.0): solo con `compressor`, OFF en gas/eléctrico/comunitaria.** Grupos por compresor (F25) diferidos. |
| **F10** | ✅ implementada | 5 servicios (`reset_learning`/`boost`/`set_observe`/`reset_filter`/`recalibrate`) con `services.yaml` + traducciones EN/ES, destino por entidad/dispositivo/área; 4 eventos emitiéndose (degraded/conflict/filter_due/mode_changed). |
| **F11** | ☑ revisada | Ventilación anticipatoria por derivada CO₂/PM (patrón ducha: on/off + hold). |
| **F12** | ☑ revisada | Horas de silencio: nivel máx OFF/V1/V2 en franja (o vía Sleep F01); excepción crítica de seguridad. |
| **F13** | ☑ revisada | Secado por punto de rocío (dp_diff): mejora del dry_mode; margen + histéresis regulables. |
| **F14** | ☑ revisada | Boost V3 temporizado: duración configurable, vía servicio, re-disparo reinicia. |
| **F15** | ✅ implementada | Sombreado geométrico (switch opt-in): objetivo "X m de suelo"; +geometría (alféizar, profundidad); por pasos; fallback a % fijo. |
| **F16** | ✅ implementada | Aislamiento nocturno por modo del climate (heat=cerrar/aislar, cool=abrir/inercia); coordina con free-cooling; seguridad manda. |
| **F17** | ✅ implementada | Alerta meteo genérica + granizo/viento (binary_sensor que enchufa el usuario); posición protección + hold configurables; agnóstico de proveedor. |
| **F18** | ❄️ congelada | Anti-helada persianas. Marginal (clima español + enrollables). |
| **F19** | ✅ implementada | Amanecer gradual: opt-in por zona, rampa %/duración, disparo por sol; respeta si ya está abierta (free-cooling). |
| **F20** | ☑ revisada | Ventana abierta: sensor real primero + inferencia por caída temp (coherente con demanda); recuperación por estabilización/timeout. |
| **F31** | ☑ revisada | Aviso/aprovechamiento de espacio adyacente (terraza): heat→abrir gratis, cool→avisar si se abre. Advisory. |
| **F21** | ✅ implementada | Programador semanal (editor común, perfil por entrada; fusiona F29): 4 tramos/día por día; DC fija base absoluta (biases encima), DV velocidad/suelo; switch + sensor; presencia diferida. |
| **F22** | ☑ revisada | Índice de moho simple (horas sobre HR con decaimiento); aviso + secado si efectivo (dp_diff); por zona, configurable. |
| **F23** | ✅ implementada | Confort↔economía por presets (Eco/Equilibrado/Confort, deltas integrados); mueve bandas/atenuación/lead/umbrales; select global + override zona; ligado a F01. |
| **F24** | ✅ implementada | Tres niveles zona→grupo→casa; entrada singleton + editor de árbol; zonas propias (no Areas HA). Modo por ámbito ya lo aplica F01. |
| **F25** | ✅ implementada | Multi-emisor por zona (1..N, `climate` y/o `switch`) con **staging primario/apoyo** (`staging.py`) y **conductos compartidos** (`shared_emitter.py` + `SharedEmitterHub`: agregación ponderada + guarda de undershoot + rejillas). Editor de emisores en opciones; un solo cerebro por zona; legacy single-device intacto. Canal de compresor por-emisor diferido. |
| **F26** | 🟡 parcial | Capa de declaración (v0.16.0): asistente 3D **generador×distribución×emisión**, defaults por inercia y perfil `community`/`compressor`/`peak`. **Gating F09/F03 cableado al perfil (v0.17.0).** Emisores F25 y "personalizado" diferidos. |
| **F27** | ☑ revisada | Señal de demanda real opcional para DC (hvac_action/helpers/relé Shelly); convive con backup hardware. |
| **F31** | ☑ revisada | Aviso/aprovechamiento de espacio adyacente (terraza): heat→abrir gratis, cool→avisar. Advisory. |
| **F29** | ☑ fusionada | Programación por día → fusionada en F21. |
| **F28** | ☑ revisada | Eficiencia recuperador (3 sondas, sin expulsión) + inferencia bypass (aviso solo si desplome inesperado). |
| **F30** | ☑ revisada | IAQ extendido: actúan solo CO₂/PM2.5; VOC informativo; NOx descartado; exteriores observación + hostil. |
| **F33** | ✅ implementada | Weather agnóstico multi-fuente con fallback; entidad weather proxy (reenvía get_forecasts) + alerta derivada (F17) + fuente activa; weather.* + sensores crudos; sin FV (eso es F34). |
| **F34** | ☑ revisada | Módulo Energy: publica contexto al bus (surplus/headroom/tarifa/escasez), no comanda; agnóstico + gating; consolida F03/F04/F06; VE opt-in. ⚠️ Parte FV/batería/VE no testable por el autor (validación externa). |
| **F35** | ✅ implementada | Campana coordinada (PM interior → subir campana; 3 relés break-before-make + interlock; entidad fan auto+manual). |
| **F36** | ✅ implementada | Espejos de hardware (opción 3): sensores estables por rol para dashboards; reemplazar hardware = solo reconfigurar la entrada. Toggle `expose_mirrors` por zona. |
