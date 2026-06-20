# Dynamic Home — Backlog de ideas (exploración)

> Documento vivo. **No es compromiso de implementación.** Vamos revisando cada
> idea una a una; al cerrar la opinión se marca *Revisada* y se rellena
> *Perfilado*. Cuando estén perfiladas, se redactará un documento de requisitos
> y se implementarán en una fase posterior.

**Leyenda de estado:** ☐ pendiente · 🔄 en discusión · ☑ revisada (perfilada) · ❄️ congelada
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

### F02 · Explicador de conflictos del bus ⭐
- **Estado:** ☑ revisada · **Módulos:** DV·DS·DC · **Valor:** Alta · **Esfuerzo:** S
- **Idea:** sensor que expone "quién ganó y por qué" cuando hay intents en conflicto (p.ej. DC pide abrir por ganancia solar y DS quiere cerrar por viento).
- **Perfilado:**
  - **Una entidad por consumidor** del bus (cada VMC, cada persiana; y DC en su self-bias) — la que muestra qué intents le llegan y cuál gana sobre él.
  - **Agrupadas bajo un dispositivo nuevo central** "Dynamic Home · Bus" (no cuelgan de cada módulo). Implementación: device con identificador propio `(DOMAIN, "bus")`; el hub registra una entidad por consumidor.
  - **Contenido: ganador + motivo** (intent ganador como estado, motivo como atributo: prioridad/TTL). Sin la lista completa de descartados.
  - **Solo estado actual** del sensor; **sin** registro en logbook/historial de conflictos.
  - Encaje: el `SdhbHub` ya tiene `source/intent/target/priority/ttl`; basta añadir un `explain(targets)` que devuelva ganador + motivo.

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

### F06 · Sensor de coste/consumo/energía
- **Estado:** ☑ revisada · **Módulos:** DV·DS·DC · **Valor:** Media-Alta · **Esfuerzo:** M
- **Idea:** energía/coste por módulo, con medidor real si lo hay o estimación por horas si no.
- **Perfilado:**
  - **Potencia: medidor real preferente.** Si el módulo tiene un sensor de potencia (Shelly) → se usa ese. Si no, **estimación** por potencia configurable por estado/velocidad.
  - **Energía (kWh)** como sensor `device_class: energy`, `state_class: total_increasing` → **entra en el panel de Energía de HA**.
  - **Coste (€) opcional:** vía **sensor de precio** (tarifa plana que el usuario mete, o integración externa para variable) o un precio fijo configurable.
  - **Módulos:** VMC y Persianas (suelen tener Shelly). **DC opcional** y ligado a **F26**: en aerotermia comunitaria no aporta; en eléctrico/AC sí, si hay medidor. (El usuario ya calcula horas de frío/calor por el helper del climate; portarlo es interesante para él, opcional para otros.)
  - **Potencia instantánea / pico:** exponer la potencia total instantánea. **Cruza con F03**: aunque las persianas consumen poco, su **pico de arranque** importa (12 persianas bajando a la vez ≈ 2000 W → puede saltar el ICP), así que el anti-pico debe considerar también DS.

## Robustez y mantenimiento

### F07 · HA Repairs sobre `degraded` ⭐
- **Estado:** ☑ revisada · **Módulos:** DV·DS·DC · **Valor:** Alta · **Esfuerzo:** S
- **Idea:** cuando un sensor configurado desaparece o lleva obsoleto, emitir un *issue* accionable en Ajustes→Reparaciones (se apoya en el `binary_sensor degraded` ya existente).
- **Perfilado:**
  - **Disparo:** entidad **ausente/renombrada** Y **obsoleta** (`unavailable`/`unknown` > X min, p.ej. 5 min) — igual que su YAML actual.
  - **Solo fuentes requeridas** (las opcionales se ignoran).
  - **Acción del botón:** **reabrir el config flow** del módulo para corregir el mapeo.
  - **Un issue por módulo**, listando las fuentes que faltan (como su Telegram "DV HW MAP / SENSORES REQUERIDOS KO ... Missing (2): ...").
  - **Extra opcional:** emitir además un **evento** (`dynamic_home_degraded`) para que quien quiera lo enrute a Telegram/notify (como hace hoy). Lo nativo es el *issue* de Reparaciones; el evento es para power-users.
  - Se borra el issue al recuperarse la fuente (`async_delete_issue`).

### F08 · Vida del filtro VMC
- **Estado:** ☑ revisada · **Módulos:** DV · **Valor:** Media · **Esfuerzo:** S
- **Idea:** % de vida del filtro + recordatorio al umbral, sobre `filter_hours` ya contabilizadas.
- **Perfilado:** (réplica nativa de su sección "7) Filtros")
  - **Intervalo configurable** `number` "Vida del filtro (h)", default **3650 h** (su valor de fábrica). Horas **totales simples** (no ponderadas por velocidad; ponderación queda como posible mejora futura).
  - **Sensor "% de vida del filtro"** = 100·(1 − filter_hours/intervalo). Reset = el **botón existente** (mecanismo offset, como su `dv_filtros_horas_offset`).
  - **Umbral único** (al 100% del intervalo). Pre-aviso al 90% queda opcional.
  - **Aviso:** issue de **Repairs** (sistema de F07) + opción de notificación persistente / evento para Telegram (como sus toggles "Notificaciones persistentes / Telegram").
  - Fecha/contador de último cambio: opcional, no por defecto.

### F09 · Anti-ciclado corto (DC)
- **Estado:** ☐ · **Módulos:** DC · **Valor:** Media · **Esfuerzo:** M
- **Idea:** tiempos mínimos ON/OFF para proteger compresores; el aprendizaje ya mide la tasa, así que hay datos.
- **Perfilado:** _(pendiente)_

### F10 · Servicios y eventos nativos
- **Estado:** ☐ · **Módulos:** DV·DS·DC · **Valor:** Media · **Esfuerzo:** S
- **Idea:** `dynamic_home.reset_learning`, `force_observe`, `recalibrate`… + eventos para automatizaciones.
- **Perfilado:** _(pendiente)_

## DV (ventilación)

### F11 · Ventilación anticipatoria (derivada CO₂/PM)
- **Estado:** ☐ · **Módulos:** DV · **Valor:** Media · **Esfuerzo:** M
- **Idea:** pre-ventilar cuando CO₂/PM suben rápido (ya hay EMAs; falta la derivada), análogo al lead de DC.
- **Perfilado:** _(pendiente)_

### F12 · Horas de silencio (cap nocturno)
- **Estado:** ☐ · **Módulos:** DV · **Valor:** Media · **Esfuerzo:** S
- **Idea:** capar a V1/V2 en franja de sueño por ruido (distinto del schedule de encendido).
- **Perfilado:** _(pendiente)_

### F13 · Intercambio por humedad absoluta ⭐
- **Estado:** ☐ · **Módulos:** DV · **Valor:** Alta · **Esfuerzo:** M
- **Idea:** ventilar para secar **solo si el aire exterior es más seco** (comparar puntos de rocío absolutos), no por HR relativa.
- **Perfilado:** _(pendiente)_

### F14 · Botón Boost de un toque
- **Estado:** ☐ · **Módulos:** DV · **Valor:** Baja · **Esfuerzo:** S
- **Idea:** botón que fuerza V3 N minutos con auto-reversión (reutiliza el timer de override).
- **Perfilado:** _(pendiente)_

## DS (persianas)

### F15 · Sombreado geométrico real ⭐
- **Estado:** ☐ · **Módulos:** DS · **Valor:** Alta · **Esfuerzo:** L
- **Idea:** calcular la penetración solar por geometría (azimut, span, alto, voladizo — ya son campos) y cerrar solo lo necesario, no todo/nada.
- **Perfilado:** _(pendiente)_

### F16 · Aislamiento nocturno estacional
- **Estado:** ☐ · **Módulos:** DS · **Valor:** Media · **Esfuerzo:** S
- **Idea:** cerrar en noche de invierno (aislar) / abrir en noche de verano (refrescar); ampliar `winter_night_pct`.
- **Perfilado:** _(pendiente)_

### F17 · Avisos meteo (tormenta/granizo)
- **Estado:** ☐ · **Módulos:** DS · **Valor:** Media · **Esfuerzo:** M
- **Idea:** integrar alertas (met.no/AEMET) → cierre preventivo.
- **Perfilado:** _(pendiente)_

### F18 · Protección anti-helada
- **Estado:** ☐ · **Módulos:** DS · **Valor:** Baja · **Esfuerzo:** S
- **Idea:** no mover lamas con riesgo de hielo.
- **Perfilado:** _(pendiente)_

### F19 · Apertura gradual al amanecer
- **Estado:** ☐ · **Módulos:** DS · **Valor:** Baja · **Esfuerzo:** M
- **Idea:** simulación de salida del sol, opcionalmente ligada a una alarma.
- **Perfilado:** _(pendiente)_

## DC (clima)

### F20 · Detección de ventana por caída de temperatura
- **Estado:** ☐ · **Módulos:** DC · **Valor:** Media · **Esfuerzo:** M
- **Idea:** lockout por derivada brusca de temperatura cuando no hay sensor de ventana.
- **Perfilado:** _(pendiente)_

### F21 · Perfiles horarios de consigna
- **Estado:** ☐ · **Módulos:** DC · **Valor:** Media · **Esfuerzo:** M
- **Idea:** consignas por franja (laborable/finde), como el schedule de DV.
- **Perfilado:** _(pendiente)_

### F22 · Índice de moho
- **Estado:** ☐ · **Módulos:** DC · **Valor:** Media · **Esfuerzo:** S
- **Idea:** riesgo de moho sostenido (no solo punto de rocío puntual) como alerta de salud.
- **Perfilado:** _(pendiente)_

### F23 · Slider confort ↔ economía
- **Estado:** ☐ · **Módulos:** DC · **Valor:** Media · **Esfuerzo:** M
- **Idea:** un único mando que escala la agresividad de los biases.
- **Perfilado:** _(pendiente)_

## Fundacionales (emergentes de la revisión)

### F24 · Agrupación de zonas + presets por persona
- **Estado:** ☐ · **Módulos:** núcleo/bus · **Valor:** Alta · **Esfuerzo:** L
- **Idea:** agrupar entidades en zonas lógicas (`salón-cocina`, `habitaciones`, `baños`) y que cada persona gestione su grupo con su preset/modo. Es prerrequisito de F01 por grupos.
- **Perfilado:** _(pendiente — afecta a la arquitectura; revisar antes que features que dependan de zonas)_

### F25 · Módulo Dynamic AC (aire acondicionado)
- **Estado:** ☐ · **Módulos:** nuevo (AC) · **Valor:** Alta · **Esfuerzo:** L
- **Idea:** nuevo tipo de módulo para aire acondicionado, integrado en el bus y reactivo al modo global (F01). Validar que la arquitectura de coordinators/engines lo soporta sin fricción.
- **Perfilado:** _(pendiente)_

### F26 · Tipo de instalación / fuente de calor (config)
- **Estado:** ☐ · **Módulos:** DC (config) · **Valor:** Alta · **Esfuerzo:** M
- **Idea:** declarar por zona/sistema el tipo de instalación: aerotermia central compartida, aerotermia individual, radiante eléctrico, caldera de gas, etc. Es **prerrequisito de F03** (anti-pico solo en eléctricas) y condiciona otras (p.ej. F09 anti-ciclado, que aplica a compresores/aerotermia). Permite activar/ocultar comportamientos específicos según la instalación.
- **Perfilado:** _(pendiente — emergente de F03; revisar pronto)_

### F27 · Señal de demanda/válvula real opcional (DC)
- **Estado:** ☑ revisada · **Módulos:** DC · **Valor:** Media-Alta · **Esfuerzo:** S
- **Idea:** entrada opcional por zona con la **demanda real** (no inferida de `t_int` vs `target`), que mejora la precisión del **Adaptive Lead** y da **horas de frío/calor exactas** (F06).
- **Perfilado:**
  - **Tres fuentes admitidas** (el usuario elige): (a) `hvac_action` del `climate` (heating/cooling/idle); (b) **helpers explícitos** de demanda frío/calor (como sus `Salón frío` / `Salón calor`); (c) **estado real del relé/potencia** (Shelly) — la más fiable.
  - **Por qué (c) es la mejor:** captura también la actuación del **termostato analógico de backup** (vía entrada SW del Shelly), que el `hvac_action` del climate **no ve**. Es la "verdad de campo" de si la válvula está abierta.
  - Si se aporta, el motor usa esta señal como `valve_open` en lugar de inferirla; si no, sigue infiriéndola (comportamiento actual).
  - **Coexistencia con backup hardware:** Dynamic Home controla por el relé normalmente, pero debe **convivir** con que el termostato analógico pueda actuar el relé por la entrada SW si cae la domótica (no pelearse; detectar el estado real).

---

## Registro de revisión
| ID | Estado | Decisión resumida |
|----|--------|-------------------|
| **F01** | ☑ revisada | Modos base configurables; vive en el bus (sustituye vacaciones DC); por grupos (F24); extensible a AC (F25). Jerarquía: override > horario > manual > modo. |
| **F02** | ☑ revisada | Una entidad por consumidor bajo un dispositivo "Bus" nuevo; ganador + motivo; solo estado actual. |
| **F03** | ☑ revisada | Depende del tipo de instalación (F26); solo eléctricas; límite por amperios/kW o N zonas; escalonado temporal (~10 s). |
| **F04** | ❄️ congelada | Precio luz → Adaptive Lead. Aparcada hasta madurar la idea. |
| **F05** | ❄️ congelada | Outdoor reset. Se solapa con `bias_exterior` en la instalación objetivo. |
| **F06** | ☑ revisada | Energía/coste: medidor real (Shelly) o estimación; panel de Energía; precio opcional; pico instantáneo (cruza F03, incl. persianas). |
| **F07** | ☑ revisada | Repairs por módulo (ausente + obsoleto >5min, solo requeridos); botón reabre config flow; + evento opcional para Telegram. |
| **F08** | ☑ revisada | Vida del filtro: intervalo configurable (3650 h), sensor % , reset existente, aviso por Repairs/notif. |
| F09–F23 | ☐ | Pendientes de revisar |
| F24, F25, F26 | ☐ | Fundacionales emergentes; revisar pronto |
| **F27** | ☑ revisada | Señal de demanda real opcional para DC (hvac_action / helpers / relé Shelly); mejora Adaptive Lead y horas F06; convive con backup hardware. |
