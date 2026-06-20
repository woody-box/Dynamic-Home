# Dynamic Home

<p align="center">
  <img src="docs/img/dynamic_home.png" alt="Dynamic Home" width="280">
</p>

[![tests](https://github.com/woody-box/Dynamic-Home/actions/workflows/tests.yml/badge.svg)](https://github.com/woody-box/Dynamic-Home/actions/workflows/tests.yml)
[![hacs](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz)

> **Dynamic Home no pretende sustituir sistemas profesionales certificados:** es una
> integración **experimental / open source** para automatización residencial avanzada
> en Home Assistant.

**Dynamic Home** es un BMS doméstico (gestión integral del hogar) para Home
Assistant, dividido en tres módulos coordinados por un bus interno:

| Módulo | Entidad | Qué controla |
|--------|---------|--------------|
| **DC** · Dynamic Climate | `climate` | Calefacción y suelo refrescante (consigna por zona) |
| **DV** · Dynamic Ventilation | `fan` | VMC de doble flujo (velocidad por calidad de aire) |
| **DS** · Dynamic Shutter | `cover` | Persianas (posición por sol, clima y meteo) |

<p align="center">
  <img src="docs/brand/dynamic_climate.png" alt="Dynamic Climate" width="120">
  <img src="docs/brand/dynamic_ventilation.png" alt="Dynamic Ventilation" width="120">
  <img src="docs/brand/dynamic_shutter.png" alt="Dynamic Shutter" width="120">
</p>

Los tres comparten el **bus SDHB** (en memoria). **DC es el cerebro**: al
calentar pide a las persianas *ganancia solar* y al enfriar pide *protección
solar*; DS y DV reaccionan. Todo esto antes vivía en miles de *helpers* YAML;
ahora es una integración nativa que se añade desde la interfaz.

> Este repositorio contiene **la integración** en `custom_components/dynamic_home/`
> (lo que instala HACS). La suite YAML original v4.2 (referencia/legado) vive en la
> rama [`archive/v4.2-source`](https://github.com/woody-box/Dynamic-Home/tree/archive/v4.2-source),
> fuera de `main` para mantener el repo ligero.

---

## ⚠️ Estado del proyecto

- **Experimental / beta.** En desarrollo activo; puede haber cambios y fallos.
- **Prueba primero con relés o entidades de prueba**, no directamente sobre tu hardware.
- **No conectes a hardware crítico sin validar** (usa el modo *Observe only* para
  ver las decisiones sin actuar).
- Pensado para **usuarios avanzados de Home Assistant**.

---

## Instalación (HACS)

1. HACS → Integraciones → menú ⋮ → **Repositorios personalizados**.
2. Añade `https://github.com/woody-box/Dynamic-Home` con categoría **Integration**.
3. Instala **Dynamic Home** y reinicia Home Assistant.
4. Ajustes → Dispositivos y servicios → **Añadir integración** → *Dynamic Home*.

### Instalación manual (alternativa)

Copia `custom_components/dynamic_home/` a tu carpeta `config/custom_components/`
y reinicia Home Assistant.

**Requisitos:** Home Assistant ≥ 2024.3.

---

## Uso

Al añadir la integración eliges el módulo (un asistente por instancia):

- **Ventilación (VMC):** relés de velocidad + sensores de CO₂ y PM2.5
  (temperaturas, AQI y humedad son opcionales).
- **Persiana:** la `cover` y la orientación de la fachada (clima/viento/lluvia
  opcionales).
- **Clima (zona):** sensor de temperatura interior y el *target* de persianas
  al que publica en el bus.

Puedes añadir varias instancias (varias zonas, varias persianas). Todas
comparten el bus y se coordinan automáticamente. Cada persiana escucha en su
**fachada** (`ds_f<azimut>`), así que una zona de clima puede pedir protección
solar solo a la fachada soleada y dejar el resto sin tocar.

> ⚠️ Pruébalo primero contra interruptores de prueba antes que contra el
> hardware real, hasta validar el comportamiento en tu instalación.

---

## Documentación técnica

- [`docs/SPEC_DC.md`](docs/SPEC_DC.md) — algoritmo de clima (target, biases, bus).
- [`docs/SPEC_DV.md`](docs/SPEC_DV.md) — algoritmo de ventilación (IAQ, EMA, failsafe).
- [`docs/SPEC_DS.md`](docs/SPEC_DS.md) — algoritmo de persianas (cascada + caps).
- [`docs/INTEGRATION.md`](docs/INTEGRATION.md) — arquitectura del port y cómo probar.

## Desarrollo

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-test.txt
pytest -q
```

La lógica de decisión vive en módulos **puros sin dependencias de Home
Assistant** (`*_engine.py`), con tests unitarios; los *wrappers* de HA solo
traducen estado. CI ejecuta toda la batería en cada push.

## Licencia

MIT — ver [`LICENSE`](LICENSE).
