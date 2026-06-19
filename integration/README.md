# Dynamic Home — port a integración (PoC)

Prueba de concepto del port de la suite YAML (`../Dynamic_Suite_v4_2_WOODBOX_FINAL/`)
a una **integración de Home Assistant**. Primera pieza: **Dynamic Ventilation (DV)**,
el VMC de doble flujo, expuesto como una entidad `fan`.

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

## Probar el engine

```bash
python integration/tests/test_engine.py      # o: python -m pytest integration/tests/ -q
```

## Qué cubre el PoC

- Pipeline de decisión IAQ completo: EMA, histéresis V1/V2/V3, free-cooling,
  pre-riesgo de rocío, dry mode, intents SDHB (quiet/boost/freecool), cap por
  AQI hostil y anti-flapping. Ver `SPEC.md`.
- Config flow + options flow.
- Entidad `fan` con preset modes y driver de 3 relés.

## Fuera del PoC (siguiente iteración)

Adaptive thresholds, programación semanal, failsafe/trip-counter, boost por
ducha (ΔRH), telemetría (horas/consumo/filtros), y portar DC y DS sobre el
mismo `SdhbHub`. Ver `SPEC.md §7`.

> ⚠️ Estado: esqueleto/PoC. El `engine.py` está validado con tests; los wrappers
> de HA compilan pero aún no se han ejecutado dentro de una instancia HA real.
