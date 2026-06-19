# Dynamic Home — port a integración (PoC)

Port de la suite YAML original (rama `archive/v4.2-source`) a una
**integración de Home Assistant**. Módulos portados:
- **DV** (ventilación / VMC) → entidad `fan` — ver `SPEC.md`.
- **DS** (persianas) → entidad `cover` — ver `SPEC_DS.md`.
- **DC** (clima / zona) → entidad `climate` — ver `SPEC_DC.md`.

Los tres comparten un **bus SDHB en memoria** (`SdhbHub`): **DC es el cerebro** y
publica intenciones (`request_solar_gain`/`request_solar_shield`) que **DS y DV
consumen** y coordinan. El config flow ofrece un **menú** para añadir VMC,
persiana o zona de clima.

## Estructura

```
integration/
├── SPEC.md                          # Especificación destilada del algoritmo DV
├── custom_components/dynamic_home/
│   ├── manifest.json
│   ├── const.py
│   ├── dv_engine.py                 # ★ Lógica de decisión PURA DV (sin deps HA, testeable)
│   ├── dc_engine.py                 # ★ Lógica de decisión PURA DC (clima)
│   ├── ds_engine.py                 # ★ Lógica de decisión PURA DS (persiana)
│   ├── coordinator.py               # Shim que re-exporta los coordinators + SdhbHub
│   ├── coordinator_dv.py            # Puente HA → engine DV
│   ├── coordinator_dc.py            # Puente HA → engine DC (+ publica al bus)
│   ├── coordinator_ds.py            # Puente HA → engine DS
│   ├── config_flow.py               # Asistente UI (reemplaza los REPLACE_* del hw_map)
│   ├── fan.py                       # Entidad fan (auto / v1 / v2 / v3) + driver de relés
│   ├── number.py                    # Umbrales IAQ como entidades number
│   └── strings.json                 # Textos UI (ES)
└── tests/
    └── test_dv_engine.py            # tests del engine DV (sustituyen los golden YAML)
```

## Idea clave

La lógica de control vive en los `*_engine.py` **sin dependencias de Home
Assistant**: es Python puro, lo que permite probarla en CI sin levantar HA. Los
wrappers (`coordinator_*`, `fan`, `number`) solo traducen estado de HA a los
`*Inputs` del engine y aplican el resultado a los relés.

## Probar

**Engine (lógica pura, sin dependencias):**
```bash
python integration/tests/test_dv_engine.py
```

**Integración completa dentro de un Home Assistant simulado** (config flow,
coordinator, fan, number — carga la integración en un HA real de test):
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r integration/requirements-test.txt
cd integration && python -m pytest tests/ -q
```

Estado actual: **112/112 verde** (engine/bus + integración). Los tests verifican que la
integración **se carga en HA**, crea `fan` / `cover` / `climate` + helpers, el
**triángulo completo** (DC en cool → bus → DS se clampa) y el **targeting solar
dinámico**: DC calcula qué fachadas ilumina el sol y dirige la intención solo
ahí; al moverse el sol, re-dirige (la persiana protegida se reabre y la nueva
fachada soleada se protege).

## Multi-instancia y bus

Cada instancia es un config entry y todas comparten el `SdhbHub`. El bus
(`bus.py`, puro) arbitra por prioridad y soporta **targets de fachada**: cada
persiana escucha en `ds` (broadcast) y en su fachada `ds_fXXX` (azimut a 3
dígitos) y se registra en `hass.data`.

**Targeting solar dinámico:** DC, en cada ciclo, calcula con
`dc_engine.sunlit_facades()` qué fachadas están soleadas (sol sobre el horizonte
y dentro del span de la fachada) y publica la intención a esas fachadas,
reconciliando los slots del bus (limpia las que dejan de estar soleadas). Si no
hay datos de sol/fachadas, hace fallback al target configurado. Cada persiana
aporta su **ángulo de aceptación** (`facade_span_deg`), así que fachadas
estrechas solo reaccionan con el sol casi de frente.

## Qué cubre

- Pipeline de decisión IAQ completo: EMA, histéresis V1/V2/V3, free-cooling,
  pre-riesgo de rocío, dry mode, intents SDHB (quiet/boost/freecool), cap por
  AQI hostil y anti-flapping.
- **Gate `permitida`**: programación semanal (con wrap nocturno) + permiso extra.
- **Failsafe**: sensores vitales KO → V1, trip-counter → lockout, startup grace.
- **Boost por ducha** vía ΔRH (histéresis + hold).
- **Umbrales adaptativos** (percentiles 7d en buffer rodante + switch).
- **Telemetría VMC** (horas por velocidad/máquina/filtro + reset).
- Config flow + options flow.
- Entidad `fan` con preset modes y driver de 3 relés.

## Siguiente iteración

Cálculo de percentiles 7d para los umbrales adaptativos (estadísticas del
recorder), telemetría (horas/consumo/filtros), multi-VMC, y portar DC y DS
sobre el mismo `SdhbHub`. Ver `SPEC.md §7`.

> Estado: PoC validado. El `engine.py` está cubierto por tests unitarios y los
> wrappers de HA se han ejecutado y verificado dentro de un Home Assistant de
> test (HA 2024.3.x vía harness). Falta la prueba en una instancia HA real con
> hardware (Opción B): usa switches de juguete antes que la VMC real.
