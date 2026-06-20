# Dynamic Home — Documento de Requisitos

> Derivado de `docs/BACKLOG.md` (ideas F01–F35, perfiladas con el usuario).
> **Versión 1 — Fase 0 (fundacionales) en detalle**; el resto, en el roadmap
> (§4) para expandir fase a fase. Prioridad por MoSCoW: **M** (Must) · **S**
> (Should) · **C** (Could). Cada requisito debe ser verificable.

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

> El detalle de Fases 1–4 se redactará al entrar cada fase, partiendo del
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

## 5. Trazabilidad

Cada requisito procede de una idea perfilada en `docs/BACKLOG.md` (misma
nomenclatura Fxx). Las decisiones de diseño y matices del usuario están en el
perfilado de cada Fxx; este documento las formaliza como requisitos verificables.

## 6. Pendiente de redactar
- Detalle de **Fases 1–4** (al entrar cada fase).
- **Criterios de aceptación** ampliados y casos de prueba por requisito.
- **Plan de migración** desde la suite YAML del usuario (coexistencia vía modo observación).
