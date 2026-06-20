# Dynamic Home — Backlog de ideas (exploración)

> Documento vivo. **No es compromiso de implementación.** Vamos revisando cada
> idea una a una; al cerrar la opinión se marca *Revisada* y se rellena
> *Perfilado*. Cuando estén perfiladas, se redactará un documento de requisitos
> y se implementarán en una fase posterior.

**Leyenda de estado:** ☐ pendiente · 🔄 en discusión · ☑ revisada (perfilada)
**Valor:** Alta / Media / Baja · **Esfuerzo:** S (pequeño) / M (medio) / L (grande)

---

## Cross-módulo (bus SDHB)

### F01 · Modo global de la casa ⭐
- **Estado:** ☐ · **Módulos:** DV·DS·DC · **Valor:** Alta · **Esfuerzo:** M
- **Idea:** un `select` único (`Home/Away/Sleep/Boost/Eco`) que publica al bus y sesga los tres módulos a la vez (ej. *Sleep* = VMC≤V1, persianas a aislamiento nocturno, DC con banda ancha).
- **Perfilado:** _(pendiente)_

### F02 · Explicador de conflictos del bus ⭐
- **Estado:** ☐ · **Módulos:** DV·DS·DC · **Valor:** Alta · **Esfuerzo:** S
- **Idea:** sensor que expone "quién ganó y por qué" cuando hay intents en conflicto (p.ej. DC pide abrir por ganancia solar y DS quiere cerrar por viento).
- **Perfilado:** _(pendiente)_

### F03 · Anti-pico / reparto de cargas
- **Estado:** ☐ · **Módulos:** DC (vía bus) · **Valor:** Media · **Esfuerzo:** M
- **Idea:** evitar que todas las zonas DC arranquen a la vez; escalonar demanda (útil con bomba de calor / potencia contratada).
- **Perfilado:** _(pendiente)_

## Energía y coste

### F04 · Precio de electricidad → Adaptive Lead ⭐
- **Estado:** ☐ · **Módulos:** DC · **Valor:** Alta · **Esfuerzo:** M
- **Idea:** input de precio (PVPC/Nordpool) para desplazar el pre-calentamiento/enfriamiento del Adaptive Lead a horas baratas.
- **Perfilado:** _(pendiente)_

### F05 · Compensación por curva exterior (outdoor reset)
- **Estado:** ☐ · **Módulos:** DC · **Valor:** Media · **Esfuerzo:** M
- **Idea:** curva clásica de calefacción que ajusta la consigna de la fuente según la temperatura exterior.
- **Perfilado:** _(pendiente)_

### F06 · Sensor de coste/consumo estimado
- **Estado:** ☐ · **Módulos:** DV (y DC) · **Valor:** Media · **Esfuerzo:** S
- **Idea:** estimar consumo/coste por horas de funcionamiento (la telemetría de horas ya existe en DV).
- **Perfilado:** _(pendiente)_

## Robustez y mantenimiento

### F07 · HA Repairs sobre `degraded` ⭐
- **Estado:** ☐ · **Módulos:** DV·DS·DC · **Valor:** Alta · **Esfuerzo:** S
- **Idea:** cuando un sensor configurado desaparece o lleva obsoleto, emitir un *issue* accionable en Ajustes→Reparaciones (se apoya en el `binary_sensor degraded` ya existente).
- **Perfilado:** _(pendiente)_

### F08 · Vida del filtro VMC
- **Estado:** ☐ · **Módulos:** DV · **Valor:** Media · **Esfuerzo:** S
- **Idea:** % de vida del filtro + recordatorio al umbral, sobre `filter_hours` ya contabilizadas.
- **Perfilado:** _(pendiente)_

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

---

## Registro de revisión
| ID | Estado | Decisión resumida |
|----|--------|-------------------|
| F01–F23 | ☐ | Pendiente de revisar una a una |
