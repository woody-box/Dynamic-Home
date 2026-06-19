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

Estado actual: **19/19 verde** (16 engine + 3 integración). Los tests de
integración verifican que la integración **se carga en HA**, crea `fan.vmc` +
los `number`, y que al subir el CO₂ del sensor la velocidad pasa a V3 y se
conmuta el relé correcto.

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

> Estado: PoC validado. El `engine.py` está cubierto por tests unitarios y los
> wrappers de HA se han ejecutado y verificado dentro de un Home Assistant de
> test (HA 2024.3.x vía harness). Falta la prueba en una instancia HA real con
> hardware (Opción B): usa switches de juguete antes que la VMC real.
