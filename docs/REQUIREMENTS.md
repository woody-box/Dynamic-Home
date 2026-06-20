# Dynamic Home — Documento de Requisitos

> Derivado de `docs/BACKLOG.md` (ideas F01–F35, perfiladas con el usuario).
> **Versión 2 — Fases 0 (fundacionales) y 1 (transversales + DC) en detalle**;
> el resto, en el roadmap (§3) para expandir fase a fase. Prioridad por MoSCoW:
> **M** (Must) · **S** (Should) · **C** (Could). Cada requisito debe ser verificable.

Estado actual del producto: v0.5.0 publicada en HACS (DV/DS/DC + bus SDHB en
memoria, observabilidad 1:1, modo observación, config por UI por categoría).

---

## 1. Visión y alcance

Dynamic Home es un **BMS doméstico para Home Assistant**: tres módulos (DC clima,
DV ventilación, DS persianas — y futuros AC/Energy) **coordinados por un bus**
interno (SDHB), con control **predictivo/adaptativo** del confort, el aire, el
sombreado y la energía. El diferenciador frente a HA "a secas" es la
**coordinación entre módulos** y la **anticipación** (no solo reaccionar).

**Dentro de alcance:** confort térmico, calidad de aire, sombreado solar,
energía, presencia como entrada transversal.
**Fuera de alcance:** media (TV/Music), IT (Unraid/Network), robótica, ofimática.

---

## 2. Requisitos no funcionales (principios de diseño) — RNF

- **RNF-1 · Nada hardcodeado.** Los valores por defecto viven **solo** en los
  dataclasses del motor (`*_engine.py`); todo parámetro es **configurable por UI**
  (options por categoría). Tests garantizan que el catálogo no tiene campos fantasma.
- **RNF-2 · Modo observación (dry-run).** Cada módulo puede **calcular y publicar
  sin actuar** sobre hardware. Imprescindible para validar antes de dar control.
- **RNF-3 · Seguridad primero.** Jerarquía de autoridad: **override manual > horario
  > manual > modo**. Las protecciones (condensación, viento/granizo, ventana,
  límites) **prevalecen** sobre cualquier optimización.
- **RNF-4 · Coordinación por bus (SDHB).** Arbitraje por **prioridad + TTL**; los
  módulos publican intenciones y consumen las dirigidas a ellos. Observabilidad del
  arbitraje (F02).
- **RNF-5 · HA-native.** Config flow + entidades nativas + options flow por
  categoría + **Repairs** + servicios/eventos + traducciones **EN/ES**.
- **RNF-6 · Agnóstico de proveedor.** Las entradas se aportan como **entidades**
  (sensor/binary_sensor/climate/cover…) que el usuario enchufa; **no** atarse a
  integraciones concretas (p.ej. meteo) por su (in)fiabilidad.
- **RNF-7 · Resiliencia y degradación.** `binary_sensor degraded` + Repairs cuando
  falta una fuente requerida; failsafe; estado **restaurado** entre reinicios.
- **RNF-8 · Testeable.** Lógica pura en `*_engine.py` sin dependencias de HA; CI
  con **lint (ruff) + hassfest + HACS**; suite verde y sin flaky.
- **RNF-9 · Local y privado.** `local_polling`, sin nube; datos del usuario no se
  versionan en el repo.
- **RNF-10 · Multi-instancia y por zona.** Varias zonas/módulos coexisten y se
  agrupan (F24); comportamientos activables/ocultables según la instalación (F26).

---

## 3. Roadmap por fases

**Fase 0 — Fundacionales** (desbloquean el resto, detalladas en §4):
F24 Zonas/grupos · F26 Tipo de instalación · F25 Emisores y staging ·
F32 Presencia · F33 Weather. (Apoyo: F02 explicador del bus.)

| Fase | Contenido | Features |
|------|-----------|----------|
| **0** | Fundacionales / enablers | F24, F26, F25, F32, F33, F02 |
| **1** | Transversales + DC avanzado | F01 modos, F07 Repairs, F10 servicios/eventos, F06 energía, F27 demanda real, F09 anti-ciclado, F03 anti-pico, F20 ventana, F21 programador, F22 moho, F23 confort/eco, F31 terraza |
| **2** | DV (ventilación) | F11 anticipatoria, F12 silencio, F13 secado rocío, F14 boost, F28 eficiencia, F30 IAQ extendido, F35 campana |
| **3** | DS (persianas) | F15 sombreado geométrico, F16 aislamiento nocturno, F17 avisos meteo, F19 amanecer |
| **4** | Módulo nuevo | F34 Dynamic Energy (+ VE) |
| **❄️** | Congeladas / fuera | F04 precio, F05 outdoor reset, F18 anti-helada |

> El detalle de Fases 2–4 se redactará al entrar cada fase, partiendo del
> perfilado ya cerrado en `docs/BACKLOG.md`.

---

## 4. Fase 0 — Fundacionales (detalle)

### 4.1 · Zonas y grupos (F24)

**Objetivo:** organizar módulos/entidades en una jerarquía **zona → grupo de
zonas → casa** para aplicar modo/perfil/avisos por ámbito.

- **REQ-ZON-1 (M):** el sistema soporta 3 niveles: **zona**, **grupo de zonas**,
  **casa**.
- **REQ-ZON-2 (M):** existe una **configuración dedicada** para definir zonas y
  grupos y asignar qué módulos pertenecen a cada zona y qué zonas a cada grupo.
- **REQ-ZON-3 (M):** las zonas son **propias** de Dynamic Home (no se reutilizan
  las Areas de HA).
- **REQ-ZON-4 (S):** modo (F01) y perfil (F21) son **aplicables por ámbito**
  (zona/grupo/casa), no solo global.
- **REQ-ZON-5 (S):** un módulo pertenece como máximo a una zona; una zona a un
  grupo; validado en config.

**Dependencias:** ninguna (base). **Habilita:** F01, F21, F23, F25(ámbito), F32.
**Criterios de aceptación:**
- ☐ Puedo crear zonas y grupos y asignar módulos desde la UI.
- ☐ Un cambio de modo en una zona no afecta a otras.
- ☐ La jerarquía se persiste y sobrevive a reinicios.

### 4.2 · Tipo de instalación (F26)

**Objetivo:** declarar la instalación (**fuente** + **sistema de emisión**) para
**precargar defaults** y **mostrar/ocultar** comportamientos según apliquen.

- **REQ-INS-1 (M):** asistente con flujo **Fuente → Emisión → (evaluar) → cargar
  presets + gating**.
- **REQ-INS-2 (M):** **Fuente** (catálogo cerrado): aerotermia central compartida,
  aerotermia individual, radiante eléctrico, caldera de gas, AC.
- **REQ-INS-3 (M):** **Emisión** (catálogo cerrado): suelo radiante, radiadores,
  convectores, conductos (calor); radiante refrescante, fancoil, conductos/split
  (frío). Determina la **inercia** (afecta lead/freno/anti-ciclado).
- **REQ-INS-4 (M):** **gating duro** — oculta comportamientos no aplicables
  (no solo precarga valores).
- **REQ-INS-5 (M):** **fuente comunitaria** ⇒ **anti-ciclado (F09) y anti-pico
  (F03) DESACTIVADOS** automáticamente (fluido siempre disponible, solo se abre
  válvula).
- **REQ-INS-6 (S):** configurable **por zona**; tratable **global** si la
  instalación no está zonificada.
- **REQ-INS-7 (C):** opción "personalizado" avanzada fuera del catálogo cerrado.

**Dependencias:** F24 (ámbito). **Habilita:** F03, F09, F25, defaults de DC.
**Criterios de aceptación:**
- ☐ Al elegir fuente+emisión se precargan defaults coherentes (editables luego).
- ☐ Con fuente comunitaria, F03/F09 no aparecen ni actúan.
- ☐ La inercia elegida cambia los defaults de lead/freno.

### 4.3 · Emisores y staging (F25)

**Objetivo:** una zona puede tener **varios emisores** (p.ej. radiante + AC) con
**primario + apoyo**, sin "dos cerebros peleando". AC = **tipo de emisor**, no
módulo aparte.

- **REQ-EMI-1 (M):** una zona tiene **1..N emisores**; el **cerebro DC** es único
  por zona y conduce a todos.
- **REQ-EMI-2 (M):** **staging primario + apoyo**: el primario lleva la consigna;
  el apoyo entra cuando el primario **va por detrás** (desviación > umbral durante
  T) y se retira con **histéresis**.
- **REQ-EMI-3 (M):** **primario configurable por zona y por modo** (típico:
  radiante en `heat`, AC en `cool`).
- **REQ-EMI-4 (M):** **ámbito del emisor**: **zona** (split), **grupo/casa**
  (conductos sin zonificar), **grupo/casa con actuador por zona** (conductos +
  **rejillas motorizadas** = "válvula de aire").
- **REQ-EMI-5 (M):** **reconciliación del emisor compartido sin zonificar**: una
  sola orden con política configurable (**zona peor parada** / prioridad / media);
  por defecto la peor parada en el sentido activo.
- **REQ-EMI-6 (S):** el AC aporta sus capacidades propias (dry nativo → usable por
  F13, fan, swing).
- **REQ-EMI-7 (M):** casos límite — solo AC ⇒ AC emisor único; solo radiante ⇒
  comportamiento actual.

**Dependencias:** F24, F26. **Habilita:** módulo AC, F13 (dry nativo).
**Criterios de aceptación:**
- ☐ Con radiante+AC, el apoyo arranca solo cuando el primario no llega y se retira al recuperar.
- ☐ Conductos sin zonificar: una sola orden coherente para todas las zonas del ámbito.
- ☐ Conductos con rejillas: control por zona vía rejilla, unidad con consigna única.

### 4.4 · Presencia (F32)

**Objetivo:** estado de presencia **robusto por zona** (y casa) que alimenta
modos, perfiles y setback. **Fusiona** fuentes; no depende de un solo sensor.

- **REQ-PRE-1 (M):** **fusión** de fuentes por zona: PIR (rápido), mmWave
  (sostenido/quieto), BLE/Bermuda (identidad+habitación), móvil (Casa/Fuera).
- **REQ-PRE-2 (M):** estados por zona `Ocupada/Vacía`; global `Casa/Fuera/Durmiendo`.
- **REQ-PRE-3 (M):** **anti-flapping** — no marcar `Vacía` por inmovilidad mientras
  un mmWave detecte presencia (timeouts por fuente).
- **REQ-PRE-4 (S):** **ocupación direccional en la puerta** — contacto de puerta +
  movimiento interior por **orden de eventos** (movimiento→puerta = salida;
  puerta→movimiento = entrada); BLE desambigua **quién**.
- **REQ-PRE-5 (M):** máquina de estado de casa: `Ocupada` mientras haya presencia
  interior; `Vacía` cuando se apaga la última + hubo apertura de puerta reciente.
- **REQ-PRE-6 (S):** detección de `Durmiendo` por franja + sin movimiento / zona
  "cama" del mmWave / modo manual.
- **REQ-PRE-7 (M):** **publica el estado al bus**; cada módulo decide (setback,
  persianas…). Disparos directos opcionales y configurables.
- **REQ-PRE-8 (M):** las fuentes son **entidades aportadas por el usuario** (RNF-6);
  funciona con subconjuntos (solo PIR, solo mmWave…).

**Dependencias:** F24 (zonas), bus. **Habilita:** F01 (away/home/sleep), F21, setback DC/DV.
**Criterios de aceptación:**
- ☐ Estar quieto en el sofá NO marca la zona como vacía.
- ☐ Salir de casa (con la última zona vaciándose + puerta) pasa la casa a `Fuera`.
- ☐ Con beacons BLE, el estado distingue **quién** está y en qué zona.

### 4.5 · Weather (F33)

**Objetivo:** capa meteo **resiliente y agnóstica** que provee forecast/alertas al
resto, sin depender de integraciones inestables.

- **REQ-WEA-1 (M):** agrega **múltiples fuentes** (p.ej. Open-Meteo, OpenWeather)
  con **disponibilidad/fallback** (si una cae, usa otra).
- **REQ-WEA-2 (M):** expone **forecast** (temp, precip, viento, etc.) consumible por
  DC (forecast bias) y por free-cooling.
- **REQ-WEA-3 (M):** expone **alertas** (genéricas) consumibles por DS (F17).
- **REQ-WEA-4 (S):** lat/lon configurables; sin claves obligatorias para la fuente
  libre; clave opcional para la de pago.
- **REQ-WEA-5 (M):** agnóstico (RNF-6): el usuario también puede enchufar su propio
  `weather`/sensores en vez de usar las fuentes integradas.

**Dependencias:** ninguna. **Habilita:** forecast DC, F17 avisos, free-cooling.
**Criterios de aceptación:**
- ☐ Si la fuente primaria no responde, el forecast sigue disponible por la secundaria.
- ☐ DC recibe forecast y DS recibe alertas sin configurar una integración meteo concreta.

---

## 5. Fase 1 — Transversales + DC avanzado (detalle)

Construye sobre la Fase 0 (zonas, instalación, presencia). Agrupa: control de
alto nivel (modos, presets de confort, programador), robustez operativa
(Repairs, servicios/eventos), energía (coste, anti-pico) y la inteligencia
avanzada de DC (demanda real, anti-ciclado, ventana, moho, espacio adyacente).

### 5.1 · Modos de la casa (F01)

**Objetivo:** un "modo" (`Home/Away/Sleep/Boost/Eco`) que vive en el **bus** y
sesga todos los módulos a la vez, por ámbito (zona/grupo/casa).

- **REQ-MOD-1 (M):** modos base `Home/Away/Sleep/Boost/Eco`, con **comportamiento
  por modo configurable** (no hardcodeado): mínimo, cap de velocidad VMC por modo;
  ideal, un perfil por módulo y modo.
- **REQ-MOD-2 (M):** el modo **vive en el bus**, independiente de DC; el modo
  `Away`/vacaciones **sustituye** al toggle `vacation` de DC y existe aunque DC no
  esté instalado.
- **REQ-MOD-3 (M):** modo **aplicable por ámbito** (casa global + override por
  zona/grupo), apoyado en F24.
- **REQ-MOD-4 (M):** **jerarquía de autoridad** (de más a menos): override manual
  temporizado > horario (F21) > preset manual normal > modo. Un preset manual
  normal **no** se salta el horario; solo el override manual sí.
- **REQ-MOD-5 (S):** **extensible** — un módulo futuro (AC, F25) solo lee el modo
  del bus para adherirse. Emite evento `dynamic_home_mode_changed` (F10).

**Dependencias:** F24 (ámbito), bus, F32 (away/home/sleep automáticos).
**Habilita:** F23 (Eco fija preset), F12/F16 (Sleep aplica caps).
**Criterios de aceptación:**
- ☐ Cambiar a `Sleep` baja la VMC al cap configurado por ruido (WAF).
- ☐ `Away` del bus apaga/atenúa sin necesidad del toggle de DC.
- ☐ El override manual temporizado prevalece sobre el horario; al expirar, vuelve al plan.

### 5.2 · Confort ↔ economía (F23)

**Objetivo:** un único mando por **presets** (`Eco / Equilibrado / Confort`) que
escala de forma coherente la agresividad del sistema.

- **REQ-CMF-1 (M):** **presets** discretos (no slider): `Eco / Equilibrado /
  Confort`, predecibles.
- **REQ-CMF-2 (M):** cada preset mueve **a la vez y de forma coherente**:
  bandas/histéresis, atenuación nocturna, agresividad del lead y márgenes/límites.
- **REQ-CMF-3 (S):** **global con override por zona** (como el modo).
- **REQ-CMF-4 (S):** **ligado a F01**: el modo `Eco` puede fijar el preset
  económico; también seleccionable de forma independiente.

**Dependencias:** F01, F24, F26 (defaults por instalación).
**Criterios de aceptación:**
- ☐ Pasar a `Eco` ensancha bandas y reduce la agresividad del lead de forma observable.
- ☐ Una zona puede mantener `Confort` mientras el resto está en `Eco`.

### 5.3 · Programador semanal (F21, fusiona F29)

**Objetivo:** un **programador semanal común** reutilizable por DC (consigna) y
DV (velocidad/encendido), con presencia prevista como hook.

- **REQ-SCH-1 (M):** un único "Programador Semanal" compartido por **DC y DV**.
- **REQ-SCH-2 (M):** hasta **4 tramos por día**, por día de la semana.
- **REQ-SCH-3 (M):** **DC** — el perfil fija la **consigna BASE absoluta** (no
  offset); DC **modula encima** con sus biases (Base → biases → TARGET).
- **REQ-SCH-4 (M):** **DV** — el perfil fija velocidad/encendido base por tramo.
- **REQ-SCH-5 (S):** **hook de presencia** — arquitectura preparada para que la
  presencia (F32, away/home) ajuste sobre el plan del perfil más adelante.

**Dependencias:** F24 (por ámbito), F01 (jerarquía: el horario gana al manual).
**Criterios de aceptación:**
- ☐ Un cambio de tramo modifica la consigna base de DC; los biases siguen aplicando encima.
- ☐ El horario apaga la VMC a la hora configurada salvo override manual.

### 5.4 · Repairs sobre `degraded` (F07)

**Objetivo:** convertir el estado `degraded` en *issues* accionables de
Ajustes → Reparaciones cuando falta una fuente **requerida**.

- **REQ-REP-1 (M):** **disparo** cuando una entidad requerida está **ausente/
  renombrada** Y **obsoleta** (`unavailable`/`unknown` > X min, default 5).
- **REQ-REP-2 (M):** **solo fuentes requeridas**; las opcionales se ignoran.
- **REQ-REP-3 (M):** **un issue por módulo**, listando las fuentes que faltan.
- **REQ-REP-4 (M):** **acción del botón**: reabrir el **config flow** del módulo
  para corregir el mapeo.
- **REQ-REP-5 (M):** el issue **se borra** al recuperarse la fuente
  (`async_delete_issue`).
- **REQ-REP-6 (S):** emitir además evento `dynamic_home_degraded` (F10) para
  enrutar a Telegram/notify (power-users).

**Dependencias:** `binary_sensor degraded` existente (RNF-7).
**Criterios de aceptación:**
- ☐ Quitar una fuente requerida >5 min crea un issue con la lista de lo que falta.
- ☐ Pulsar el botón abre el config flow; restaurar la fuente borra el issue.

### 5.5 · Servicios y eventos nativos (F10)

**Objetivo:** capa de acciones (servicios) + eventos propios para
automatizaciones y dashboards. **Eventos primero** (mantienen el Telegram).

- **REQ-SVC-1 (S):** **eventos** `dynamic_home_degraded` (F07),
  `dynamic_home_conflict` (F02), `dynamic_home_filter_due` (F08),
  `dynamic_home_mode_changed` (F01).
- **REQ-SVC-2 (C):** **servicios** `reset_learning`, `boost(módulo, minutos)`,
  `set_observe(on/off)`, `reset_filter`, `recalibrate`/`refresh`.
- **REQ-SVC-3 (S):** documentados con `services.yaml` (selectores) y traducidos
  EN/ES (RNF-5). No bloqueante para el resto de la fase.

**Dependencias:** F01, F02, F07, F08 (emiten los eventos).
**Criterios de aceptación:**
- ☐ Un cambio de modo dispara `dynamic_home_mode_changed` con el modo nuevo.
- ☐ `boost` fuerza V3 los minutos indicados y auto-revierte (cubre F14).

### 5.6 · Energía y coste (F06)

**Objetivo:** energía/coste por módulo, con medidor real si lo hay o estimación
si no, integrado en el panel de Energía de HA.

- **REQ-ENE-1 (M):** **potencia** — usar el **sensor real** (p.ej. Shelly) si se
  aporta; si no, **estimación** por potencia configurable por estado/velocidad.
- **REQ-ENE-2 (M):** **energía (kWh)** como sensor `device_class: energy`,
  `state_class: total_increasing` → entra en el **panel de Energía**.
- **REQ-ENE-3 (S):** **coste (€)** opcional vía sensor de precio (tarifa plana o
  externa) o precio fijo configurable.
- **REQ-ENE-4 (M):** **DC opcional y gateado por F26** — en aerotermia comunitaria
  no aporta; en eléctrico/AC con medidor sí. Portar el cálculo de horas frío/calor
  del usuario (mejor con F27).
- **REQ-ENE-5 (S):** exponer **potencia instantánea total**; cruza con F03 (el
  pico de arranque de DS importa, ~2000 W con 12 persianas).

**Dependencias:** F26 (gating DC), F27 (horas exactas), F03 (pico).
**Criterios de aceptación:**
- ☐ Con Shelly, el kWh del módulo aparece en el panel de Energía.
- ☐ Sin medidor, la estimación por estado produce un kWh creciente coherente.

### 5.7 · Anti-pico / reparto de cargas (F03)

**Objetivo:** evitar arranques simultáneos que disparen el ICP, escalonando la
demanda. Solo donde el pico es un problema real.

- **REQ-PIC-1 (M):** **gateado por F26** — activo solo en **calefacción eléctrica**
  y motores DS; **off por defecto** en aerotermia/gas; **desactivado** en fuente
  comunitaria (REQ-INS-5).
- **REQ-PIC-2 (M):** **modo de límite según hardware**: con medidor(es) →
  límite por **amperios/kW** (potencia por zona); sin medidor → límite por **N
  zonas activas** simultáneas.
- **REQ-PIC-3 (M):** **escalonado temporal** configurable (no encender la siguiente
  hasta que la previa lleve, p.ej., ~10 s) para suavizar inrush.
- **REQ-PIC-4 (M):** **aplica también a DS** — escalonar subidas/bajadas masivas de
  persianas, no solo el clima eléctrico.
- **REQ-PIC-5 (S):** **prioridad de cola** por desviación de temperatura vs
  prioridad manual; posible **bypass de confort** ante frío severo (a detallar).

**Dependencias:** F26, F24, bus (el árbitro vive en el hub).
**Criterios de aceptación:**
- ☐ Con fuente comunitaria, el anti-pico ni aparece ni actúa.
- ☐ Pedir 3 zonas eléctricas a la vez las arranca escalonadas, no simultáneas.

### 5.8 · Señal de demanda real (F27)

**Objetivo:** entrada opcional por zona con la **demanda/válvula real** (no
inferida) que mejora el Adaptive Lead y da horas frío/calor exactas.

- **REQ-DEM-1 (M):** admite **tres fuentes** a elección: (a) `hvac_action` del
  `climate`; (b) **helpers explícitos** de demanda frío/calor; (c) **estado real
  de relé/potencia** (Shelly) — la más fiable.
- **REQ-DEM-2 (M):** si se aporta, el motor usa la señal como `valve_open` en lugar
  de inferirla; si no, **mantiene la inferencia actual** (compatibilidad).
- **REQ-DEM-3 (S):** la opción (c) captura la actuación del **termostato analógico
  de backup** (vía entrada SW del Shelly) que `hvac_action` no ve.
- **REQ-DEM-4 (M):** **coexistencia con backup hardware** — detectar el estado real
  sin pelearse con el termostato analógico cuando este actúe el relé.

**Dependencias:** Adaptive Lead (ya existe), F06 (horas exactas).
**Criterios de aceptación:**
- ☐ Con la señal real, las horas de calor/frío coinciden con la actuación del relé.
- ☐ Si el termostato de backup abre la válvula, el sistema lo refleja, no lo combate.

### 5.9 · Anti-ciclado corto (F09)

**Objetivo:** tiempos mínimos para proteger compresores, usando la tasa que el
aprendizaje ya mide.

- **REQ-CYC-1 (M):** protege con **min ON**, **min OFF** y **máx arranques/hora**
  (default 6/h).
- **REQ-CYC-2 (M):** **gateado por F26** — oculto en gas/eléctrico/aerotermia
  comunitaria; visible/activo con **compresor** (aerotermia o AC individual). La
  **emisión** ajusta los valores por inercia.
- **REQ-CYC-3 (M):** **la seguridad manda** — ante condensación u orden de
  seguridad, el anti-ciclado **cede** (apaga aunque no se cumpla el min ON).

**Dependencias:** F26 (gating), aprendizaje de tasa.
**Criterios de aceptación:**
- ☐ Con compresor, no se superan 6 arranques/h ni se viola el min OFF.
- ☐ Una orden anticondensación apaga aunque el min ON no se haya cumplido.

### 5.10 · Detección de ventana abierta (F20)

**Objetivo:** pausar el clima si se abre una ventana, sin climatizar a la calle.

- **REQ-WIN-1 (M):** **sensor real preferente** — `window_lockout` por
  `binary_sensor` cuando exista (detección directa).
- **REQ-WIN-2 (S):** **inferencia por caída de temperatura** como fallback/red
  extra: derivada brusca **+ coherencia con la demanda** (cae mientras calientas /
  sube mientras enfrías) para evitar falsos positivos.
- **REQ-WIN-3 (M):** **recuperación** al estabilizarse/recuperar la temperatura
  **o** por timeout, lo que ocurra antes.
- **REQ-WIN-4 (S):** **activable por zona**, sensibilidad configurable.

**Dependencias:** DC, F24 (por zona).
**Criterios de aceptación:**
- ☐ Abrir el contacto de ventana pausa la demanda de la zona.
- ☐ Sin sensor, una caída brusca coherente con la demanda dispara el lockout; recupera por timeout.

### 5.11 · Índice de moho (F22)

**Objetivo:** detectar riesgo de moho **sostenido** (no solo rocío puntual) como
alerta de salud y, si es efectivo, secar.

- **REQ-MOH-1 (M):** **modelo simple y configurable** — "horas por encima de HR
  umbral con decaimiento" (no el VTT completo). Umbral de HR y ventana/decaimiento
  configurables.
- **REQ-MOH-2 (M):** **aviso** (sensor + alerta) y **dispara secado (F13) solo si
  es efectivo** (gateado por `dp_diff`: no ventilar si el exterior no está más seco).
- **REQ-MOH-3 (S):** **activable por zona** (baños/dormitorios sí, salón quizá no).

**Dependencias:** F13 (secado por rocío), F24 (por zona).
**Criterios de aceptación:**
- ☐ Mantener HR alta varias horas eleva el índice y emite aviso.
- ☐ El secado solo arranca cuando el aire exterior está más seco (`dp_diff` favorable).

### 5.12 · Espacio adyacente / terraza (F31)

**Objetivo:** usar la temperatura de un espacio adyacente (terraza acristalada,
galería) comunicado por una puerta, para **avisar/aprovechar** (advisory).

- **REQ-ADY-1 (M):** requiere **sensor de temperatura del espacio adyacente**;
  comportamiento **advisory** (notificación/evento), sin actuar la puerta.
- **REQ-ADY-2 (M):** en `heat`, si el adyacente está mucho más caliente →
  **avisar para abrir la puerta** (ganancia solar gratuita).
- **REQ-ADY-3 (M):** en `cool`, si el adyacente está mucho más caliente →
  **avisar/alarma si se abre la puerta** (no meter ese calor).
- **REQ-ADY-4 (S):** umbrales de ΔT configurables, **por zona**; opción de **sesgar
  decisiones vía bus** además del aviso.

**Dependencias:** DC, F24, F33 (orientación/sol opcional).
**Criterios de aceptación:**
- ☐ En `heat` con terraza al sol muy por encima del salón, llega un aviso para abrir.
- ☐ En `cool`, abrir la puerta con la terraza caliente dispara la alarma configurada.

---

## 6. Trazabilidad

Cada requisito procede de una idea perfilada en `docs/BACKLOG.md` (misma
nomenclatura Fxx). Las decisiones de diseño y matices del usuario están en el
perfilado de cada Fxx; este documento las formaliza como requisitos verificables.

| Fase | Requisitos | Features origen |
|------|-----------|-----------------|
| 0 | REQ-ZON, REQ-INS, REQ-EMI, REQ-PRE, REQ-WEA | F24, F26, F25, F32, F33 |
| 1 | REQ-MOD, REQ-CMF, REQ-SCH, REQ-REP, REQ-SVC, REQ-ENE, REQ-PIC, REQ-DEM, REQ-CYC, REQ-WIN, REQ-MOH, REQ-ADY | F01, F23, F21/F29, F07, F10, F06, F03, F27, F09, F20, F22, F31 |

## 7. Pendiente de redactar
- Detalle de **Fases 2–4** (al entrar cada fase): DV, DS y Dynamic Energy.
- **Criterios de aceptación** ampliados y casos de prueba por requisito.
- **Plan de migración** desde la suite YAML del usuario (coexistencia vía modo observación).
