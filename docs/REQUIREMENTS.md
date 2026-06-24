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

- **REQ-INS-1 (M):** asistente con flujo **Generador → Distribución → Emisión →
  (evaluar) → cargar presets + gating**. *(Implementado v0.16.0: 3 pasos; el de
  distribución se omite cuando el generador es siempre individual.)*
- **REQ-INS-2 (M):** modelo de **3 dimensiones** (catálogo cerrado), separando el
  generador del carácter central/individual:
  - **Generador:** aerotermia aire-agua, geotérmica, aire-aire (AC/split), caldera
    de gas, caldera de gasoil, caldera de biomasa/pellets, caldera de leña,
    eléctrica directa.
  - **Distribución:** **individual** vs **central compartida (comunitaria)**. La
    eléctrica directa y el aire-aire son **siempre individuales** (no se preguntan).
- **REQ-INS-3 (M):** **Emisión** (catálogo cerrado): suelo radiante, techo radiante,
  radiadores, toallero/zócalo, convectores, conductos (calor); radiante refrescante,
  fancoil, split, conductos (frío). Determina la **inercia** (afecta
  lead/freno/anti-ciclado).
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
- ☑ Al elegir generador+distribución+emisión se precargan defaults coherentes
  (editables luego). *(v0.16.0)*
- ☑ Con fuente comunitaria, F03/F09 no aparecen ni actúan. *(v0.17.0: F09 cableado
  al `compressor` del perfil; F03 al `peak`; ambos OFF en comunitaria.)*
- ☑ La inercia elegida cambia los defaults de lead/freno (y de anti-ciclado).
  *(v0.16.0)*

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
**Criterios de aceptación:** *(todos ☑ en v0.18.0; ver §12.32)*
- ☑ Con radiante+AC, el apoyo arranca solo cuando el primario no llega y se retira al recuperar.
- ☑ Conductos sin zonificar: una sola orden coherente para todas las zonas del ámbito.
- ☑ Conductos con rejillas: control por zona vía rejilla, unidad con consigna única.
- ☑ Conductos sin zonificar con Salón muy caliente y Dormitorio casi en consigna:
  la unidad **no** sobre-enfría el Dormitorio (la guarda corta al llegar a
  `consigna − margen`), aunque el Salón quede un poco corto.
- ☑ Subir el `zone_demand_weight` del Salón sesga la consigna agregada hacia él
  **sin** anular la guarda de undershoot del Dormitorio.
- ☑ Con rejillas motorizadas, ni la ponderación ni la guarda aplican (control por
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
- ☑ Estar quieto en el sofá NO marca la zona como vacía. *(v0.19.0: mmWave mantiene
  presencia; PIR no cuenta como movimiento para Vacía.)*
- ☑ Salir de casa (con la última zona vaciándose + puerta) pasa la casa a `Fuera`.
  *(v0.19.0: `away` necesita puerta reciente o móviles fuera, no inmovilidad.)*
- ☐ Con beacons BLE, el estado distingue **quién** está y en qué zona. *(BLE/identidad
  diferido al siguiente ciclo; ver §12.33.)*

*(Implementado v0.19.0: REQ-PRE-1/2/3/5/6/7/8 con PIR+mmWave+móvil+puerta y detección
de Durmiendo. **Diferido**: REQ-PRE-4 puerta direccional, identidad BLE/Bermuda, y la
publicación por bus / disparos directos por zona — ver §12.33.)*

*(F37 refinado v0.22.0: **histéresis de temporada** (anti-flapping del agua) +
**override de changeover por zona** (auto/heat/cool/off, auto hereda la casa) — ver
§12.34. Pendiente: per-zona con **sensor de agua propio** por colector.)*

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

### 4.7 · Changeover comunitario (F37)

**Objetivo:** en sistemas **comunitarios a 2 tubos** (suelo radiante con cambio
estacional), la **comunidad** envía agua caliente o fría a todo el edificio; el usuario
solo abre/cierra válvula y **no** controla la temperatura ni puede mezclar direcciones.
Una **dirección de casa (changeover)** debe gatear las zonas comunitarias.

- **REQ-CHG-1 (M):** **dirección de casa** `heat`/`cool`/`off` que las zonas
  **`community`** (F26 central_shared) **siguen**; las individuales mantienen su propia
  dirección.
- **REQ-CHG-2 (M):** detección **manual + auto**: selector `auto/heat/cool/off`; en
  `auto`, inferida de un **sensor de temperatura del agua de impulsión** con umbrales
  (≥ → calor, ≤ → frío, intermedio → reposo).
- **REQ-CHG-3 (M):** **opt-in / back-compat** — sin changeover configurado (sin sensor
  y manual `auto`), las zonas se comportan **igual que antes**.
- **REQ-CHG-4 (S):** observabilidad — selector + sensor de estado de casa; la zona
  refleja la dirección real (`hvac_action`).

**Dependencias:** F26 (community), F24 (entrada de Zonas). **Habilita:** control correcto
en instalaciones comunitarias de cambio estacional.
**Criterios de aceptación:**
- ☑ Una zona comunitaria "encendida" calienta o refresca según el agua del edificio,
  no según el modo que dejó el usuario. *(v0.20.0)*
- ☑ En entretiempo (agua templada) la zona reposa aunque esté "on". *(v0.20.0)*
- ☑ Sin changeover configurado, el comportamiento no cambia. *(v0.20.0; ver §12.34)*

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
- ☑ Pasar a `Eco` ensancha bandas (DC) y sube umbrales (DV) y suaviza el lead de
  forma observable (`_cfg()` cambia); `Equilibrado` restaura.
- ☑ Una zona puede mantener `Confort` mientras el resto está en `Eco` (override por
  zona); el modo `Eco` (F01) fija el preset económico con el mando en neutro.
  *(Implementado en v0.14.0; deltas integrados predecibles. Ver §12.28.)*

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
- ☑ Un cambio de tramo modifica la consigna base de DC; los biases siguen aplicando
  encima (`base_source: schedule`; absoluta, REQ-SCH-3; vacaciones ganan).
- ☑ El horario apaga la VMC en su tramo (`Off`) y fija un suelo de velocidad
  (`V1/V2/V3`), respetando silencio/modos. *(Implementado en v0.13.0; perfil por
  entrada, editor común; presencia REQ-SCH-5 = hook futuro. Ver §12.27.)*

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
  pico de arranque de DS importa, ~2000 W con 12 persianas). *(v0.26.0)*

**Dependencias:** F26 (gating DC), F27 (horas exactas), F03 (pico).
**Criterios de aceptación:**
- ☑ Con Shelly (`power_meter`), el kWh del módulo aparece en el panel de Energía.
- ☑ Sin medidor, la estimación por estado produce un kWh creciente coherente.
- ☑ Cada módulo expone su **potencia instantánea** (W) y Energy agrega la **potencia total de casa**. *(v0.26.0; `power_w` + `PowerSensor`/`HousePowerSensor`)*
- *(REQ-ENE-1/2/4 cubiertos en v0.12.0 para VMC/DC/DS; **coste (€)** REQ-ENE-3 en
  v0.24.0; **potencia instantánea** REQ-ENE-5 en v0.26.0.)*

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
- ☑ Con fuente comunitaria, el anti-pico ni aparece ni actúa (gateado por
  `peak`/`community` del perfil F26). *(v0.17.0)*
- ☑ Pedir N zonas eléctricas a la vez las arranca escalonadas, no simultáneas
  (presupuesto por nº de zonas o kW + ventana de escalonado). *(v0.17.0)*
- ☑ REQ-PIC-5: **prioridad de cola** por desviación (la zona más alejada de su
  consigna arranca primero bajo presupuesto ajustado) + **bypass de confort** (una
  desviación severa salta el límite). *(v0.23.0; ver §12.36)*
- *(REQ-PIC-4 cubierto: el escalonado aplica también a los arranques masivos de
  persianas.)*

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
- ☑ Con compresor, no se superan 6 arranques/h ni se viola el min OFF (sobre el
  **agregado** del compresor compartido; el flap de una zona no cuenta si otra lo
  mantiene encendido).
- ☑ Una orden anticondensación/ventana apaga aunque el min ON no se haya cumplido
  (seguridad cede). *(Implementado en v0.15.0, opt-in; **gating F26 cableado en
  v0.17.0**: solo participa con `compressor` del perfil, OFF en gas/eléctrico/
  comunitaria. Agrupación por compresor F25 diferida. Ver §12.29 y §12.31.)*

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
- ☑ Con solo medidor de red + precio, el módulo arranca y publica `import_headroom_w` y `tariff_state`. *(v0.21.0; contexto en `DATA_ENERGY`)*
- ☑ Sin entidades FV, los campos de excedente no se exponen ni rompen el arranque. *(v0.21.0; `surplus_w` ausente)*

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
- ☑ El total de casa coincide con la suma de los módulos. *(v0.24.0; `HouseEnergySensor` = Σ `energy_kwh`)*
- ☑ La energía agregada aparece correctamente en el panel de Energía. *(v0.24.0; `device_class: energy`, `total_increasing`)*
- ☑ Con sensor de precio, el coste **bruto** (€) acumula ΔkWh×precio. *(v0.24.0; `HouseCostSensor`, `monetary`, restaurado)*
- ☐ **Balance neto** (consumo vs red import/export y FV ⚠️) y coste neto. *(diferido, requiere FV)*

### 8.3 · Tarifa y precio (consolida F04)

**Objetivo:** traducir el precio (PVPC/Nordpool o tarifa plana) a un estado de
tarifa que el resto usa para desplazar cargas flexibles. (F04, descongelada aquí.)

- **REQ-TAR-1 (M):** acepta **sensor de precio** (variable) **o** precio/tramos
  **fijos** configurables; **agnóstico de integración** (RNF-6).
- **REQ-TAR-2 (M):** deriva `tariff_state` (barato/normal/pico) por umbrales
  configurables y lo publica al bus.
- **REQ-TAR-3 (S):** expone **horas baratas próximas** (ventana) para que DC/VE
  planifiquen pre-acondicionamiento/carga.
- **REQ-TAR-4 (C):** alimentar el Adaptive Lead de DC para precalentar en horas
  baratas y recortar la rampa en pico (era la idea de F04). *(v0.25.0)*

**Dependencias:** F34 núcleo. **Habilita:** desplazamiento de cargas, F04.
**Criterios de aceptación:**
- ☑ Con un sensor de precio, `tariff_state` cambia según los umbrales definidos. *(v0.21.0)*
- ☑ Sin sensor, los tramos fijos producen el mismo estado de forma determinista. *(v0.21.0)*
- ☑ DC ensancha el lead (preacondiciona) en tarifa barata y lo recorta en pico; sin módulo Energy, idéntico. *(v0.25.0; `tariff_lead_mult` + `tariff_bias`)*

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
- ☑ Al acercarse al ICP, `import_headroom_w` baja y las cargas no superan el límite. *(v0.21.0; el headroom aprieta el presupuesto de `PeakLoadHub`)*
- ☑ Con fuente comunitaria, el anti-pico no actúa. *(gateado por F26 en `_peak_step`)*

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

**Implementado después:** **coste (€)** en v0.24.0 (REQ-ENE-3, agregación de casa);
**potencia instantánea** en v0.26.0 (REQ-ENE-5: `power_w` por módulo + total de casa).
**Diferido:** **medidor real en DS** (muestreo 60 s vs movimiento de segundos).

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

### 12.27 · F21 — Programador semanal (DC + DV)

Editor de programación **común en estética**, con **perfil independiente por
entrada** (cada VMC su velocidad, cada zona DC su consigna): hasta **4 tramos/día**
por día de la semana, guardados en `entry.options[CONF_SCHEDULE]`
(`{"0":[{"start":"HH:MM","value":x}], …}`). Modelo puro `schedule.py`
(`active_value` con continuidad en medianoche). El editor reutiliza el patrón del
editor de zonas (menú de 7 días → form de 4 tramos + copiar-a-días/vaciar). Activado
por el switch **"Programador"** (DV reaprovecha el de horario; perfil vacío → on/off
simple legacy). Sensor diagnóstico "Programación".

- **DC:** el tramo fija la **consigna BASE absoluta** (`dc_engine.decide()`:
  `scheduled_base` reemplaza `base_active`); los biases se aplican encima; vacaciones
  ganan; sin atenuación nocturna sobre la programada.
- **DV:** el tramo fija velocidad/encendido base — `0` = off (`not_permitted`),
  `1/2/3` = **suelo** sobre la rama auto/IAQ (protegido de anti-flapping), cediendo a
  los caps de silencio (F12)/hostil/modo (F01).

**Aceptación:**

- ☑ Con un tramo activo, DC parte de la consigna programada (`base_source: schedule`)
  y los biases siguen encima; vacaciones la ignoran.
- ☑ Un tramo VMC a `Off` apaga; a `V2` sube el suelo de la velocidad automática y
  respeta el cap de horas de silencio.
- ☑ El editor de opciones persiste los tramos por día (y el "copiar a días"); cada
  entrada conserva su propio perfil.

**Diferido (anotado):** **hook de presencia** (F32 away/home ajustando sobre el plan,
REQ-SCH-5) — arquitectura preparada, efecto real → futuro; jerarquía completa
temporizado>horario>manual>modo con DS.

### 12.28 · F23 — Confort↔Economía (presets)

Un **mando por presets discretos** (`Eco / Equilibrado / Confort`) que escala de
forma **coherente** la agresividad en DC y DV a la vez. **Calca la maquinaria de
F01**: dos `select` en la entrada de Zonas — global ("Confort casa") + override por
zona ("Confort {zona}", `auto` hereda) — publicados en el blob `DATA_MODE` y
resueltos por ámbito (`comfort.effective_from_published`, vía `zones.scope_for_module`).
Modelo puro `comfort.py`. Los presets son **deltas integrados y predecibles** (no
editables, REQ-CMF-1), aplicados en runtime en `coordinator_*._cfg()` tras
`apply_options`:

- **DC eco**: banda más ancha (`base_heat_day −0.7`, `base_cool_day +0.7`),
  `delta_night +0.3`, lead más suave (`lead_base_h`/`trend_lead_h ×0.6`),
  `apply_min_delta +0.2`. **DC confort**: lo contrario (banda más estrecha, lead más
  agresivo). **DV eco**: ventila menos (`co2_v2/v3 +150`, `pm` arriba, `co2_hys +50`);
  **DV confort**: umbrales a la baja (manteniendo el orden v3>v2). `Equilibrado` =
  identidad.
- **Enlace F01 (REQ-CMF-4)**: con el mando en `Equilibrado` y el modo de la casa en
  `Eco`, se sigue el preset económico; una elección explícita del mando manda.

**Aceptación:**

- ☑ `Eco` ensancha la banda de DC y sube los umbrales de DV de forma observable;
  `Equilibrado` restaura los valores por defecto.
- ☑ Override por zona: una zona en `Confort` con el resto en `Eco`.
- ☑ El modo `Eco` (F01) aplica el preset económico con el mando en neutro.

**Diferido (anotado):** deltas **editables** por el usuario (ahora fijos); defaults
por instalación (F26); efecto del preset en DS (persianas).

### 12.29 · F09 — Anti-ciclado corto (DC)

Protección de compresor **opt-in** (switch "Anti short-cycle" por zona de clima)
con **min ON**, **min OFF** y **máx arranques/hora** (default 6). En aerotermia/bomba
de calor el **compresor es compartido**, así que el guard opera sobre el **agregado**:
un único `AntiCycleHub` en `hass.data` (como el SDHB) al que cada zona reporta su
demanda; un arranque = primera zona ON con todas apagadas, una parada = última que se
apaga. Así el flapping de una zona **no cuenta como arranque** si otra mantiene el
compresor despierto. Modelo puro `anticycle.py` (`CompressorState` + `step` +
`AntiCycleHub`). Vigila el ON/OFF que **DC manda** al termostato; cuando el agregado
retiene un arranque (`anticycle_min_off_hold` / `anticycle_max_starts_hold`) o sostiene
el min ON (`anticycle_min_on_hold`), la zona conduce el termostato real a **OFF**
(`climate.py._apply`). **La seguridad manda** (`anticycle_safety_off`): condensación/
ventana/override fuerzan OFF aunque no se cumpla el min ON. Observabilidad:
`anticycle_hold`/`anticycle_reason` en los atributos del `climate`.

**Aceptación:**

- ☑ Min OFF y máx arranques/h retienen el arranque del compresor (la zona se conduce
  a OFF mientras está retenida).
- ☑ El agregado evita falsos arranques: con la zona B activa, la zona A que apaga y
  vuelve a pedir no añade un arranque nuevo.
- ☑ Una parada de seguridad (condensación/ventana) cede el min ON y apaga.
- ☑ Opt-in: con el switch apagado la zona no participa en el agregado (sin efecto).

**Sin fairness por zona aquí (por diseño).** F09 es un guard **agregado y mecánico**: al
alcanzar `max_starts_per_h` todas las zonas que demandan reciben `anticycle_max_starts_hold`
**por igual**, sin ordenar por desviación. El reparto por prioridad — que arranque primero
la zona más alejada de consigna — vive en **F03/peak** (§12.31), no en F09. F09 responde
"¿puede el compresor compartido cambiar de estado ahora?"; F03 responde "¿qué zona arranca
cuando los arranques escasean?". No esperes orden por desviación en este módulo.

**Diferido (anotado):** **gating por instalación** (F26: oculto en gas/eléctrico/
comunitaria, activo con compresor); usar la **tasa aprendida** para autodimensionar min
ON/OFF. *(La agrupación fina por compresor `compressor_id` se entregó en v0.27.0.)*

### 12.30 · F26 — Tipo de instalación (capa de declaración)

Declaración **por zona DC** de la instalación en **3 dimensiones independientes**
(modelo puro `install.py`, sin imports de HA): **Generador** (aerotermia aire-agua,
geotérmica, aire-aire/AC, calderas de gas/gasoil/biomasa/leña, eléctrica directa) ×
**Distribución** (individual / central compartida) × **Emisión** (suelo/techo
radiante, radiadores, toallero, convectores, conductos calor/frío, radiante
refrescante, fancoil, split). El central/individual es una **dimensión aparte** del
generador: gas, pellets, gasoil y aerotermia pueden ser centrales o individuales; la
eléctrica directa y el aire-aire son **siempre individuales** (el asistente omite el
paso de distribución, `install.forced_individual`).

De la terna se deriva un **perfil** (`install.profile`):
`community` = distribución central compartida (solo se abre válvula); `compressor` =
generador con compresor (aerotermia/geotérmica/aire-aire) **e individual** (F09);
`peak` = carga eléctrica individual —eléctrica directa o bomba de calor— (F03). Las
**combustiones** (gas/gasoil/pellets/leña) nunca activan `compressor`/`peak`.

Elegir la terna **precarga defaults** coherentes por **inercia**
(`install.defaults`): alta inercia → más lead (`lead_base_h`/`trend_lead_h`↑) y
anti-ciclado más largo (`anticycle_min_on_s`/`_min_off_s`↑); baja inercia → al revés.
Solo emite claves válidas de `options_spec` (test guarda) y se mergea en
`entry.options` (editable luego). El asistente vive en el options-flow de clima
(`async_step_install` → `install_dist` → `install_emission`), guarda
`CONF_GENERATOR`/`CONF_DISTRIBUTION`/`CONF_EMISSION`, y un **sensor diagnóstico**
"Instalación" expone la terna (estado) y los flags (atributos). El coordinator
expone `has_install()` + `install_profile`. **No** se cablea aún F09/F03 al perfil.

**Aceptación:**

- ☑ Al elegir generador+distribución+emisión se precargan defaults coherentes por
  inercia (editables luego) y solo con claves válidas de `options_spec`.
- ☑ La inercia elegida cambia los defaults de lead/freno/anti-ciclado.
- ☑ El perfil expone `community`/`compressor`/`peak` correctos (comunitaria sin
  compresor/pico; aerotermia individual con ambos; combustión sin ninguno; eléctrica
  con pico y sin compresor).

**Diferido (anotado, orden del usuario):** **cablear F09** al perfil ✅ (v0.17.0);
**F03** ✅ (v0.17.0); **F25** emisores (primario/stage2/ámbito) dentro del asistente;
opción **"personalizado"** (REQ-INS-7).

### 12.31 · F09 (gating) + F03 — Anti-pico / reparto de cargas eléctricas

**F09 cableado al perfil F26** (`coordinator_dc._anticycle_step`): la protección de
compresor solo participa en el agregado cuando el perfil declara `compressor`
(aerotermia/geotérmica/aire-aire **individual**); en gas/eléctrica directa/comunitaria
queda **OFF** aunque el switch esté activo. Sin instalación declarada se mantiene el
opt-in legacy (compatibilidad).

**F03 (anti-pico / load staging)** — árbitro puro `peak.py` (`PeakLoadHub`) a nivel
casa, espejo del `AntiCycleHub`. Limita los **arranques simultáneos** y los **escalona**
para no disparar el ICP. Dos canales independientes en `hass.data`:
`_peak_dc` (cargas **sostenidas** de calefacción eléctrica: el slot vive mientras la
zona demanda) y `_peak_ds` (inrush **transitorio** de motores de persiana: pulso que
expira tras el recorrido). Cada participante reporta su demanda por ciclo y el hub
decide si puede **arrancar** ahora; lo ya en marcha nunca se interrumpe.

- **Presupuesto**: por **nº de cargas** simultáneas (`peak_max_zones`) o por **vatios**
  (`peak_max_power_w > 0`, medidor real o estimación `est_w_on`/`est_w_motor`).
- **Escalonado** (`peak_stagger_s`, ~10 s): un arranque nuevo se difiere hasta esa
  ventana tras el anterior, de modo que una ráfaga sube de uno en uno.
- **Gating F26 (clima)**: solo se engancha con `peak` del perfil (eléctrica directa o
  bomba de calor individual) y **no** comunitaria; opt-in (switch "Peak limiting").
  Una zona ya retenida por F09 no consume slot de pico.
- **DS (REQ-PIC-4)**: opt-in por persiana; cuando el presupuesto/escalonado difiere un
  movimiento, la persiana **mantiene su posición** ese ciclo y reintenta al siguiente
  (el slew sigue dando forma al movimiento cuando se permite).
- Observabilidad: `peak_hold`/`peak_reason` en los atributos del `climate`;
  `peak_reason`/`peak_deferred_pos` en los del `cover`.

**Aceptación:**

- ☑ Con fuente comunitaria, ni F09 ni F03 actúan (gateados por el perfil).
- ☑ N zonas eléctricas pidiendo a la vez arrancan escalonadas (la 2ª se difiere por
  presupuesto/escalonado).
- ☑ El escalonado aplica también a persianas (arranques masivos diferidos).

**Prioridad de cola + bypass de confort (REQ-PIC-5):** hechos en v0.23.0 (ver §12.36).
**Diferido (anotado):** **presupuesto único de casa** en la entrada de Zonas (hoy por
entrada, como F09); agrupación fina por compresor (F25).

### 12.32 · F25 — Emisores y staging (multi-emisor + conductos compartidos)

Una zona DC mantiene **un solo cerebro** (`dc_engine.decide` intacto) pero puede
conducir **1..N emisores**. El staging y la reconciliación son **post-decisión**
(consumen `decision.target` + `indoor_temperature()`); **sin** lista `emitters` la zona
se comporta **idéntica a antes** (single-device, REQ-EMI-7).

**Modelo (`emitters.py`, puro):** lista en `entry.options["emitters"]`; cada emisor
declara su terna F26 (reusa `install.py`), el dispositivo real que conduce —
**`climate` y/o `switch`/válvula** — su rol por modo (`primary_heat/cool`), y para
conductos su `scope` (`zone`/`group_unzoned`/`group_grilles`), `shared_emitter_id`,
`owner` y `policy`. `primary_for(hvac)` con fallback al único emisor con dispositivo.

**Fase A — staging primario/apoyo (`staging.py`, puro):** el primario lleva la consigna;
cada apoyo arma cuando la desviación en la dirección activa supera `support_dev_on`
durante `support_confirm_min` y se retira con histéresis (`support_dev_off` /
`support_release_min`) — calca el debounce de `_infer_window`. `coordinator_dc.
_build_emitter_commands` mapea la decisión a `emitter_commands` (id→{mode,target,on});
un hold de F09/F03 o modo off apaga todos; un emisor **switch sin termostato** sigue la
demanda real (`_valve_demand`). `climate.py._apply_emitters` conduce cada dispositivo
(`climate.*` o `homeassistant.turn_on/off`), con el mismo anti-jitter por emisor; el
camino legacy single-device queda **intacto**.

**Fase B — conductos compartidos (`shared_emitter.py`, puro + `SharedEmitterHub`):**
hub de casa en `hass.data["_shared_emit"]` (espejo de `PeakLoadHub`), canal por
`shared_emitter_id`. Cada zona hermana publica su `ZoneDemand`; el **dueño** (declarado,
o fallback determinista = menor entry_id) reconcilia y conduce la unidad, los demás se
apartan. `aggregate_setpoint` por política (**ponderada** default = media de consignas
ponderada por `weight × max(desviación,ε)`; `mean`/`priority`/`worst_stuck`),
`undershoot_cut` (REQ-EMI-8: corta cuando la zona **más satisfecha** llega a
`consigna ∓ shared_undershoot_margin`); con **rejillas** la unidad va al setpoint
más exigente y la guarda no aplica (cada rejilla regula su caudal). Hermanas vía
`zones.scope_for_module` + `DATA_ZONES` (canal por defecto = id del grupo).

**Opciones:** categorías `staging` (`support_*`) y `shared` (`zone_demand_weight`,
`shared_undershoot_margin`) en `options_spec`; editor de emisores en el options-flow
(espejo del editor de Zonas). Observabilidad: `emitter_commands` (con `shared`/`reason`).

**Aceptación:** las 6 casillas de §4.3 ☑. **Tests:** puros `test_emitters` /
`test_staging` / `test_shared_emitter` + integración (apoyo arma/retira; legacy intacto;
conducto compartido reconcilia una orden y la guarda corta; editor añade/borra). Suite
371→398.

**Gating de compresor por-emisor (F09):** hecho **acotado** en v0.23.0 (hold solo a
emisores de bomba de calor) y **completo** en v0.27.0 — cada emisor declara su
`compressor_id` y el `AntiCycleHub` corre **un `CompressorState` por canal**, de modo
que dos bombas de calor independientes no se interfieren (default `"default"` = un solo
compresor de casa, back-compat). Ver §12.36. **Diferido (anotado):** reordenar/duplicar
emisores avanzado.

### 12.33 · F32 — Presencia (fusión por zona + estado de casa)

La presencia vive en la **entrada singleton de Zonas** (junto a modos F01 y confort
F23). Modelo puro `presence.py`: cada zona fusiona las **entidades del usuario**
(RNF-6) — **PIR** (rápido, hold corto), **mmWave** (sostenido, hold largo: mantiene
presencia durante la inmovilidad) y **contacto de puerta** — en **Ocupada/Vacía**, y
la casa en **`occupied`/`away`/`sleeping`**.

- `zone_occupied(state,cfg,now)`: Ocupada mientras alguna fuente de movimiento esté
  **fresca** dentro de su timeout por tipo; pasa a Vacía solo tras un **debounce**
  (`empty_confirm_s`) con todo obsoleto → estar quieto bajo mmWave **no** marca Vacía
  (REQ-PRE-3). Calca el latch de `staging.py`.
- `house_state(...)`: **`away`** solo si **ninguna** zona ocupada **y** (puerta
  reciente dentro de `away_door_window_s` **o** móviles fuera) — nunca por mera
  inmovilidad (REQ-PRE-5). **`sleeping`** si ocupada, dentro de la **ventana nocturna**
  y **sin movimiento PIR** reciente (REQ-PRE-6; el mmWave da ocupación, el PIR da
  movimiento). Si no, **`occupied`**.

El `ZonesCoordinator` registra **listeners** sobre las fuentes y **sondea**
(`UPDATE_INTERVAL_S`) cuando hay presencia configurada, recomputa y **publica
`DATA_PRESENCE`** (`{house, zones, reasons}`) + evento `EVENT_PRESENCE_CHANGED`. Con
**auto-pilotaje** (`CONF_PRESENCE_AUTO`) mapea el estado al **modo F01 de la casa**
(`occupied→home`/`away→away`/`sleeping→sleep`) por el eje home/away/sleep — **nunca
pisa un Boost/Eco manual** (manual > auto, RNF-3). Entidades: **binary_sensor de
ocupación por zona** (con fuentes) + **presencia de casa** (`device_class=occupancy`),
acuñadas iterando el árbol como los selects F01. Editor en `ZonesOptionsFlow`
(`presence` → `presence_house`/`presence_zone` → `presence_zone_detail`), funciona con
**subconjuntos** de fuentes (REQ-PRE-8). Defaults en `PresenceConfig` (RNF-1).

**Aceptación:** §4.4 — sofá-quieto ☑, salida→Fuera ☑; identidad BLE ☐ (diferida).
**Tests:** puro `test_presence.py` (mmWave hold, debounce, away requiere señal,
sleeping en ventana sin PIR, subconjuntos) + integración (publica DATA_PRESENCE,
entidades, auto-away conduce DATA_MODE, no pisa Boost). Suite 398→411.

**❌ Descartado (decisión del usuario, v0.23.0):** la **puerta direccional** por orden
de eventos (REQ-PRE-4) y la **identidad BLE dedicada** ("quién") **no se implementarán**.
La presencia se queda con sensores de presencia/movimiento/móvil/puerta-simple. **Bermuda
NO se descarta**: si expone un `binary_sensor` de ocupación por zona, se enchufa en las
casillas de fuente existentes (mmWave/PIR) sin código nuevo.
**Diferido (anotado):** **publicación por bus** (hoy `DATA_PRESENCE`) y **disparos
directos de setback por zona** (REQ-PRE-7, hoy vía auto-modo).

### 12.34 · F37 — Changeover comunitario (modo estacional de agua)

Sistemas **comunitarios a 2 tubos**: el edificio manda agua caliente o fría a todos por
temporada; el usuario solo abre válvula. Una **dirección de casa** gatea las zonas
`community`. Vive en la entrada de **Zonas** (como F01/F32) y **reusa el poll/listeners
de F32**.

Modelo puro `changeover.py`: `resolve(manual, water_temp, cfg)` → `heat`/`cool`/`off`/
`None`. `manual` ∈ {heat,cool,off} **fuerza**; `auto` infiere del **sensor de agua de
impulsión** (`≥ heat_above_c` → heat; `≤ cool_below_c` → cool; intermedio → off);
**sin sensor en auto → `None`** (sin gating, back-compat). El `ZonesCoordinator` resuelve
y **publica `DATA_CHANGEOVER`** `{state,manual,water_temp}` + evento, y avisa a los
módulos DC. Entidades en Zonas: **select** `auto/heat/cool/off` (`ChangeoverSelect`,
restaurado) + **sensor** de estado (`ChangeoverSensor`, ENUM).

Consumo en DC (`coordinator_dc._effective_hvac`): si la zona es **`community`** y hay
changeover (`state` ≠ None), su dirección efectiva la fija el edificio — `off` si la
zona está off, si no `state` (heat/cool) o `off` en entretiempo. Esa dirección efectiva
entra en `DcInputs.hvac_mode` (decisión) y en `_build_emitter_commands` (rol del emisor
por modo). El **motor `decide` no se toca**. La tarjeta muestra `hvac_action`
(heating/cooling/idle/off) real. Zonas individuales o sin changeover → comportamiento
idéntico.

**Aceptación:** §4.7 — las 3 casillas ☑. **Tests:** puro `test_changeover.py` +
integración (zona community sigue el agua: cool/heat/off; individual ignora; sin config
= back-compat; `DATA_CHANGEOVER` desde sensor + override manual; entidades). Suite
411→420.

**Refinamiento v0.22.0:** **histéresis de temporada** — `changeover.resolve(...,prev)`
mantiene la dirección hasta que el agua cruza el umbral menos `hysteresis_c` (anti-flap);
`ZonesCoordinator` pasa `prev=self.changeover`. **Override de changeover por zona** —
`changeover.effective(house, override)`; selector por zona `auto/heat/cool/off` (espejo
del override de modo F01), publicado en `DATA_CHANGEOVER["zones"]`; DC resuelve su zid vía
`zones.scope_for_module` y usa el override o el estado de casa.

**Exponer a DS (v0.28.0):** `coordinator_ds._hvac_mode` cae al **changeover de casa**
(`_house_changeover`, espejo del de DC: override por zona vía `zones.scope_for_module`,
si no el estado de casa) cuando la persiana no tiene termostato propio activo. Así una
instalación comunitaria sin `climate` por persiana hace **escudo solar / free-cooling en
verano** y **ganancia solar / aislamiento nocturno en invierno** siguiendo la temporada
del edificio. Sin changeover configurado → `off` (back-compat exacto). Un termostato por
persiana que pide heat/cool gana; idle/off cae al changeover.

**Exponer a DV (v0.29.0):** `coordinator_dv` lee el mismo `_house_changeover` y pasa
`heating_season` al motor; `compute_freecool` **suprime el free-cooling en temporada de
calor** (un día templado de invierno —dentro 21°, fuera 12°— activaría free-cooling por
la histéresis de temperatura y tiraría el calor que pagas). Sin changeover → no es
temporada de calor (back-compat: free-cooling solo por temperatura).

**Aviso de Repairs cuando falta el changeover (v0.30.0, F07):** como el fallback "sin
changeover → no es temporada de calor" deja el riesgo en pie para quien no lo configure,
`coordinator_dv._freecool_changeover_advisory` levanta un issue **no-fixable** cuando
coinciden las tres condiciones: **free-cooling activo** + **alguna zona DC en calor** +
**sin changeover**. Se borra solo en cuanto cae cualquiera (configuras changeover, apagas
free-cooling, o ninguna zona calienta). Solo dispara con evidencia de calefacción → no
molesta a climas solo-frío. Issue `freecool_no_changeover`.

**Diferido (anotado):** **changeover por zona/grupo con sensor de agua propio** (varios
colectores con resolución auto independiente); `HVACMode.HEAT_COOL` como modo "seguir al
edificio".

### 12.35 · F34 — Módulo Dynamic Energy (núcleo + tarifa + anti-pico)

Módulo **singleton** nuevo (`MODULE_ENERGY`, como Zonas/Meteo) que **publica contexto
energético de casa** y **no comanda** (RNF-3/4). Vive con su coordinator + motor puro,
patrón DC/DV/DS. **§8.5 FV** y **§8.6 VE** diferidos (⚠️ sin validación del autor); los
campos PV quedan *present-but-gated*.

Modelo puro `energy_engine.py` (sin HA): `tariff_state(price|None, cfg)` (umbrales
€/kWh; precio None → tarifa fija determinista, REQ-TAR-1/2); `import_headroom(grid_w|None,
cfg)` = `max(floor, contratada-grid)` (None sin medidor → degrada); `surplus(pv,cons)`
(None sin FV → gated); `scarcity(tariff,surplus)` (pico **y** sin excedente);
`resolve_context(inputs,cfg)` ensambla el blob (omite `surplus_w` sin FV). `EnergyConfig`
con `contracted_w`/`cheap_below`/`peak_above` (defaults RNF-1).

`coordinator_energy.py` (patrón `coordinator_weather`/listeners de F32): lee las entidades
del usuario (red import, precio, opc. FV/consumo), resuelve y **publica `DATA_ENERGY`**
`{tariff_state, import_headroom_w, contracted_w, [surplus_w], scarcity}` + evento, avisa a
los consumidores en cambios materiales. Entrada **singleton** en el menú de alta; opciones
por categoría `tariff` (umbrales) vía `options_spec`. Sensores: **Margen de red** (W,
power; sin medidor → atributo "n_loads"), **Tarifa** (ENUM), **Excedente FV** (gated por
FV) + binary **Escasez**.

**Consumidor (§8.4, consolida F03):** en `coordinator_dc._peak_step`, si hay
`import_headroom_w` (medidor de red) el **presupuesto de pico** pasa a vatios =
headroom (apretado por el cap estático, nunca aflojado); sin medidor → vatios estáticos
o **N cargas** (REQ-EPK-1). Sigue gateado por `peak_enabled` + `profile["peak"]` (OFF en
comunitaria, REQ-EPK-3); **solo baja un presupuesto** que el `PeakLoadHub` ya arbitra → ni
comando ni mecanismo nuevo, la seguridad manda.

**Aceptación:** §8.1/§8.3/§8.4 ☑. **Tests:** puro `test_energy_engine.py` (tarifa fija/
sensor, headroom +/clamp/None, escasez, subconjuntos) + integración (publica `DATA_ENERGY`
con solo red+precio; sin FV → `surplus_w` ausente y sin sensor; tarifa fija determinista;
headroom pequeño aprieta el pico de una zona DC eléctrica). Suite 420→431.

**§8.2 (v0.24.0):** el coordinator de Energy **agrega** `energy_kwh` de cada coordinator
de módulo (DC/DV/DS, F06) en `house_kwh` y, con sensor de precio, acumula `house_cost`
integrando ΔkWh×precio (coste **bruto**, `energy_engine.add_cost`, ΔkWh negativo no resta;
el primer ciclo solo siembra el previo para no contar los kWh restaurados). Sensores:
`HouseEnergySensor` (siempre, `energy`/`total_increasing`→panel de Energía, REQ-EAG-1/2) y
`HouseCostSensor` (gateado al precio, `monetary`/`total`, restaurado). `house_kwh`/
`house_cost` también en el blob `DATA_ENERGY`. **Aceptación §8.2** ☑ (balance **neto** con
FV diferido). **Tests:** puro `add_cost` + integración (suma de módulos; coste acumula
Δ×precio; sin precio → sin sensor de coste). Suite 441→445.

**Diferido (anotado):** **§8.5 FV/excedente** y **§8.6 carga VE** (⚠️ validación externa);
**§8.2 balance neto** (consumo vs red import/export y FV ⚠️) y coste neto; **DS** respetando headroom; afinar la
contabilidad del headroom (incremental vs absoluto). *(La potencia instantánea total
REQ-ENE-5 se entregó en v0.26.0: `house_power_w` en `DATA_ENERGY` + `HousePowerSensor`.)*

**§8.3 sesgo de tarifa en DC (v0.25.0, REQ-TAR-4):** DC lee `tariff_state` de
`DATA_ENERGY` (helper `_tariff_state`, como ya lee el headroom) y lo pasa a `DcInputs`.
En el motor puro: `tariff_lead_mult` multiplica el lead de anticipación (barato ×1.5 →
preacondiciona antes; pico ×0.6 → recorta la rampa cara; acotado a `[lead_min_h,
lead_max_h]`), y `tariff_bias` añade un sesgo de base opcional (`tariff_bias_c`, 0=off;
barato carga masa, pico se deja llevar). Solo actúa con `tariff_state` ∈ {cheap, peak};
sin módulo Energy = idéntico (back-compat). Tunables en la categoría `tariff_bias`.
Tests puros + integración (lead barato > neutro > pico). Suite 445→449.

### 12.36 · F03 prioridad/bypass + F09 compresor por-emisor (refinamientos)

**F03 prioridad de cola (REQ-PIC-5):** `PeakLoadHub` lleva un libro de **waiters**
`{entry_id→(priority,ts)}` (poda por ventana). `evaluate(...)` acepta `priority`: un
arranque que cabe en el presupuesto **cede** (`peak_yield`) a un waiter de mayor
prioridad visto en la ventana → la zona **más alejada de su consigna** arranca primero.
Best-effort (cada coordinator corre en su propio timer; converge en uno o dos ciclos).
DS intacto (sin `priority` → 0.0 → FIFO). **F03 bypass de confort:** en
`coordinator_dc._peak_step`, `dev = staging.deviation(action, t_int, target)`; si
`dev ≥ cfg.peak_comfort_bypass_c` (°C, def. 2.5; 0=off) la zona **salta el gate**
(`peak_hold=False`, reason `peak_comfort_bypass`) — el confort gana al recorte; la
seguridad sigue ganando por encima. En caso normal pasa `priority=dev` al hub.

**F09 compresor por-emisor (acotado):** sin cambios en `anticycle.py`. En
`_build_emitter_commands` el `held` se calcula **por emisor**: OFF/seguridad y `peak_hold`
gatean **todos**; el `anticycle_hold` (compresor) **solo** los emisores de bomba de calor
(`em["generator"] in install.HEATPUMPS`, con fallback al perfil de zona si el generador
está vacío → legacy/single-emisor intacto). Así, en una zona aerotermia + caldera de gas,
el guard de compresor retiene el emisor de bomba pero el de gas sigue calentando.

**Tests:** puro `test_peak.py` (prioridad concede al más desviado y robusto al orden;
`peak_yield`; caducidad de waiters; sin priority = FIFO) + integración (bypass de confort
salta el presupuesto; F09 por-emisor: bomba off / gas on con anti-ciclado). Suite 436→441.

**Nota F32:** la **puerta direccional** y la **identidad BLE dedicada** quedan
**descartadas** (ver §12.33).

**§12.37 · F09 canal de compresor completo (v0.27.0):** cada emisor declara su
`compressor_id` (`emitters.normalize`, default `"default"`). El `AntiCycleHub` pasa a ser
**multi-canal** (`evaluate(..., channel=...)`, `participates`, `clear` en todos los
canales) con un `CompressorState` por canal. `coordinator_dc._anticycle_step` reporta la
demanda de la zona a cada canal de sus emisores de bomba de calor y guarda
`_channel_holds`; `_build_emitter_commands` retiene cada emisor por **su** canal. Dos
bombas de calor independientes ya no se interfieren; `"default"` preserva el compresor
único de casa (back-compat, single-device intacto). Editor: campo `compressor_id` por
emisor. Tests puros (canales independientes; `participates`/`clear`) + integración (dos
bombas en `hp_a`/`hp_b`, una bloqueada retiene solo su emisor). Suite 451→454.
