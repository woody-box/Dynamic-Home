# Dynamic Home — Documento de Requisitos

> Derivado de `docs/BACKLOG.md` (ideas F01–F35, perfiladas con el usuario).
> **Versión 5 — Fases 0–4 detalladas (documento completo)**. Prioridad por
> MoSCoW: **M** (Must) · **S** (Should) · **C** (Could). Cada requisito debe ser
> verificable.

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

> Todas las fases (0–4) están detalladas en §4–§8, partiendo del perfilado
> cerrado en `docs/BACKLOG.md`.

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
- ☑ Puedo crear zonas y grupos y asignar módulos desde la UI.
- ☑ Un cambio de modo en una zona no afecta a otras. *(cubierto por F01: override de
  modo por zona)*
- ☑ La jerarquía se persiste y sobrevive a reinicios.

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
  sola orden calculada con **agregación ponderada** de la demanda de las zonas del
  ámbito (peso por zona, REQ-EMI-9). Políticas seleccionables: **ponderada
  (default)** / peor parada / prioridad / media. La "peor parada" **deja de ser el
  default** por el riesgo de péndulo/undershoot en estancias pequeñas (un solo
  caudal no cortable por zona sobre-acondiciona las de baja demanda).
- **REQ-EMI-6 (S):** el AC aporta sus capacidades propias (dry nativo → usable por
  F13, fan, swing).
- **REQ-EMI-7 (M):** casos límite — solo AC ⇒ AC emisor único; solo radiante ⇒
  comportamiento actual.
- **REQ-EMI-8 (M):** **guarda de undershoot/overshoot** (conductos sin rejillas):
  como el caudal no es cortable por zona, la unidad **corta o modula a la baja**
  cuando la zona **más satisfecha** del ámbito alcanza su límite de confort en el
  sentido activo (`consigna ∓ shared_undershoot_margin`), aunque la peor parada no
  haya llegado. Acota el sobre-acondicionamiento de las estancias pequeñas (el
  compromiso físicamente inevitable de un conducto sin rejillas). **No aplica** con
  rejillas motorizadas (REQ-EMI-4: cada zona regula su propio caudal).
- **REQ-EMI-9 (S):** **parámetros del catálogo cerrado** para lo anterior:
  `zone_demand_weight` (por zona, adimensional, default 1.0; el usuario puede
  derivarlo de volumen/masa térmica si los conoce) y `shared_undershoot_margin`
  (°C, margen de la guarda de corte). Solo relevantes en ámbito grupo/casa **sin**
  rejillas.

**Dependencias:** F24, F26. **Habilita:** módulo AC, F13 (dry nativo).
**Criterios de aceptación:**
- ☐ Con radiante+AC, el apoyo arranca solo cuando el primario no llega y se retira al recuperar.
- ☐ Conductos sin zonificar: una sola orden coherente para todas las zonas del ámbito.
- ☐ Conductos con rejillas: control por zona vía rejilla, unidad con consigna única.
- ☐ Conductos sin zonificar con Salón muy caliente y Dormitorio casi en consigna:
  la unidad **no** sobre-enfría el Dormitorio (la guarda corta al llegar a
  `consigna − margen`), aunque el Salón quede un poco corto.
- ☐ Subir el `zone_demand_weight` del Salón sesga la consigna agregada hacia él
  **sin** anular la guarda de undershoot del Dormitorio.
- ☐ Con rejillas motorizadas, ni la ponderación ni la guarda aplican (control por
  zona vía rejilla).

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
- ☑ Si la fuente primaria no responde, el forecast sigue disponible por la secundaria.
- ☑ DC recibe forecast y DS recibe alertas sin configurar una integración meteo concreta.

### 4.6 · Explicador de conflictos del bus (F02)

**Objetivo:** hacer **observable el arbitraje del bus** — para cada consumidor,
qué intent gana sobre él y por qué. Apoyo transversal (RNF-4) que acompaña a las
fundacionales.

- **REQ-BUS-1 (M):** **una entidad por consumidor** del bus (cada VMC, cada
  persiana, y DC en su self-bias) que muestra qué intents le llegan y cuál gana.
- **REQ-BUS-2 (M):** **estado = intent ganador**; **atributo = motivo**
  (prioridad/TTL/origen). Sin la lista completa de descartados.
- **REQ-BUS-3 (S):** las entidades cuelgan de un **dispositivo central nuevo**
  "Dynamic Home · Bus" (identificador `(DOMAIN, "bus")`), no de cada módulo.
- **REQ-BUS-4 (M):** **solo estado actual**; sin registro en logbook/historial de
  conflictos.
- **REQ-BUS-5 (S):** emite evento `dynamic_home_conflict` (F10/REQ-SVC) para
  enrutar a notify/Telegram.

**Dependencias:** bus (`SdhbHub` ya tiene source/intent/target/priority/ttl;
basta un `explain(targets)`). **Habilita:** depuración de coordinación.
**Criterios de aceptación:**
- ☑ Cuando DC pide ganancia solar y DS quiere cerrar por viento, la entidad de esa
  persiana muestra el ganador y el motivo (origen/prioridad/TTL + aspirante).
- ☑ Cada consumidor (VMC/persiana/DC) tiene su entidad bajo el dispositivo
  "Dynamic Home · Bus".

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
- ☑ Cambiar a `Sleep` baja la VMC al cap configurado por ruido (WAF).
- ☑ `Away` apaga/atenúa (DC en vacación) sin necesidad del toggle de DC.
- ◐ El override manual prevalece (el preset manual/override local ya gana al modo);
  la pieza de **horario** depende de **F21** (no implementado).

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
- ☑ Quitar una fuente requerida >5 min crea un issue con la lista de lo que falta
  (transversal DV/DS/DC; evento `dynamic_home_degraded` al instante).
- ◐ Restaurar la fuente borra el issue (☑); el **botón** que reabre el config flow
  queda **diferido** (issue no-fixable + `learn_more_url`; el texto indica
  Ajustes → Dispositivos y servicios → Configurar) — REQ-REP-4 pendiente.

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
- ☑ `boost` fuerza V3 los minutos indicados y auto-revierte (cubre F14).

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
- ☑ Con Shelly (`power_meter`), el kWh del módulo aparece en el panel de Energía.
- ☑ Sin medidor, la estimación por estado produce un kWh creciente coherente.
- *(REQ-ENE-1/2/4 cubiertos en v0.12.0 para VMC/DC/DS; **coste (€)** REQ-ENE-3 y
  **potencia instantánea/pico** REQ-ENE-5 quedan diferidos; ver §12.x.)*

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
- ☐ Con la señal real, las horas de calor/frío coinciden con la actuación del relé. *(horas exactas: pend. F06; la señal ya sigue al relé)*
- ☑ Si el termostato de backup abre la válvula, el sistema lo refleja, no lo combate.

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
- ☑ Abrir el contacto de ventana pausa la demanda de la zona.
- ☑ Sin sensor, una caída brusca coherente con la demanda dispara el lockout; recupera por estabilización o timeout.

### 5.11 · Índice de moho (F22)

**Objetivo:** detectar riesgo de moho **sostenido** (no solo rocío puntual) como
alerta de salud y, si es efectivo, secar.

- **REQ-MOH-1 (M):** **modelo simple y configurable** — "horas por encima de HR
  umbral con decaimiento" (no el VTT completo). Umbral de HR y ventana/decaimiento
  configurables.
- **REQ-MOH-2 (M):** **aviso** (sensor + alerta) y **dispara secado (F13) solo si
  es efectivo** (gateado por `dp_diff`: no ventilar si el exterior no está más seco).
  *(También puede disparar un **deshumidificador** opcional por zona — siempre
  efectivo, sin gate `dp_diff`.)*
- **REQ-MOH-3 (S):** **activable por zona** (baños/dormitorios sí, salón quizá no).

**Dependencias:** F13 (secado por rocío), F24 (por zona).
**Criterios de aceptación:**
- ☑ Mantener HR alta varias horas eleva el índice y emite aviso.
- ☑ El secado solo arranca cuando el aire exterior está más seco (`dp_diff` favorable).

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
- ☑ En `heat` con terraza al sol muy por encima del salón, llega un aviso para abrir.
- ☑ En `cool`, abrir la puerta con la terraza caliente dispara la alarma configurada.

---

## 6. Fase 2 — DV (ventilación) (detalle)

Profundiza el módulo DV: anticipación por calidad de aire, respeto del ruido,
secado físicamente correcto, boost, diagnóstico del recuperador, IAQ ampliado y
sinergia con la campana de cocina. Reutiliza patrones ya existentes en DV (EMAs,
`dry_mode`, `dp_diff`, timer de override).

### 6.1 · Ventilación anticipatoria (F11)

**Objetivo:** pre-ventilar cuando CO₂/PM **suben rápido** (derivada), análogo al
lead de DC; modelado como el refuerzo de ducha/humedad pero con calidad de aire.

- **REQ-ANT-1 (M):** disparo por la **derivada (pendiente)** de **CO₂ y PM**
  (EMA-suavizada), con **umbral on/off** y **hold** anti-transitorio (patrón
  `shower_rh_delta_on/off` + `shower_hold_s`).
- **REQ-ANT-2 (M):** **anticipación suave** — una pendiente fuerte **adelanta** el
  salto de velocidad (V2/V3) antes de cruzar el umbral de nivel absoluto.
- **REQ-ANT-3 (S):** ampliable a VOC/NOx vía F30 (sin que estos **actúen** por
  defecto, REQ-IAQ).
- **REQ-ANT-4 (M):** umbrales, hold y constante de la EMA **configurables**
  (RNF-1); off por defecto si no se activa.

**Dependencias:** DV (EMAs existentes), F30 (contaminantes), F32 (presencia opc.).
**Criterios de aceptación:**
- ☑ Una subida brusca de CO₂ eleva la velocidad antes de alcanzar el umbral fijo.
- ☑ Un pico transitorio dentro del `hold` no provoca oscilación de velocidad.

### 6.2 · Horas de silencio (F12)

**Objetivo:** franja en la que la VMC no supera cierta velocidad por ruido (WAF),
distinta del schedule de encendido.

- **REQ-SIL-1 (M):** nivel máximo seleccionable en la franja: **`OFF / V1 / V2`**
  (V3 = sin cap). `OFF` cubre "apagar la máquina a ciertas horas".
- **REQ-SIL-2 (M):** **franja propia** (hora inicio/fin + nivel máx) **y**
  reutilizable por el **modo Sleep (F01)** (Sleep aplica el cap configurado).
- **REQ-SIL-3 (M):** **excepción de seguridad** — un umbral **crítico** de CO₂/PM
  **cede el cap** y sube igual (salud > silencio).
- **REQ-SIL-4 (S):** **por día** opcional (enlaza con el programador F21).

**Dependencias:** F01 (Sleep), F21 (por día), DV.
**Criterios de aceptación:**
- ☑ Dentro de la franja con cap `V1`, la VMC no supera V1 salvo umbral crítico.
- ☐ Activar `Sleep` aplica el mismo cap sin configurar la franja aparte. *(pend. F01)*

### 6.3 · Secado por punto de rocío (F13)

**Objetivo:** ventilar para secar **solo si el aire exterior es más seco**
(comparar puntos de rocío), no por HR relativa. Mejora del `dry_mode` actual.

- **REQ-DRY-1 (M):** **criterio: punto de rocío** — ventilar para secar si
  `dp_out < dp_in − margen` (usa el `dp_diff` ya calculado en el coordinator).
- **REQ-DRY-2 (M):** **sustituye/mejora el `dry_mode`** existente, que pasa a
  **gatear por `dp_diff`** en lugar de por HR relativa.
- **REQ-DRY-3 (M):** **margen ("corta ventaja") configurable** — no ventilar por
  diferencias mínimas.
- **REQ-DRY-4 (M):** **histéresis on/off regulable** para no conmutar en el límite.
- **REQ-DRY-5 (S):** si la zona tiene AC con **dry nativo** (REQ-EMI-6), puede
  usarse como alternativa/refuerzo al secado por ventilación.

**Dependencias:** DV (`dp_diff`), F22 (lo invoca), F25 (dry nativo AC).
**Criterios de aceptación:**
- ☐ Con el exterior más húmedo (`dp_out ≥ dp_in − margen`), el secado **no** ventila.
- ☐ Con ventaja clara de rocío, ventila; al estrecharse el margen, no oscila (histéresis).

### 6.4 · Boost (V3 temporizado) (F14)

**Objetivo:** forzar V3 N minutos con auto-reversión, reutilizando el timer de
override existente.

- **REQ-BST-1 (M):** **duración configurable** (`number` "minutos de boost"),
  nada hardcodeado.
- **REQ-BST-2 (M):** **solo V3** mientras dura; auto-revierte al expirar.
- **REQ-BST-3 (M):** se expone como **servicio** `dynamic_home.boost` (parte de
  F10/REQ-SVC); un `button` queda como azúcar opcional.
- **REQ-BST-4 (M):** **re-disparar reinicia** el temporizador.

**Dependencias:** F10 (servicio), timer de override (existe).
**Criterios de aceptación:**
- ☑ Invocar `boost(15 min)` fija V3 y vuelve al estado previo a los 15 min.
- ☑ Re-invocar durante el boost reinicia la cuenta atrás.

### 6.5 · Eficiencia del recuperador (F28)

**Objetivo:** sensor de rendimiento del recuperador + inferencia de bypass/fallo,
con **3 sondas** (la de expulsión NO interviene).

- **REQ-EFF-1 (M):** **η = (T_insuflación − T_absorción_aire_nuevo) /
  (T_extracción_viciado − T_absorción_aire_nuevo)** — rendimiento de impulsión,
  válido en ambos sentidos (recupera calor o frescor).
- **REQ-EFF-2 (M):** **3 sondas opcionales**; si faltan, el sensor **no se expone**
  (RNF-6/RNF-7).
- **REQ-EFF-3 (S):** exponer estado **"recuperación activa / bypass"** — η ~0 con
  ΔT significativo ⇒ no hay recuperación.
- **REQ-EFF-4 (S):** **avisar solo si el desplome es inesperado/sostenido** (no se
  distingue siempre bypass intencionado de suciedad/fallo solo por temperaturas →
  evitar falsas alarmas).

**Dependencias:** DV, F07 (aviso vía Repairs/evento).
**Criterios de aceptación:**
- ☑ Con las 3 sondas y ΔT real, η refleja el rendimiento; sin las sondas, no aparece.
- ☐ Un desplome puntual de η no dispara aviso; uno sostenido e inesperado sí. *(REQ-EFF-4, follow-up)*

### 6.6 · IAQ extendido (F30)

**Objetivo:** aceptar más contaminantes, pero con **acción acotada** a los que
tienen sentido sanitario en el caso objetivo.

- **REQ-IAQ-1 (M):** **actúan (suben velocidad): solo CO₂ y PM2.5** (como hoy).
- **REQ-IAQ-2 (M):** **VOC (COV): informativo/observación**, no actúa.
- **REQ-IAQ-3 (M):** **NOx descartado** de momento (no presente en el caso del
  usuario); estructura abierta a añadirlo si aparece.
- **REQ-IAQ-4 (S):** **contaminantes exteriores** (CO/PM10/NO2/SO2/O3/índice):
  **solo observación**, y alimentan el **"exterior hostil"** para no ventilar en
  días muy malos. *(Hoy: el "exterior hostil" ya opera sobre un índice AQI único
  (`CONF_AQI`). La observación multi-contaminante y su normalización a un índice
  común se completan con **F33**.)*

**Dependencias:** DV, F11 (deriva sobre los que actúan), F33 (exterior).
**Criterios de aceptación:**
- ☑ Subir VOC no cambia la velocidad; subir CO₂/PM2.5 sí.
- ☑ Con exterior hostil activo, no se ventila pese a IAQ interior mejorable.

### 6.7 · Campana extractora coordinada (F35)

**Objetivo:** sinergia de cocina — cuando el **PM interior sube** (air fryer /
cocinar) y la **campana** está apagada/baja, encenderla/subirla. Actuador extra
de calidad de aire complementario a la VMC.

- **REQ-CAM-1 (M):** entrada: **entidad de la campana** (`fan`/`switch`) + nivel
  objetivo configurable.
- **REQ-CAM-2 (M):** **disparo por PM interior** (nivel y/o derivada, reusa F11)
  por encima de umbral; **retira al normalizar** (histéresis/hold).
- **REQ-CAM-3 (S):** opción de **subir también la VMC en paralelo**.
- **REQ-CAM-4 (M):** **opt-in** — solo activo si el usuario aporta la campana; no
  asume hardware (RNF-6).

**Dependencias:** F11 (derivada PM), DV.
**Criterios de aceptación:**
- ☐ Un pico de PM con la campana apagada la enciende al nivel objetivo.
- ☐ Al normalizar el PM (con hold), la campana vuelve a su estado previo.

### 6.8 · Vida del filtro VMC (F08)

**Objetivo:** réplica nativa del control de filtros — % de vida + recordatorio al
umbral, sobre las `filter_hours` ya contabilizadas.

- **REQ-FIL-1 (M):** **intervalo configurable** (`number` "Vida del filtro (h)"),
  default **3650 h**; horas **totales simples** (ponderar por velocidad queda como
  mejora futura).
- **REQ-FIL-2 (M):** **sensor "% de vida del filtro"** = 100·(1 − filter_hours /
  intervalo).
- **REQ-FIL-3 (M):** **reset** mediante el **botón existente** (mecanismo offset,
  como `dv_filtros_horas_offset`).
- **REQ-FIL-4 (M):** **umbral único** (al 100% del intervalo); pre-aviso al 90%
  opcional.
- **REQ-FIL-5 (M):** **aviso** vía issue de **Repairs** (F07) + opción de
  notificación persistente / evento `dynamic_home_filter_due` (F10) para Telegram.
- **REQ-FIL-6 (C):** fecha/contador del último cambio, opcional (no por defecto).

**Dependencias:** DV (`filter_hours`), F07 (aviso), F10 (evento).
**Criterios de aceptación:**
- ☑ Al cruzar el umbral de vida, se emite el evento `dynamic_home_filter_due` y se
  crea el issue de **Repairs** (`filter_due`, no-fixable + `learn_more_url`).
- ☑ Pulsar el botón de reset (o el servicio `reset_filter`) devuelve el % a 100 y
  **borra** el issue; el aviso también se limpia al descargar la entrada.

---

## 7. Fase 3 — DS (persianas) (detalle)

Eleva el módulo DS de "todo/nada por % fijo" a control fino: sombreado por
geometría solar real, estrategia de inercia nocturna estacional, protección
anticipatoria por alertas meteo y apertura gradual al amanecer. Todo **coordinado
con la lógica DS existente** (free-cooling, viento/lluvia) y bajo "seguridad
manda".

### 7.1 · Sombreado geométrico real (F15)

**Objetivo:** calcular la penetración solar por geometría y cerrar **solo lo
necesario** (proteger X metros de suelo), no todo/nada.

- **REQ-GEO-1 (M):** **objetivo de control configurable**: no dejar que el sol
  directo penetre más de **X metros** de suelo.
- **REQ-GEO-2 (M):** **cálculo de penetración** = f(elevación y azimut del sol,
  geometría de la ventana, voladizo) → % de cierre que tapa justo esa penetración
  hasta el objetivo de metros.
- **REQ-GEO-3 (S):** **geometría ampliada opcional** — además de
  `window_height_cm` + `overhang_cm`, **altura de alféizar** (suelo→ventana) y
  **profundidad útil de la sala**.
- **REQ-GEO-4 (M):** actuación **por pasos** (p.ej. 25/50/75), no continua (el slew
  suaviza y evita mover la persiana cada poco).
- **REQ-GEO-5 (M):** **fallback** — si faltan datos de geometría, comportamiento
  actual (% fijo de solar shield).

**Dependencias:** DS, posición/azimut del sol (HA), F33 (opcional, nubosidad).
**Criterios de aceptación:**
- ☑ Con sol bajo, la persiana cierra más; con sol alto, menos, para mantener X m.
- ☑ Con el sombreado geométrico apagado (por defecto) o sin sol aplicable, aplica
  el % fijo actual (`summer_solar_shield`) sin error. *(Implementado en v0.12.0 como
  switch opt-in "Geometric shading"; ver §12.x.)*

### 7.2 · Aislamiento nocturno estacional (F16)

**Objetivo:** cerrar en noche de invierno (aislar) / abrir en noche de verano
(refrescar masa), ampliando `winter_night_pct`.

- **REQ-NOC-1 (M):** **estación por el MODO del climatizador de la zona**: `heat`
  → cara invierno (**cerrar para aislar**); `cool` → cara verano (**abrir/purga
  nocturna**).
- **REQ-NOC-2 (M):** **activable por zona**.
- **REQ-NOC-3 (M):** **noche = sol bajo el horizonte**.
- **REQ-NOC-4 (M):** **no duplicar free-cooling** — la cara de verano se
  **coordina** con el free-cooling existente; lo distintivo es la **estrategia de
  inercia** (abrir de noche para pre-acondicionar la masa y empezar el día
  siguiente con ventaja, incluso en condiciones marginales). _Condiciones térmicas
  exactas (ext vs int, consigna) a detallar en implementación._
- **REQ-NOC-5 (M):** **seguridad manda** (viento/lluvia/override por encima del
  aislamiento).

**Dependencias:** DS, modo del `climate` de la zona (F25), free-cooling existente.
**Criterios de aceptación:**
- ☑ En `heat`, al caer la noche la persiana cierra para aislar.
- ☑ En `cool`, la apertura nocturna no entra en conflicto con el free-cooling.

### 7.3 · Avisos meteo (tormenta/granizo) (F17)

**Objetivo:** alerta meteo → **protección preventiva** (anticipa el granizo, no
reacciona cuando ya cae). Capa anticipatoria sobre la protección viento/lluvia
actual.

- **REQ-MET-1 (M):** **fuente genérica y agnóstica** — el usuario enchufa un
  `binary_sensor` de "alerta meteo" (de cualquier proveedor/template); **no atarse
  a un proveedor** (RNF-6; AEMET es poco fiable).
- **REQ-MET-2 (S):** un disparo genérico "alerta → proteger" + **opcional** entradas
  separadas (granizo/tormenta vs viento) con **posiciones de protección distintas**.
- **REQ-MET-3 (M):** **posición de protección configurable** (no siempre cerrar del
  todo; a veces media protege mejor las lamas).
- **REQ-MET-4 (M):** **hold configurable** tras levantarse la alerta (mantener
  protegido X min).
- **REQ-MET-5 (M):** **complementa** la protección por viento/lluvia **actuales** ya
  existentes (esto es la capa anticipatoria).

**Dependencias:** DS, F33 (puede proveer la alerta), protección viento/lluvia.
**Criterios de aceptación:**
- ☑ Activar el `binary_sensor` de alerta lleva la persiana a la posición de protección.
- ☑ Al desactivarse, mantiene la protección el `hold` configurado antes de soltar.

### 7.4 · Apertura gradual al amanecer (F19)

**Objetivo:** subir la persiana poco a poco al amanecer (despertar natural), sin
pelear con el resto de la lógica DS.

- **REQ-AMA-1 (M):** **opt-in por zona** (p.ej. salón por las mañanas; dormitorio
  según preferencia).
- **REQ-AMA-2 (M):** **rampa por pasos de % + duración entre pasos**, configurable
  por zona.
- **REQ-AMA-3 (M):** **disparo por amanecer** (sol).
- **REQ-AMA-4 (M):** **coordinación** — si la persiana **ya está abierta** (p.ej.
  free-cooling en verano), la rampa **no actúa**; seguridad manda.

**Dependencias:** DS, amanecer (sol), free-cooling/F16.
**Criterios de aceptación:**
- ☑ Al amanecer, la persiana sube por pasos según la rampa configurada.
- ☑ Si ya estaba abierta por free-cooling, la rampa no la mueve.

---

## 8. Fase 4 — Dynamic Energy (módulo nuevo) (detalle)

Cerebro de energía al nivel de DC/DV/DS: **agrega** consumo/coste, **arbitra el
límite de red** y **publica contexto energético al bus** para que el resto module
su agresividad. **No comanda** a otros módulos (RNF-3/RNF-4). Consolida F03
(anti-pico), F04 (precio) y F06 (coste).

> ⚠️ **Testabilidad:** el autor no dispone de FV (probablemente tampoco batería ni
> wallbox). Los requisitos de **excedente FV, batería y VE** quedan **pendientes de
> validación externa**; lo testable por el autor es **red/anti-pico, coste/consumo,
> tarifa** y la **mecánica del bus** con entradas simuladas. Marcados con (⚠️).

### 8.1 · Núcleo del módulo y contexto del bus (F34)

**Objetivo:** un módulo Energy que publica el estado energético de la casa al bus;
cada consumidor (DC/DV/AC/DS) decide cómo reaccionar.

- **REQ-ENG-1 (M):** módulo con **coordinator propio + motor puro**
  (`energy_engine.py`) + publisher de bus, mismo patrón que DC/DV/DS (RNF-8).
- **REQ-ENG-2 (M):** **publica contexto al bus, no comanda** — los módulos siguen
  mandando sobre sí mismos y la **seguridad prevalece** (RNF-3).
- **REQ-ENG-3 (M):** contexto publicado: `import_headroom_w` (margen hasta el ICP),
  `tariff_state` (barato/normal/pico), `surplus_w` (⚠️ excedente FV),
  `scarcity` (caro y sin excedente).
- **REQ-ENG-4 (M):** **agnóstico (RNF-6)** — el usuario aporta las entidades
  (consumo total, red import/export, FV, SoC batería); funciona con **subconjuntos**.
- **REQ-ENG-5 (M):** **gating** — componentes FV/batería/VE **ocultos** si no se
  aportan sus entidades (estilo F26).
- **REQ-ENG-6 (M):** **resiliencia (RNF-7)** — degrada a lo disponible (sin medidor
  de red → anti-pico por "N cargas" en vez de por kW).

**Dependencias:** bus (RNF-4), F06 (entradas de consumo), F26 (patrón de gating).
**Criterios de aceptación:**
- ☐ Con solo medidor de red + precio, el módulo arranca y publica `import_headroom_w` y `tariff_state`.
- ☐ Sin entidades FV, los campos de excedente no se exponen ni rompen el arranque.

### 8.2 · Agregación de consumo y coste (consolida F06)

**Objetivo:** sumar lo que cada módulo ya expone (F06) en una vista de casa e
integrarlo en el panel de Energía de HA.

- **REQ-EAG-1 (M):** **agrega** consumo (kWh) y coste (€) de los módulos
  (DC/DV/DS) en totales de casa, sin duplicar la medición de cada uno.
- **REQ-EAG-2 (M):** expone energía como `device_class: energy`,
  `state_class: total_increasing` → **panel de Energía**.
- **REQ-EAG-3 (S):** **balance de casa** (consumo total vs red import/export y
  FV ⚠️), con coste neto si hay precio.

**Dependencias:** F06 (REQ-ENE), sensor de red.
**Criterios de aceptación:**
- ☐ El total de casa coincide con la suma de los módulos + cargas declaradas.
- ☐ La energía agregada aparece correctamente en el panel de Energía.

### 8.3 · Tarifa y precio (consolida F04)

**Objetivo:** traducir el precio (PVPC/Nordpool o tarifa plana) a un estado de
tarifa que el resto usa para desplazar cargas flexibles. (F04, descongelada aquí.)

- **REQ-TAR-1 (M):** acepta **sensor de precio** (variable) **o** precio/tramos
  **fijos** configurables; **agnóstico de integración** (RNF-6).
- **REQ-TAR-2 (M):** deriva `tariff_state` (barato/normal/pico) por umbrales
  configurables y lo publica al bus.
- **REQ-TAR-3 (S):** expone **horas baratas próximas** (ventana) para que DC/VE
  planifiquen pre-acondicionamiento/carga.
- **REQ-TAR-4 (C):** *(futuro)* alimentar el Adaptive Lead de DC para precalentar en
  horas baratas (era la idea de F04; queda como mejora, no Must).

**Dependencias:** F34 núcleo. **Habilita:** desplazamiento de cargas, F04.
**Criterios de aceptación:**
- ☐ Con un sensor de precio, `tariff_state` cambia según los umbrales definidos.
- ☐ Sin sensor, los tramos fijos producen el mismo estado de forma determinista.

### 8.4 · Anti-pico de red (consolida F03)

**Objetivo:** mantener el import por debajo de la potencia contratada (ICP),
escalonando/recortando cargas. Es la cara de red de F03, ahora dentro de Energy.

- **REQ-EPK-1 (M):** **límite de import** por amperios/kW si hay medidor; por
  **N cargas activas** si no (degradación, RNF-7).
- **REQ-EPK-2 (M):** **arbitra vía bus** publicando `import_headroom_w`; el
  escalonado real de cargas lo aplican los módulos / el hub (coherente con REQ-PIC).
- **REQ-EPK-3 (M):** **gateado por F26** — desactivado con fuente comunitaria;
  relevante en eléctrico/compresor y en picos de DS.
- **REQ-EPK-4 (S):** prioridad de cola (desviación de confort vs prioridad manual)
  y posible **bypass de confort** ante frío/calor severo.

**Dependencias:** F03/REQ-PIC (misma lógica de escalonado), F26.
**Criterios de aceptación:**
- ☐ Al acercarse al ICP, `import_headroom_w` baja y las cargas no superan el límite.
- ☐ Con fuente comunitaria, el anti-pico no actúa.

### 8.5 · Autoconsumo / excedente FV (⚠️ validación externa)

**Objetivo:** aprovechar el excedente FV para adelantar cargas flexibles, vía bus
(sesgo, no comando).

- **REQ-PVS-1 (M ⚠️):** calcula `surplus_w` (producción − consumo, con batería si
  la hay) y lo publica al bus.
- **REQ-PVS-2 (S ⚠️):** con excedente, **sesga** a DC/DV/VE para
  **pre-acondicionar/cargar** (lead más agresivo, boost), respetando que cada
  módulo decide y la seguridad manda.
- **REQ-PVS-3 (S ⚠️):** política de **batería** (umbrales de SoC para priorizar
  autoconsumo vs reserva) configurable.
- **REQ-PVS-4 (M ⚠️):** todo **opt-in y gateado**: sin FV, esta sección no existe.

**Dependencias:** F34 núcleo, entidades FV/batería del usuario.
**Criterios de aceptación (pendientes de validación externa):**
- ☐ Con excedente declarado, `surplus_w` es positivo y los módulos reciben el sesgo.
- ☐ Sin FV, la sección está oculta y no afecta al resto.

### 8.6 · Carga inteligente del VE (⚠️ validación externa)

**Objetivo:** cargar el coche de excedente FV o en horas baratas, con mínimo
garantizado y deadline.

- **REQ-VE-1 (M ⚠️):** requiere **wallbox controlable** (entidad aportada);
  **opt-in**, oculto si no existe.
- **REQ-VE-2 (S ⚠️):** modos: **solo excedente FV**, **horas baratas** (tarifa),
  o **mixto**; configurable.
- **REQ-VE-3 (M ⚠️):** **mínimo garantizado + deadline** ("salir con X% a las
  HH:MM") que prevalece sobre la optimización.
- **REQ-VE-4 (M ⚠️):** participa en el **anti-pico** (la carga cede `headroom`
  cuando la casa se acerca al ICP).

**Dependencias:** F34 núcleo, REQ-TAR (horas baratas), REQ-PVS (excedente), wallbox.
**Criterios de aceptación (pendientes de validación externa):**
- ☐ En modo "horas baratas", la carga se concentra en los tramos baratos respetando el deadline.
- ☐ Al acercarse al ICP, la carga del VE se reduce antes de recortar confort.

---

## 9. Trazabilidad

Cada requisito procede de una idea perfilada en `docs/BACKLOG.md` (misma
nomenclatura Fxx). Las decisiones de diseño y matices del usuario están en el
perfilado de cada Fxx; este documento las formaliza como requisitos verificables.

| Fase | Requisitos | Features origen |
|------|-----------|-----------------|
| 0 | REQ-ZON, REQ-INS, REQ-EMI, REQ-PRE, REQ-WEA, REQ-BUS | F24, F26, F25, F32, F33, F02 |
| 1 | REQ-MOD, REQ-CMF, REQ-SCH, REQ-REP, REQ-SVC, REQ-ENE, REQ-PIC, REQ-DEM, REQ-CYC, REQ-WIN, REQ-MOH, REQ-ADY | F01, F23, F21/F29, F07, F10, F06, F03, F27, F09, F20, F22, F31 |
| 2 | REQ-ANT, REQ-SIL, REQ-DRY, REQ-BST, REQ-EFF, REQ-IAQ, REQ-CAM, REQ-FIL | F11, F12, F13, F14, F28, F30, F35, F08 |
| 3 | REQ-GEO, REQ-NOC, REQ-MET, REQ-AMA | F15, F16, F17, F19 |
| 4 | REQ-ENG, REQ-EAG, REQ-TAR, REQ-EPK, REQ-PVS (⚠️), REQ-VE (⚠️) | F34, F03, F04, F06 |

Congeladas (fuera de fases): **F05** (outdoor reset), **F18** (anti-helada).
**F04** (precio) se recupera dentro de la Fase 4 (REQ-TAR).

## 10. Pendiente de redactar
- **Criterios de aceptación** ampliados y casos de prueba por requisito (al entrar
  cada fase a implementación).
- **Validación externa** de los requisitos ⚠️ (FV/batería/VE) por un usuario con
  esa instalación.

---

## 11. Plan de migración desde la suite YAML v4.2

**Objetivo:** pasar de la suite YAML (helpers + automatizaciones) a la integración
**sin cortes de servicio y sin que dos cerebros peleen por el mismo relé**.

### 11.1 · Principio rector: el conflicto solo está en los actuadores

- **Sensores = sin conflicto.** Leer un sensor (temperatura, CO₂, PM, HR, sol,
  viento…) es **read-only**: la integración y el YAML pueden leer **lo mismo a la
  vez** sin interferir. Mapear sensores nunca rompe nada.
- **Actuadores = único conflicto.** Solo los **relés de velocidad de la VMC**, los
  **motores de persiana** y el **relé de calefacción/válvula** pueden recibir
  órdenes contradictorias. La regla de oro: **un actuador, un dueño en cada
  momento**.
- **Corolario:** se puede tener toda la integración **funcionando y validándose en
  paralelo** al YAML mientras esté en **modo observación** (RNF-2), porque en
  observe **calcula y publica pero no actúa**.

### 11.2 · Las cuatro etapas (por módulo/actuador)

1. **A · Instalar en observe.** Añadir la(s) instancia(s) del módulo, mapear
   **sensores** (no hace falta tocar el YAML). Activar **"Observe only"**. La
   integración calcula, publica al bus y expone sus decisiones, **sin mover nada**.
2. **B · Observar y comparar.** Contrastar las decisiones de la integración contra
   el comportamiento real del YAML usando los **sensores de observabilidad 1:1**
   (biases DC, modo DV, target DS), el **explicador del bus (F02/REQ-BUS)** y el
   `binary_sensor degraded` + **Repairs (F07)** para detectar mapeos incompletos.
   No pasar de etapa hasta que coincida (o mejore) de forma consistente.
3. **C · Cesión de control (cutover atómico).** En **una sola ventana de
   mantenimiento por actuador**: **deshabilitar** la automatización YAML que manda
   ese relé **y** quitar el "Observe only" del módulo **a la vez**. Nunca dejar los
   dos activos sobre el mismo relé. Mantener los **helpers YAML deshabilitados (no
   borrados)** como rollback inmediato.
4. **D · Retirada.** Tras un período estable, borrar los helpers/automatizaciones
   YAML de ese actuador. El **hardware de backup** (termostato analógico por la
   entrada SW del Shelly) se conserva como red de seguridad final.

### 11.3 · Orden recomendado (de menor a mayor riesgo)

1. **DS · Persianas** — riesgo bajo (confort visual; el YAML ya protege por
   viento/lluvia). Migrar **fachada por fachada** (`ds_f<azimut>`): cede una
   fachada, observa el resto.
2. **DV · Ventilación** — riesgo medio. Validar especialmente el **break-before-make**
   de los relés de velocidad y el `dry_mode`/secado antes de ceder.
3. **DC · Clima** — riesgo alto (confort + **anticondensación** = seguridad). Va el
   **último**, pero conviene tenerlo **en observe desde el principio**: es el
   cerebro que publica al bus (ganancia/protección solar), así que observándolo se
   valida también lo que pedirá a DS/DV.

> Las **peticiones de DC al bus** hacia DS solo tienen efecto cuando **ambos** han
> cedido control; mientras DC esté en observe, publica pero DS (si ya cedió) puede
> escucharle — validar este cruce en la etapa B de DC.

### 11.4 · Reglas de seguridad durante la transición

- **Cutover atómico por actuador** (11.2-C): jamás YAML + integración mandando el
  mismo relé.
- **Coexistencia con el backup hardware (F27/REQ-DEM):** el termostato analógico
  puede actuar el relé por la entrada SW si cae la domótica; la integración debe
  **detectar el estado real** del relé y **no pelearse** con él. Recomendado
  aportar la señal real (opción c de REQ-DEM) antes del cutover de DC.
- **Anti-pico (F03) durante la convivencia:** si se ceden varios actuadores
  eléctricos a la vez, vigilar el pico de arranque; ceder **escalonado**.
- **Rollback en segundos:** re-habilitar la automatización YAML y volver a poner el
  módulo en observe.

### 11.5 · Checklist de cesión por módulo (resumen)

- ☐ Sensores requeridos mapeados (sin `degraded`/Repairs activos).
- ☐ Decisiones validadas en observe vs YAML (etapa B superada).
- ☐ Automatización(es) YAML del actuador **localizadas** y listas para deshabilitar.
- ☐ Ventana de mantenimiento: deshabilitar YAML **+** quitar observe (atómico).
- ☐ Helpers YAML deshabilitados (no borrados) como rollback.
- ☐ Período de estabilización superado → retirada del YAML.

---

## 12 · Fase 0 — Quick wins (criterios de aceptación)

Requisitos breves por feature de la Fase 0 del roadmap (ver `docs/ROADMAP.md`).
Cada feature se entrega en su propio commit con tests en verde.

### 12.1 · F10 — Servicios + eventos nativos

**Servicios** (`dynamic_home.*`), dirigibles por `target` (entity/device/area):

- `reset_learning` — borra el modelo adaptativo del DC (EMAs, lead aprendido,
  contadores y máquina de estado del ciclo). Solo actúa sobre módulos DC.
- `set_observe` (campo `enabled: bool`) — entra/sale de modo observación (dry-run)
  en DC/DV/DS.
- `reset_filter` — pone a cero las horas de filtro de la VMC (DV).
- `recalibrate` — fuerza un refresco inmediato del coordinator destino.

**Eventos** (`dynamic_home_*`), emitidos **solo en transición** (nunca cada ciclo):
`dynamic_home_degraded`, `dynamic_home_conflict`, `dynamic_home_filter_due`.
Payload común: `entry_id`, `name`, `module`.

**Aceptación:**

- ☐ Los 4 servicios existen tras cargar la primera entrada y desaparecen al
  descargar la última.
- ☐ Registro **único**: con varias entradas no se registran por duplicado.
- ☐ Cada servicio actúa solo sobre el coordinator del `target` (y del tipo correcto).
- ☐ Los helpers de `events.py` emiten el evento con el payload esperado.

### 12.2 · F02 — Explicador de conflictos del bus

Cada consumidor (DC/DV/DS) expone un sensor con el **intent ganador** del bus y
el **motivo** (fuente, prioridad, nº de candidatos). Todos los sensores se
agrupan bajo un único dispositivo compartido "Dynamic Home Bus".

**Aceptación:**

- ☐ `SdhbHub.explain(targets)` devuelve `{winner, source, priority, candidates,
  reason}` y su `winner` coincide siempre con `winner(targets)`.
- ☐ Sin candidatos → `winner="none"`, `reason="no_candidates"`.
- ☐ Con DC en frío + DS, el sensor de bus de DS muestra `request_solar_shield`
  con `priority=70` y `candidates>=1`.
- ☐ Los sensores de bus de todas las entradas caen en el dispositivo
  `(dynamic_home, "bus")`.
- ☐ Se emite `dynamic_home_conflict` al cambiar el ganador (no cada ciclo).

### 12.3 · F07 — Repairs sobre `degraded` (transversal DV·DS·DC)

Cuando una fuente **requerida** de un módulo está configurada pero **ausente/
renombrada u obsoleta** (`unavailable`/`unknown`) de forma **sostenida**
(> `ISSUE_STALE_S` = 300 s), se crea una incidencia en **Reparaciones** de Home
Assistant que **lista las fuentes que faltan**; se borra al recuperarse o al
descargar la entrada. El evento `dynamic_home_degraded` se emite en la transición
(inmediato), independientemente del umbral de la incidencia. El mecanismo es
**transversal**: un mixin `DegradedTracker` (`repairs.py`) lo comparten los tres
módulos. Requeridas por módulo: **DV** relés `sw_pwr/v2/v3` + `co2`/`pm25`; **DS**
el `cover`; **DC** la Tª interior (solo en heat/cool). Cada módulo expone además
el `binary_sensor` "Degradado".

**Aceptación:**

- ☑ Fuente requerida ausente/obsoleta → `degraded=True` y evento emitido (DV/DS/DC).
- ☑ La incidencia **no** aparece hasta superar el umbral de obsolescencia.
- ☑ Superado el umbral → incidencia `required_source_missing` con la lista de lo
  que falta (no *fixable*, con `learn_more_url`).
- ☑ Recuperación de la fuente → incidencia borrada + evento de salida.
- ☑ Descarga de la entrada degradada → incidencia borrada.
- ☑ Cobertura **transversal** DV/DS/DC (antes solo DC).
- ◐ Botón que reabre el config flow (REQ-REP-4) **diferido** (issue no-fixable).

### 12.4 · F08 — Vida del filtro VMC

Parámetro configurable "Vida del filtro (h)" (default 3650) y sensor "% de vida
del filtro" = `100·(1 − filter_hours/vida)`. Al cruzar el umbral se emite **una
vez** el evento `dynamic_home_filter_due` (histéresis `FILTER_DUE_PCT` /
`FILTER_CLEAR_PCT`) **y** se crea un issue de **Repairs** (`filter_due`,
no-fixable + `learn_more_url`). El reset (botón o servicio `reset_filter`) re-arma
el evento, devuelve el % a 100 y **borra** el issue.

**Aceptación:**

- ☑ `filter_life_pct(hours, life)` acota a [0,100] y devuelve 100 si `life<=0`.
- ☑ Sensor `sensor.<vmc>_filter_life` refleja el % restante.
- ☑ `dynamic_home_filter_due` se emite una sola vez por cruce (no en cada ciclo).
- ☑ Al cruzar el umbral se crea el issue de Repairs `filter_due`; el reset/descarga
  lo borra.
- ☑ Reset → re-arma el evento y el % vuelve a 100.
- ☑ "Vida del filtro (h)" aparece como número/opción configurable de la VMC.

### 12.5 · F13 — Secado por punto de rocío (DV)

El `dry_mode` de la VMC pasa a **gatear por punto de rocío**: solo ventila para
secar si el exterior está realmente más seco (`dp_diff = dp_in − dp_out` supera
un **margen** configurable), con **histéresis** para no oscilar. La selección de
velocidad (V1/V2/V3 por `dp_v2/v3_delta`) no cambia. Parámetros nuevos
(categoría "dry", no avanzados): `dry_margin` (default 1.0 °C), `dry_hys`
(default 0.5 °C).

**Aceptación:**

- ☐ Con el exterior igual de húmedo (`dp_diff ≤ margen`), el secado **no**
  ventila aunque `dry_mode` esté activo y el interior cerca del rocío (cae a IAQ).
- ☐ Con ventaja clara (`dp_diff > margen`), ventila (reason `dry_mode`).
- ☐ Histéresis: una vez activo se mantiene hasta `dp_diff ≤ margen − histéresis`;
  inactivo no se arma dentro de la banda → no oscila.
- ☐ `dp_diff None` / `dry_mode` off / sin `dew_risk` → no seca (estado reseteado).
- ☐ `dry_margin` y `dry_hys` configurables en opciones de la VMC.

### 12.6 · F11 — Ventilación anticipatoria (DV)

La VMC pre-ventila cuando CO₂ o PM **suben rápido**: un detector con histéresis
on/off + hold sobre la **pendiente** (derivada EMA) de cada contaminante adelanta
el salto de velocidad antes de cruzar el umbral de nivel absoluto. Modelado como
el refuerzo de ducha. Activable por **switch** ("Anticipatory boost"). Parámetros
nuevos (categoría "anticipatory"): `anticip_co2_rate_on/off`,
`anticip_pm_rate_on/off`, `anticip_hold_s`, `anticip_level`; avanzado:
`anticip_ema_alpha`.

**Aceptación:**

- ☐ Subida brusca de CO₂/PM (pendiente ≥ umbral on) eleva a `anticip_level` con
  reason `anticipatory`, aun en un tick de reloj (sin trigger IAQ).
- ☐ Tendencia plana no eleva; un pico dentro del `hold` no oscila (histéresis).
- ☐ No baja una base ya mayor; `hostile`/`sdhb_quiet` siguen capando por encima.
- ☐ `dt<=0` o primera muestra → pendiente 0 (no dispara).
- ☐ Switch off por defecto → comportamiento idéntico al anterior.

### 12.7 · Robustez — Piso de cordura de CO₂ (DV)

Una lectura de CO₂ por debajo de `co2_sanity_floor` (default 250 ppm,
configurable/avanzado, categoría "failsafe") es físicamente imposible en interior
habitado (línea base atmosférica ~410 ppm) y se trata como **fallo de sensor**:
se invalida en la validación inicial → cae al failsafe `vital_ko` (V1) y **no**
contamina la EMA. Solo CO₂ — el PM2.5 ~0 µg/m³ es real (aire limpio) y no se filtra.

**Aceptación:**

- ☐ CO₂ absurdamente bajo (p. ej. 0 tras glitch de calibración) → `failsafe_vital_ko`, V1.
- ☐ La EMA de CO₂ no se arrastra por la lectura absurda.
- ☐ CO₂ normal (≥ piso) y PM2.5 = 0 no disparan el failsafe.
- ☐ `co2_sanity_floor = 0` desactiva el piso (acepta 0).

### 12.8 · F12 — Horas de silencio (DV)

Franja diaria (con wrap nocturno) en la que la VMC **no supera** un nivel máximo
(`OFF/V1/V2`; V3 = sin cap), por ruido/WAF. **Excepción de seguridad:** un CO₂ o
PM2.5 por encima de su umbral **crítico** levanta el cap (salud > silencio).
Aplica solo a la ruta **auto/IAQ** (incluye freecool y anticipatorio F11);
manual override, ducha y secado la **bypasean**. Entidades: switch "Quiet hours",
number "Quiet max level" (0-2), times "Quiet start/end"; opciones (categoría
"quiet"): `quiet_critical_co2` (1500), `quiet_critical_pm` (50). Reutilizable por
el modo Sleep (F01) cuando exista.

**Aceptación:**

- ☐ Dentro de la franja, con CO₂ alto que pediría V3, la velocidad se limita a
  `quiet_max_level` (reason `quiet_cap`); fuera de la franja no.
- ☐ CO₂/PM ≥ crítico levanta el cap (sube igual).
- ☐ `quiet_max_level=0` apaga; `=3` no capa.
- ☐ Manual override / ducha / secado no se ven afectados por el cap.
- ☐ Switch off por defecto → comportamiento idéntico al anterior.

### 12.9 · F14 — Boost (V3 temporizado, DV)

Servicio `dynamic_home.boost` (campo `minutes`, default 15) que fuerza la VMC a
**V3** durante N minutos y **auto-revierte** al expirar (granularidad del ciclo,
~60 s). Re-invocar **reinicia** la cuenta atrás. Es explícito: **bypasea** el cap
de horas de silencio (F12) y la ruta auto, pero respeta el gate `permitida`
(lockout/no permitido). Completa el hook de servicio que F10 dejó documentado.
La duración por defecto vive en `BOOST_MIN_DEFAULT` (no hardcodeada en el motor);
un `number`/`button` de azúcar UI queda como follow-up opcional (REQ-BST-1/3).

**Aceptación:**

- ☐ `boost(minutes=N)` → V3 inmediato (reason `boost`); al expirar vuelve al control normal.
- ☐ Re-invocar reinicia el temporizador (`boost_until` se extiende).
- ☐ Bypasea el cap de silencio pero no actúa si el módulo no está `permitida`.
- ☐ Solo afecta a módulos DV del `target`.

### 12.10 · F28 — Eficiencia del recuperador (DV)

Sensor diagnóstico de rendimiento del recuperador con **3 sondas dedicadas
opcionales** (insuflación, absorción de aire nuevo, extracción; la de expulsión
NO interviene): η = (T_insuflación − T_absorción) / (T_extracción − T_absorción),
clamp [0,1], válido en ambos sentidos. Solo se expone si están las 3 sondas.
Atributo `state`: `recovering` / `bypass` / `idle` (η~0 con ΔT significativo →
bypass; ΔT pequeño → idle). Umbrales configurables (categoría "recuperator"):
`hrv_bypass_eff_max` (0.2), `hrv_bypass_dt_min` (3 °C).

**Aceptación:**

- ☐ Con las 3 sondas y ΔT real, η refleja el rendimiento; sin sondas, el sensor no aparece.
- ☐ η~0 con ΔT significativo → `state=bypass`; ΔT pequeño → `idle`; recuperación normal → `recovering`.
- ☐ Funciona en calor y en frío (ambos signos de ΔT).

**Diferido (REQ-EFF-4):** el aviso por desplome sostenido/inesperado (Repairs/
evento) queda como follow-up — el spec advierte del riesgo de falsas alarmas al
no distinguir bypass intencionado de fallo solo por temperaturas.

### 12.11 · F30 — IAQ extendido (DV)

Acepta **VOC como observación** (REQ-IAQ-2): entrada opcional `CONF_VOC` + sensor
diagnóstico "VOC" que **espeja la lectura** y **no entra en `decide()`** — esa es
la garantía de REQ-IAQ-1 (solo CO₂/PM2.5 actúan). Solo se expone si la sonda está
configurada (`has_voc()`). **NOx** (REQ-IAQ-3) queda **descartado** por ahora; el
patrón de sensor de observación deja la puerta abierta a añadirlo trivialmente. El
**"exterior hostil"** (REQ-IAQ-4 / AC2) ya operaba sobre el índice `CONF_AQI`
(cap `hostile_*` en el motor): se añade test de contrato. La observación
multi-contaminante exterior (CO/PM10/NO2/SO2/O3) y su normalización a un índice
hostil común se **difieren a F33** (su dependencia).

**Aceptación:**

- ☐ Con `CONF_VOC`, aparece el sensor "VOC" y espeja la lectura; sin ella, no aparece.
- ☐ Subir VOC con CO₂/PM2.5 limpios **no** cambia la velocidad; subir CO₂ sí (→ V3).
- ☐ Con AQI exterior ≥ umbral, la decisión es `hostile_off` pese a CO₂ interior alto.

**Diferido a F33:** observación de contaminantes exteriores (CO/PM10/NO2/SO2/O3) y
su agregación a un índice hostil; NOx (REQ-IAQ-3) si aparece en el caso de uso.

### 12.12 · F27 — Señal de demanda/válvula real (DC)

Entrada opcional por entrada DC con la **demanda real** de la zona, que alimenta el
**Adaptive Lead** (detección de ciclo) en lugar de inferirla de `t_int` vs
`target`. Prioridad **c > b > a**, con *fallback* a la inferencia actual
(compatibilidad):

- **(c)** `CONF_DC_VALVE`: estado real de relé/potencia (Shelly). Numérico →
  `> valve_power_min` (W); binario → on/off. La más fiable; **captura el termostato
  analógico de backup** que `hvac_action` no ve.
- **(b)** `CONF_DC_DEMAND_HEAT`/`CONF_DC_DEMAND_COOL`: helpers explícitos por modo.
- **(a)** `hvac_action` del `CONF_DC_CLIMATE` (`heating`/`cooling`→on; `idle`/`off`→off).

Diagnóstico: `binary_sensor` "Demanda real" (device_class `running`, atributo
`source`), creado **solo si hay fuente real** (`has_real_demand()`). Tunable
`valve_power_min` (opciones, categoría "demand", avanzado).

**Aceptación:**

- ☐ Con `CONF_DC_VALVE` (c), la demanda sigue al relé independientemente del modo/orden de DC.
- ☐ Helpers (b) y `hvac_action` (a) en su prioridad; sin fuentes → inferencia (sin regresión).
- ☐ El `binary_sensor` aparece solo con fuente real configurada.

**Diferido a F06:** el contador de **horas exactas** de calor/frío (la señal real
ya está lista para alimentarlo cuando se construya F06).

### 12.13 · F22 — Índice de moho (DC)

Riesgo de moho **sostenido** por entrada DC: índice = "horas por encima de
`mold_rh_threshold` con decaimiento exponencial" (helper puro `mold_index_step`),
acumulado en el coordinator e integrado por tiempo (patrón `_accumulate`),
**persistido** vía `MoldIndexSensor` (RestoreSensor, unidad h). Histéresis
`mold_on_h`/`mold_off_h` arma/desarma. Solo se expone con RH interior
(`has_mold()` ← `CONF_DC_HUMIDITY`).

Al armarse: **Repairs issue** (`mold_risk`) + **evento** `dynamic_home_mold`, y
**dos vías de secado**:
1. **Bus** → publica `request_dry` a `"dv"`; DV lo consume (`INTENT_DRY`,
   `DvInputs.dry_requested`) aplicando su **gate `dp_diff` (F13)** → solo seca si
   el exterior está más seco. DC no necesita humedad exterior.
2. **Deshumidificador** opcional (`CONF_DC_DEHUMIDIFIER`) → `homeassistant.turn_on/off`
   (siempre efectivo, sin gate; respeta modo *observe*).
Al desarmarse se borran issue, bus y deshumidificador.

**Aceptación:**

- ☐ RH alta sostenida sube el índice → Repairs + evento + `request_dry` + deshumidificador ON.
- ☐ DV solo seca con `dp_diff` favorable (gate F13 intacto para la vía bus).
- ☐ Sin `CONF_DC_HUMIDITY` no se expone el sensor de índice.

**Notas:** "por zona" = por entrada DC (F24 añadirá grupo). Caveat: arbitraje
multi-intent en `"dv"` (dry vs quiet/boost) en primer corte.

### 12.14 · F20 — Detección de ventana abierta (DC)

Con sensor (`CONF_DC_WINDOW`) el comportamiento previo se mantiene
(`window_lockout` → `DcDecision OFF`, reason `off_window`). F20 añade una
**inferencia por temperatura** para zonas **sin sensor** (`has_window_infer()` ⇒
`not _hw(CONF_DC_WINDOW)`):

- Señal pura `window_anomaly(hvac, valve_open, trend_cph, cfg)`: zona climatizando
  cuya Tª interior se mueve **en contra** de la demanda más rápido que
  `window_drop_cph` (cae calentando / sube enfriando). `valve_open` viene de la
  señal real F27 (`_real_valve_open`) o, sin fuente, de `hvac in (heat,cool)`.
- Latch en el coordinator (`_infer_window`) con **confirm** (debounce para armar),
  **release** (estabilización para desarmar) y **timeout** de seguridad
  (`window_confirm_min` / `window_release_min` / `window_max_lockout_min`).
- Al armar: `DcInputs.window_inferred` → `decide()` devuelve OFF con reason
  `off_window_inferred`, y **aborta el aprendizaje** igual que el sensor. Evento
  `dynamic_home_window` en cada transición.
- Diagnóstico: `WindowInferredBinarySensor` (device_class window) solo cuando
  aplica. Opciones: categoría `window` (sensibilidad principal + 3 avanzados).

**Aceptación:**

- ☐ Sin sensor, caída coherente sostenida ≥ confirm → OFF (`off_window_inferred`).
- ☐ Recupera al estabilizarse la Tª (release) o por timeout de seguridad.
- ☐ Con sensor configurado, la inferencia queda inactiva (manda el sensor).

**Notas:** decisión usuario = solo sin sensor; con sensor, sin inferencia. La
lógica de latch se testea inyectando `now_ts`/`trend_cph` en `_infer_window`
(el derivado real usa reloj de pared).

### 12.15 · F31 — Espacio adyacente / terraza (DC)

Advisory por entrada DC, **sin actuar la puerta**. Requiere sensor de Tª del
adyacente (`CONF_DC_ADJ_TEMP`); puerta opcional (`CONF_DC_ADJ_DOOR`).

- Señal pura `adjacent_advice(hvac, t_int, t_adj, door_open, cfg)` →
  `"open_gain"` / `"close_alarm"` / `"none"`:
  - **heat**: `t_adj − t_int ≥ adj_open_dt` y puerta cerrada (o sin sensor) →
    `open_gain` (avisar para abrir y aprovechar ganancia solar gratuita).
  - **cool**: `t_adj − t_int ≥ adj_alarm_dt` y **puerta abierta** → `close_alarm`
    (entra calor mientras enfrías). Sin sensor de puerta no hay alarma.
- Coordinator `_adjacent_step`: evalúa cada ciclo y emite evento
  `dynamic_home_adjacent` en cada transición; expone `AdjacentAdviceSensor`
  (enum diagnóstico) solo si `has_adjacent()`.
- Opciones: categoría `adjacent` (`adj_open_dt`, `adj_alarm_dt`), por zona.

**Aceptación:**

- ☐ heat + adyacente muy por encima + puerta cerrada → `open_gain` + evento.
- ☐ cool + adyacente caliente + puerta abierta → `close_alarm` + evento.
- ☐ Sin `CONF_DC_ADJ_TEMP` no se expone el sensor de aviso.

**Diferido (REQ-ADY-4, S):** sesgar decisiones vía bus además del aviso; el primer
corte es solo advisory (evento + sensor).

### 12.16 · F36 — Espejos de hardware para dashboards (HAL de salida)

La integración ya es el mapa rol→`entity_id` para la lógica; F36 lo extiende a los
**dashboards**: expone un sensor "espejo" estable por cada **rol de entrada
numérico** configurado, con `unique_id = (entry_id, rol)`. El dashboard apunta a la
entidad de la integración; reemplazar el sensor físico = solo reconfigurar la
entrada (el `unique_id` no cambia).

- **Opt-in por entrada**: opción booleana `expose_mirrors` (off por defecto) en un
  paso propio del options flow. Al cambiarla, `_async_options_updated` **recarga**
  la entrada (las entidades se crean en el setup de la plataforma).
- `HwMirrorSensor` (en `sensor.py`): sigue al origen vía
  `async_track_state_change_event` y copia `value`/`unit`/`device_class`/
  `state_class`. Roles cubiertos: DV (co2, pm25, t_in/t_ext, AQI, humedades, HRV,
  voc), DC (dc_t_int/dc_t_ext/dc_humidity/dc_wind/dc_adj_temp), DS (ds_t_in/
  ds_t_out/wind). Se omiten switches/cover/climate/binarios.

**Aceptación:**

- ☐ Con `expose_mirrors` on, aparece un espejo por rol configurado, reflejando
  valor y unidad/clase del origen.
- ☐ Off por defecto: no se crea ninguna entidad espejo.
- ☐ Cambiar el toggle recarga la entrada y crea/elimina los espejos.

**Diferido:** mirror de roles binarios (ventana/puerta/lluvia) como
`binary_sensor`; nivel de grupo (F24).

### 12.17 · F19 — Apertura gradual al amanecer (DS)

Opt-in por zona (switch "Gradual sunrise"). Al cruzar el sol la
`dawn_trigger_elevation` hacia arriba y **solo si la persiana no está ya (casi)
abierta**, arranca una rampa que sube `dawn_step_pct` cada `dawn_step_min` hasta
`dawn_target_pct`.

- Señal pura: nueva rama `dawn_ramp` en `decide_cover` (en el `else`, tras
  override/lluvia/privacidad y **antes** de las ramas de clima), que usa
  `DsInputs.dawn_pos`.
- Estado/tiempo en `coordinator_ds._dawn_step`: detecta el cruce del sol
  (`_prev_sun_el`), gestiona la rampa y devuelve la posición escalonada o `None`.
  **Solo sube** (floor creciente, `max(target, current_pos)`); termina al llegar
  al objetivo o si algo la abre antes → no pelea con free-cooling ni con el
  usuario. Caps (viento/bus/slew) y seguridad siguen mandando.
- Config (categoría `dawn`): `dawn_step_pct`, `dawn_step_min`, `dawn_target_pct`,
  `dawn_trigger_elevation`.

**Aceptación:**

- ☐ Al amanecer la persiana sube por pasos según la rampa.
- ☐ Si ya estaba abierta (free-cooling/usuario), la rampa no la mueve.
- ☐ Opt-in: desactivada por defecto (switch).

### 12.18 · F16 — Aislamiento nocturno estacional (DS)

Opt-in por zona (switch "Night insulation"). Estación por el **modo del climate**
de la zona; **noche = sol bajo el horizonte** (`sun_el <= 0`). Autocontenido: no
toca el `night`/free-cooling latentes; usa su propio `DsInputs.night_pos`.

- `coordinator_ds._night_iso(cfg, hvac, sun_el, t_in, t_out)`:
  - `heat` + noche → `night_iso_close_pct` (cerrar para aislar).
  - `cool` + noche → `night_iso_open_pct` si `t_out <= t_in` (purga de la masa),
    si no `night_iso_close_pct` (proteger la masa en noche cálida); temps
    desconocidas → `None` (decide la cascada).
  - Desactivado / de día / sol desconocido → `None`.
- Motor: rama `night_insulate` en `decide_cover` (en el `else`, tras
  override/lluvia/privacidad y la rampa de amanecer, **antes** de las ramas de
  clima). Caps (viento/bus/slew) y seguridad siguen mandando.
- Config (categoría `night`): `night_iso_close_pct`, `night_iso_open_pct`.

**Aceptación:**

- ☐ En `heat`, de noche cierra para aislar.
- ☐ En `cool`, de noche abre solo si el exterior está más fresco (no mete calor);
  no duplica el free-cooling (cuando F16 está activo, posee la estrategia nocturna).
- ☐ Opt-in: desactivado por defecto.

**Nota:** el `night`/free-cooling base siguen latentes (pre-existente); F16 es
independiente y opt-in.

### 12.19 · F17 — Avisos meteo / protección anticipatoria (DS)

Capa anticipatoria sobre la protección viento/lluvia. **Agnóstica de proveedor**:
el usuario enchufa hasta 3 `binary_sensor` (genérico `CONF_DS_ALERT`, granizo
`CONF_DS_ALERT_HAIL`, viento `CONF_DS_ALERT_WIND`); cada uno con su posición de
protección. La **adquisición** del dato es de Meteoalarm / Open-Meteo / template
del usuario / F33, **no** de la integración.

- `coordinator_ds._weather_alert(cfg, now_ts)`: entre las alertas activas toma la
  posición **más protectora** (`min` de `alert_pct`/`alert_hail_pct`/
  `alert_wind_pct`); al despejarse mantiene un **hold** (`alert_hold_min`) antes
  de soltar. Devuelve la posición o `None`.
- Motor: rama `meteo_alert` en `decide_cover` (tras override, **antes** de lluvia),
  añadida a `PROTECTED` (slew/viento/bus no la mueven). Override sigue por encima.
- Config (categoría `alert`): `alert_pct`, `alert_hail_pct`, `alert_wind_pct`,
  `alert_hold_min`.

**Aceptación:**

- ☐ Activar el binary_sensor de alerta → persiana a la posición de protección.
- ☐ Al desactivarse, mantiene el `hold` configurado antes de soltar.
- ☐ Varias alertas activas → gana la más protectora (cierre).

**Nota:** complementa (no sustituye) la protección por viento/lluvia *actuales*.

### 12.20 · F35 — Campana extractora coordinada (DV)

Sinergia de cocina: cuando el **PM2.5 interior** sube (cocinar/air-fryer), encender
o subir la campana para limpiar el aire; complementa a la VMC. **Caso de hardware:
3 relés, uno por velocidad** (ausencia de relés = OFF).

- Pura `dv_engine.hood_speed(pm, prev, cfg)`: nivel 0..3 por umbrales
  `hood_pm_v1/v2/v3` con **histéresis** `hood_hys` (baja de nivel solo cuando el PM
  cae por debajo del umbral del nivel actual menos la histéresis); PM ausente →
  mantiene el nivel.
- `coordinator_dv`: `has_hood()` (algún relé configurado); calcula
  `hood_speed_auto` cada ciclo con el PM ya leído.
- `fan.HoodFan` (creada solo si `has_hood()`): entidad **fan** propia "Campana" con
  presets auto/V1/V2/V3/off (restaurados), **driver break-before-make 1-de-3**
  (baja los no-objetivo → `RELAY_SETTLE_S` → cierra el objetivo; off = todos
  abiertos), **observe-mode** respetado, y un **vigilante de interlock**: si dos
  relés quedan en `on` a la vez, fuerza corrección reaplicando la velocidad. En
  auto, `_handle_coordinator_update` aplica el `hood_speed_auto`.
- Config (categoría `hood`): `hood_pm_v1/v2/v3`, `hood_hys`; 3 selectores de relé
  en el alta VMC.

**Aceptación:**

- ☐ PM interior alto sostenido → la campana sube de velocidad (auto).
- ☐ Cambiar de velocidad nunca energiza dos relés a la vez (break-before-make).
- ☐ Si dos relés quedan activos (manual), el interlock lo corrige.

**Seguridad:** el software coordina, **no** sustituye un **interlock hardware**
(relés mutuamente excluyentes / selector); recomendado para garantizar "nunca dos
velocidades". Override/observe siguen mandando.

### 12.21 · F33 — Dynamic Weather (módulo nuevo)

Capa meteo **resiliente y agnóstica**: módulo propio (`MODULE_WEATHER`,
plataformas `weather`/`binary_sensor`/`sensor`) que **no obtiene datos**, sino que
elige la primera fuente sana de una lista priorizada y **reexpone** una vista
normalizada con fallback. **No mete APIs/keys** en la integración (RNF-6): consume
entidades `weather.*` de HA (Open-Meteo oficial sin clave, OWM, met.no, AEMET…) y,
como último recurso, **sensores crudos** del usuario.

- Motor puro `weather_engine`: `pick_source` (primera disponible por prioridad),
  `is_fresh` (caduca tras `stale_after_h`), `derive_alert` (condición peligrosa /
  viento / precipitación → alerta).
- `coordinator_weather.WxCoordinator`: fuentes `wx_source_1/2/3` (weather) →
  fallback `wx_temp/wx_wind/wx_precip` (sensores); elige activa, expone
  `active_label`/`active_entity`/`active_since`, condición/temp/humedad/presión/
  viento y la alerta; evento `dynamic_home_weather_source` al cambiar de fuente.
- `weather.ProxyWeather`: entidad `weather` que **espeja** la fuente activa y
  **reenvía `get_forecasts`** a ella → DC (forecast bias) y free-cooling la
  consumen transparente, con fallback. `unavailable` solo si **todas** caen.
- `binary_sensor` "Alerta meteo" (device_class safety) → consumible por **DS/F17**.
  `sensor` "Fuente activa" (diagnóstico, con `since`). Opciones (categoría `wx`):
  `stale_after_h`, `alert_wind_kmh`, `alert_precip_mm`.

**Aceptación:**

- ☐ Si la primaria cae, el forecast sigue por la secundaria; si todas caen, por
  los sensores crudos (sin forecast).
- ☐ DC apunta `CONF_DC_WEATHER` a la entidad proxy y recibe forecast con fallback;
  DS apunta su alerta (F17) al `binary_sensor` derivado.
- ☐ Diagnóstico de fuente activa + `since`; `unavailable` solo si todas fallan.

**Notas:** el forecast solo está disponible cuando la fuente activa es una
entidad `weather` (los sensores crudos dan solo valores actuales). La alerta
derivada es heurística (condición/viento/precip); para avisos oficiales,
Meteoalarm sigue siendo enchufable en F17.

### 12.22 · F24 — Zonas y grupos (estructura)

Jerarquía **propia** zona → grupo → casa (no Areas de HA), en una **entrada
singleton** "Dynamic Home · Zonas" (`MODULE_ZONES`, `unique_id="zones_singleton"`).
**Alcance v0.10.0 = solo estructura**; el **modo por ámbito (REQ-ZON-4) se difiere
a F01**, que consumirá esta estructura.

- Modelo puro `zones.py`: árbol en `entry.options[CONF_ZONES_TREE]`
  (`{zones:{zid:{name,modules[]}}, groups:{gid:{name,zones[]}}}`); helpers
  `assign_modules` (1 módulo→1 zona, expulsando de otras), `assign_zones`
  (1 zona→1 grupo), `add/remove_*`, `scope_for_module` (API para F01/F21/F25),
  `counts`.
- **Editor de árbol** en un `ZonesOptionsFlow` dedicado (devuelto por
  `async_get_options_flow` para el módulo zonas): pasos `zone_add`/`zone_edit`/
  `zone_detail`/`group_add`/`group_edit`/`group_detail` con multi-select de
  módulos/zonas existentes.
- `ZonesCoordinator` (read-only, config-time) **publica** el árbol normalizado en
  `hass.data[DOMAIN][DATA_ZONES]`; la entrada **recarga** al editar para
  re-publicarlo. `ZonesSensor` diagnóstico (nº zonas + árbol legible).

**Aceptación:**

- ☑ Crear zonas/grupos y asignar módulos desde la UI (singleton; 2ª alta aborta).
- ☑ Persiste en `entry.options` y sobrevive a reinicios; 1 módulo no queda en dos
  zonas (validación).
- ☐ "Un cambio de modo en una zona no afecta a otras" → **F01** (consume
  `scope_for_module` + `DATA_ZONES`).

**Nota:** F24 entrega solo la estructura + la API de resolución de ámbito; sin
consumidores de modo todavía.

### 12.23 · F01 — Modos de la casa

Un **modo** (`Home/Away/Sleep/Boost/Eco`) que sesga todos los módulos por ámbito
(**casa + override por zona**, vía F24). Alojado en la entrada de Zonas; el modo
es **independiente de DC** y **sustituye** la vacación de DC en `Away`.

- Capa de coordinación: la entrada de Zonas resuelve el **modo efectivo por
  módulo** (override de zona ?? casa, `modes.effective_mode_for_entry` con
  `zones.scope_for_module`) y lo **publica** en `hass.data[DOMAIN][DATA_MODE]`;
  cada coordinator lee su modo (sin meter el modo como intent en el SDHB). Evento
  `dynamic_home_mode_changed`. *(Un módulo futuro —F25— solo lee
  `effective_from_published`, REQ-MOD-5.)*
- Plataforma `select` en la entrada de Zonas: **Modo casa** + un **Modo por zona**
  (`auto` hereda), restaurados.
- Consumo: **DV** capa la velocidad del modo (`mode_cap`/`mode_boost` → ramas
  `mode_cap`/`mode_boost` en `decide`, con excepción de seguridad por IAQ crítico);
  **DC** `vacation = switch or is_away(modo)`. **DS** lee el modo sin efecto
  todavía (extensible). Caps por modo configurables (paso `mode_caps`).

**Aceptación:**

- ☑ `Sleep` → la VMC de la zona baja a su cap (WAF), salvo aire crítico.
- ☑ `Away` → DC en vacación sin su switch; override de zona resuelve por zona.
- ◐ Jerarquía override>manual>modo (el local ya prevalece); **horario → F21**.

**Diferido (anotado):** horario (F21) en la jerarquía; efecto de modo en DS;
override por **grupo** (v0.11.0 solo zona); perfil completo por módulo+modo.

### 12.24 · F02 — Explicador de conflictos del bus

Hace **observable el arbitraje del SDHB**: una entidad `sensor` por **consumidor**
(cada VMC, cada persiana y DC en su self-bias), agrupadas bajo un **dispositivo
central** "Dynamic Home · Bus" (`(DOMAIN, "bus")`). El **estado** es el intent
ganador; los **atributos** explican el porqué: `source`, `priority`, `candidates`,
`reason`, `target`, `ttl_remaining_s` y el **aspirante** (`runner_up` +
`runner_up_priority`) — el segundo intent de mayor prioridad que pierde, sin la
lista completa de descartados. `hub.explain(targets, now_ts)` calcula todo (con
orden estable que coincide con `winner()`). Emite `dynamic_home_conflict` en cada
cambio de ganador (no cada ciclo). Solo estado actual (sin logbook).

**Aceptación:**

- ☑ La entidad de un consumidor muestra el ganador y el motivo
  (origen/prioridad/TTL/target + aspirante).
- ☑ Cada consumidor cuelga del dispositivo "Dynamic Home · Bus".
- ☑ `dynamic_home_conflict` se emite al cambiar el ganador.
- ☑ Solo estado actual; sin registro de historial.

### 12.25 · F06 — Energía (kWh) por módulo

Cada módulo (**VMC, DC y persianas**) expone un sensor de **energía** (`device_class:
energy`, `state_class: total_increasing`, `RestoreSensor`) que entra en el **panel
de Energía** de HA. La **potencia** sale de un **medidor real** si se configura el
campo opcional `power_meter`; si no, de una **estimación** (helper puro `energy.py`):
la VMC integra W por velocidad (`est_w_v1/v2/v3`), DC integra `est_w_on` mientras la
zona pide calor/frío (reaprovecha la señal de demanda real de F27), y la persiana
estima la energía **marginal por movimiento** del motor (`est_w_motor` × `full_travel_s`
× Δ%, porque un movimiento dura segundos y el muestreo a 60 s no lo capta). Solo
**energía** en este ciclo.

**Aceptación:**

- ☑ Con `power_meter`, el kWh integra la potencia real y aparece en el panel de Energía.
- ☑ Sin medidor, la estimación por estado/velocidad produce un kWh creciente coherente.
- ☑ El total sobrevive a reinicios (`RestoreSensor`) en los tres módulos.

**Diferido (anotado):** **coste (€)** (sensor de precio / tarifa fija, REQ-ENE-3);
**potencia instantánea / pico** (REQ-ENE-5, cruza F03); **medidor real en DS**.

### 12.26 · F15 — Sombreado geométrico real (DS)

Switch **opt-in "Geometric shading"** por persiana. Activo, la rama de protección
solar de verano (cooling + sol enfrentado + caluroso) deja el escudo fijo por
"impacto" y calcula la **penetración real del sol en el suelo** —`solar_penetration_m`
(alféizar `sill_height_cm`, alto de ventana, voladizo, azimut y `room_depth_m`)— y
`geo_shade_pos` baja la persiana **por pasos** (`shade_step_pct`) solo hasta proteger
`target_penetration_m`, con suelo en `summer_min_open_pct` (`reason: summer_solar_geo`,
`penetration_m` en `details`). Apagado (por defecto) o cuando el sol no procede →
**fallback** al escudo fijo `summer_solar_shield`. Lógica pura en `ds_engine`,
respeta `PROTECTED`/slew/bus como el resto de la cascada.

**Aceptación:**

- ☑ Con sol alto la penetración es menor que con sol bajo; el cierre se ajusta a ello.
- ☑ Penetración bajo el objetivo → no cierra (100 %); por encima → cierra por pasos,
  con suelo en el mínimo de verano.
- ☑ Con el switch apagado (o sin sol aplicable), comportamiento idéntico al actual
  (`summer_solar_shield`) — sin regresión.

**Diferido (anotado):** geometría aún más fina (luz difusa/reflejada) fuera de alcance.
