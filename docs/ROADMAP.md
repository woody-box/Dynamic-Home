# Dynamic Home — Roadmap de implementación

> Plan de fases derivado del [BACKLOG](BACKLOG.md). **Documento vivo, no es
> compromiso de fechas.** Ordena las features ya *perfiladas* por
> **dependencias → valor → esfuerzo**. Proceso por feature (cabecera del
> BACKLOG): *perfilada → documento de requisitos (`REQUIREMENTS.md` / `SPEC_*`)
> → tests → implementación*.

**Esfuerzo:** S (pequeño) / M (medio) / L (grande) · **Valor:** Alta / Media / Baja

## Estado actual (v0.98.0)
- **Todas las fases de features (0–5) están entregadas** salvo la parte diferida de
  Energía (ver abajo). Las fundacionales (F24/F26/F32/F37) y los módulos nuevos
  (Weather, Energy) ya viven en el código.
- **Auditoría integral cerrada (v0.94.2 → v0.98.0).** Cuatro fases —seguridad,
  coherencia frío/calor, fiabilidad y pulido— más el tope de viento desde el proveedor
  (v0.97.1) y el módulo **«Dynamic Shutter · Común»** con interruptores globales de
  persianas (v0.98.0). El detalle y los criterios de aceptación viven en
  [REQUIREMENTS.md → «Auditoría integral»](REQUIREMENTS.md).
- **Pendientes anotados** (sin cambio de comportamiento, requieren decisión del usuario):
  - **Debounce/tolerancia configurable** de la detección de movimiento externo del cover
    (asentamiento antes de tratar un movimiento como override manual).
  - **Switch dedicado «solo viento»** en DS (separar el tope por viento del resto de
    protecciones meteo, hoy agrupadas).
  - **Parte diferida de Energía (F34):** FV/excedente (§8.5), carga del VE (§8.6) y
    balance neto — **no testable por el autor** (sin placas/batería/wallbox) → validación
    externa. El anti-pico de red, coste/consumo y tarifa ya están entregados.

## Principios de ordenación
1. **Quick wins primero** (S, sin dependencias, sobre código existente) para fijar
   el ritmo *requisitos→tests→código* y dejar infra reutilizable (eventos, Repairs).
2. **Mejoras autónomas** por módulo que no necesitan las fundacionales.
3. **Fundacionales** (L) cuando aporten desbloqueo: primero la que abre más features.
4. **Módulos nuevos** (Weather, Energy) al final, por tamaño y testabilidad.

## Mapa de dependencias (resumen)
- **F26** (tipo de instalación) → desbloquea **F03**, **F09**, **F25**.
- **F24** (zonas) → desbloquea el *ámbito por grupo* de **F01**, **F21**, **F23**.
- **F32** (presencia) → alimenta **F01**, **F21** (hook), setback de DC/DV.
- **F33** (weather) → mejora **F17**, forecast de DC, free-cooling.
- **F10** (eventos) → usado por **F07**, **F08**, **F02**, **F01**, **F14**.
- **F13** (secado rocío) → lo dispara **F22** (moho). **F11** → lo reutiliza **F35**.
- **F34** (Energy) → consolida **F03**, **F04**, **F06**.

---

## Fase 0 · Plataforma e infraestructura (quick wins)
> Todo **S**, sin dependencias externas, sobre código ya existente. Deja la
> fontanería (eventos, Repairs, observabilidad del bus) que reutilizan las demás.

| Orden | ID | Feature | Valor | Esf. | Apoyo existente |
|---|---|---|---|---|---|
| 1 | **F10** | Servicios y eventos nativos (eventos primero) | Media | S | capa de acciones; base de avisos |
| 2 | **F07** | HA Repairs sobre `degraded` | Alta | S | `binary_sensor degraded`; evento opcional de F10 |
| 3 | **F02** | Explicador de conflictos del bus | Alta | S | `SdhbHub` (source/intent/priority/ttl) |
| 4 | **F08** | Vida del filtro VMC | Media | S | `filter_hours`; aviso vía Repairs (F07) |

**Sprint recomendado para arrancar:** F10 → F07 → F02 → F08.

---

## Fase 1 · Mejoras autónomas por módulo
> No necesitan F24/F26/F32/F33. Alto valor entregable de forma incremental.
> Sub-fases por módulo; dentro, orden por valor.

### 1a · DV (ventilación)
| Orden | ID | Feature | Valor | Esf. | Notas |
|---|---|---|---|---|---|
| 1 | **F13** | Secado por punto de rocío (`dp_diff`) | Alta | M | mejora del `dry_mode`; `dp_diff` ya se calcula |
| 2 | **F11** | Ventilación anticipatoria (derivada CO₂/PM) | Media | M | patrón ducha (on/off + hold) sobre EMAs |
| 3 | **F12** | Horas de silencio (cap nocturno) | Media | S | excepción crítica de seguridad |
| 4 | **F28** | Eficiencia del recuperador | Media | S | 3 sondas; inferencia de bypass |
| 5 | **F30** | IAQ extendido (VOC informativo, exteriores) | Media | M | actúan solo CO₂/PM2.5 |
| 6 | **F14** | Boost V3 temporizado | Baja | S | trivial vía servicio (F10) |
| 7 | **F35** | Campana extractora coordinada | Media | S | reutiliza F11 → va después |

### 1b · DC (clima)
| Orden | ID | Feature | Valor | Esf. | Notas |
|---|---|---|---|---|---|
| 1 | **F27** | Señal de demanda/válvula real opcional | Media-Alta | S | mejora Adaptive Lead; convive con backup HW |
| 2 | **F20** | Detección de ventana abierta | Media | M | sensor real + fallback por caída de temp |
| 3 | **F22** | Índice de moho | Media | S | dispara F13 → va después de F13 |
| 4 | **F31** | Espacio adyacente (terraza/galería) | Media | M | advisory; requiere sensor del adyacente |

### 1c · DS (persianas)
| Orden | ID | Feature | Valor | Esf. | Notas |
|---|---|---|---|---|---|
| 1 | **F15** | Sombreado geométrico real ("X m de suelo") | Alta | L | fallback a % fijo si faltan datos |
| 2 | **F16** | Aislamiento nocturno estacional | Media | S | por modo del climate; coordina free-cooling |
| 3 | **F17** | Avisos meteo (tormenta/granizo) | Media | M | `binary_sensor` genérico; F33 lo mejora luego |
| 4 | **F19** | Apertura gradual al amanecer | Baja | M | opt-in por zona |

---

## Fase 2 · Fundacional A — Tipo de instalación
> **F26** desbloquea las features pesadas de DC. Se implementa la fundacional y,
> a continuación, lo que gatea.

| Orden | ID | Feature | Valor | Esf. | Dependencia |
|---|---|---|---|---|---|
| 1 | **F26** | Asistente fuente→emisión + gating + presets | Alta | M-L | base de F03/F09/F25 |
| 2 | **F09** | Anti-ciclado corto (DC) | Media | M | gated por F26 (compresor) |
| 3 | **F03** | Anti-pico / reparto de cargas (incl. DS) | Media | M | gated por F26 (eléctricas) |
| 4 | **F25** | AC = emisor + multi-emisor por zona | Alta | L | gated por F26; usa pipeline DC |

---

## Fase 3 · Fundacional B — Zonas, Modo y Presencia
> Coordinación por ámbito (zona/grupo/casa) y modos. Habilita el *por grupos* del
> resto.

| Orden | ID | Feature | Valor | Esf. | Dependencia |
|---|---|---|---|---|---|
| 1 | **F24** | Agrupación de zonas (zona→grupo→casa) | Alta | L | prereq de F01/F21/F23 por grupo |
| 2 | **F01** | Modo global de la casa (vive en bus) | Alta | L | sustituye vacaciones de DC; usa F24 |
| 3 | **F32** | Dynamic Presence (enabler transversal) | Alta | L | alimenta F01/F21/setback |
| 4 | **F21** | Programador semanal común DC+DV | Media | M | global→por grupo (F24); hook presencia (F32) |
| 5 | **F23** | Confort↔economía por presets | Media-Alta | M | ligado a F01/F24 |

---

## Fase 4 · Meteo resiliente
> Mejora la calidad de datos de varias features ya entregadas.

| Orden | ID | Feature | Valor | Esf. | Mejora a |
|---|---|---|---|---|---|
| 1 | **F33** | Dynamic Weather multi-fuente con fallback | Alta | M | F17 (alertas), DC (forecast bias), free-cooling |

---

## Fase 5 · Energía y consolidación
> Módulo grande; parte **no testable por el autor** (sin FV/batería/VE) → queda a
> validación externa. Descongela F04 (precio) dentro de Energy.

| Orden | ID | Feature | Valor | Esf. | Notas |
|---|---|---|---|---|---|
| 1 | **F06** | Sensor coste/consumo/energía | Media-Alta | M | base agregable por F34; panel de Energía HA |
| 2 | **F34** | Dynamic Energy (módulo) | Alta | L | consolida F03/F04/F06; ⚠️ FV/batería/VE sin validar |

---

## Congeladas (fuera de fases)
| ID | Motivo |
|---|---|
| **F04** | Precio luz → Adaptive Lead. Revive dentro de **F34** (Energy). |
| **F05** | Outdoor reset. Se solapa con `bias_exterior` en la instalación objetivo. |
| **F18** | Anti-helada persianas. Marginal (clima español + enrollables). |

---

## Resumen de fases
| Fase | Tema | Features | Esfuerzo dominante |
|---|---|---|---|
| 0 | Plataforma / quick wins | F10, F07, F02, F08 | S |
| 1 | Mejoras autónomas (DV/DC/DS) | F13, F11, F12, F28, F30, F14, F35, F27, F20, F22, F31, F15, F16, F17, F19 | S–M (F15 L) |
| 2 | Tipo de instalación | F26, F09, F03, F25 | M–L |
| 3 | Zonas, modo y presencia | F24, F01, F32, F21, F23 | L |
| 4 | Meteo resiliente | F33 | M |
| 5 | Energía | F06, F34 | L |
