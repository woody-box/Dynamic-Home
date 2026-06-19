# Dynamic Home — port a integración (PoC)

Port de la suite YAML (`../Dynamic_Suite_v4_2_WOODBOX_FINAL/`) a una
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
│   ├── engine.py                    # ★ Lógica de decisión PURA (sin deps HA, testeable)
│   ├── coordinator.py               # Puente HA → engine + hub SDHB en memoria
│   ├── config_flow.py               # Asistente UI (reemplaza los REPLACE_* del hw_map)
│   ├── fan.py                       # Entidad fan (auto / v1 / v2 / v3) + driver de relés
│   ├── number.py                    # Umbrales IAQ como entidades number
│   └── strings.json                 # Textos UI (ES)
└── tests/
    └── test_engine.py               # 16 tests del engine (sustituyen los golden YAML)
```

## Idea clave

La lógica de control vive en `engine.py` **sin dependencias de Home Assistant**:
es Python puro, lo que permite probarla en CI sin levantar HA. Los wrappers
(`coordinator`, `fan`, `number`) solo traducen estado de HA a `engine.DvInputs`
y aplican el resultado a los relés.

## Probar

**Engine (lógica pura, sin dependencias):**
```bash
python integration/tests/test_engine.py
```

**Integración completa dentro de un Home Assistant simulado** (config flow,
coordinator, fan, number — carga la integración en un HA real de test):
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r integration/requirements-test.txt
cd integration && python -m pytest tests/ -q
```

Estado actual: **75/75 verde** (29 DV + 21 DS + 16 DC engine · 3 DV + 3 DS + 4 DC
integración). Los tests verifican que la integración **se carga en HA**, crea
`fan` / `cover` / `climate` + helpers, y el **triángulo completo**: una zona DC
en modo cool publica al bus y la persiana DS se clampa a 30% — coordinación
multi-módulo end-to-end.

## Qué cubre

- Pipeline de decisión IAQ completo: EMA, histéresis V1/V2/V3, free-cooling,
  pre-riesgo de rocío, dry mode, intents SDHB (quiet/boost/freecool), cap por
  AQI hostil y anti-flapping.
- **Gate `permitida`**: programación semanal (con wrap nocturno) + permiso extra.
- **Failsafe**: sensores vitales KO → V1, trip-counter → lockout, startup grace.
- **Boost por ducha** vía ΔRH (histéresis + hold).
- **Umbrales adaptativos** (el engine los consume cuando se aportan).
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
