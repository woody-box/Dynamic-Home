# Dynamic Home

<p align="center">
  <img src="docs/img/dynamic_home.png" alt="Dynamic Home" width="280">
</p>

[![tests](https://github.com/woody-box/Dynamic-Home/actions/workflows/tests.yml/badge.svg)](https://github.com/woody-box/Dynamic-Home/actions/workflows/tests.yml)
[![hacs](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz)

**English** · [Español](README.es.md)

> **Experimental / open source.** Dynamic Home does not replace certified
> professional systems — it is an advanced residential automation layer that
> runs **inside** Home Assistant.

**Dynamic Home** is a modular residential BMS (building management system) for
Home Assistant: climate, ventilation and shutters driven by explainable control
logic and coordinated through an internal intent bus. It is aimed at advanced
users who want supervision, automated control, traceability ("which decision did
the system take, when and why") and coordination between subsystems.

---

## Who is it for

Dynamic Home is for **advanced Home Assistant users** who want to manage heating,
ventilation and shutters in a coordinated, explainable, automated way. It is a
good fit if you have:

- Radiant heating / cooling with high thermal inertia.
- A multi-speed HVU/HRV (VMC) driven by relays.
- Temperature, humidity, CO₂, PM2.5 or air-quality sensors.
- Motorized shutters integrated in Home Assistant.
- A need for traceability — knowing what the system decided and why.

## Who is it *not* for

It is **not** a plug-and-forget solution. It is not a good fit if you:

- Have no prior experience with Home Assistant.
- Don't want to review sensors, entities and configuration.
- Expect it to replace a certified professional system.
- Plan to wire it straight to critical equipment without testing first.
- Cannot validate the behaviour before acting on real hardware.

---

## Modules

| Module | Entity | Controls |
|--------|--------|----------|
| **DC** · Dynamic Climate | `climate` | Heating and radiant cooling (per-zone setpoint) |
| **DV** · Dynamic Ventilation | `fan` | Dual-flow HRV (speed by air quality) |
| **DS** · Dynamic Shutter | `cover` | Shutters (position by sun, climate and weather) |
| **Weather** · Dynamic Weather | `weather` | Optional: resilient multi-source forecast/alert provider (fallback) |

<p align="center">
  <img src="docs/brand/dynamic_climate.png" alt="Dynamic Climate" width="120">
  <img src="docs/brand/dynamic_ventilation.png" alt="Dynamic Ventilation" width="120">
  <img src="docs/brand/dynamic_shutter.png" alt="Dynamic Shutter" width="120">
</p>

All three share the **SDHB** bus (in memory). **DC is the brain**: while heating
it asks the shutters for *solar gain*, and while cooling it asks for *solar
shield*; DS and DV react. Each shutter listens on its **facade**
(`ds_f<azimuth>`), so a climate zone can request shielding only on the sunlit
facade and leave the rest untouched. This logic used to live in thousands of YAML
helpers; it is now a native integration you add from the UI.

---

## Architecture

```mermaid
flowchart LR
    A[Sensors · Zigbee / WiFi / MQTT] --> B[Home Assistant]
    C[Relays · Shelly / actuators] --> B
    B --> D[Dynamic Home integration]
    D --> DC[DC · Climate]
    D --> DV[DV · Ventilation]
    D --> DS[DS · Shutter]
    DC <--> SDHB[SDHB · shared intent bus]
    DV <--> SDHB
    DS <--> SDHB
    DC --> HMI[Dashboards]
    DV --> HMI
    DS --> HMI
    HMI --> U[User]
```

Dynamic Home **does not replace Home Assistant**: it runs as a custom integration
inside it. Home Assistant remains the platform for entities, automation, history
and UI. The decision logic lives in **pure modules with no Home Assistant
dependency** (`*_engine.py`); the HA wrappers only translate state.

---

## Project status

| Area | Status | Notes |
|------|--------|-------|
| HACS install | Beta | Installable as a custom integration |
| Dynamic Climate (DC) | Beta | Per-zone climate, biases, adaptive lead |
| Dynamic Ventilation (DV) | Beta | VMC speed by IAQ and humidity |
| Dynamic Shutter (DS) | Beta | Shutter position by facade/sun/weather |
| SDHB bus | Beta | In-memory intent arbitration |
| Config flow (UI) | Functional | Setup + options grouped by category |
| Example dashboards | Pending | Not packaged yet |
| Screenshots | Pending | To be added |

Nothing here is called "stable": it is **functional beta / experimental**, in
active development and tested by CI, but not yet validated by external users.

---

## Installation (HACS)

1. HACS → Integrations → ⋮ menu → **Custom repositories**.
2. Add `https://github.com/woody-box/Dynamic-Home` with category **Integration**.
3. Install **Dynamic Home** and restart Home Assistant.
4. Settings → Devices & services → **Add integration** → *Dynamic Home*.

### Manual installation

Copy `custom_components/dynamic_home/` to your `config/custom_components/` folder
and restart Home Assistant.

**Requirements:** Home Assistant ≥ 2024.3.

---

## Safe first run

Before letting Dynamic Home act on real hardware, run it in a safe mode:

1. Install the integration and add a module (a wizard runs per instance).
2. Point it at **dummy entities** (e.g. test `input_boolean`/`switch` helpers)
   instead of the real relays.
3. Turn on **Observe only** (per-module switch): it computes and publishes to the
   bus but does **not** touch hardware.
4. Watch the diagnostic sensors and **reason codes** to see each decision.
5. Validate the behaviour over several days.
6. Swap dummy entities for real ones only once the behaviour is correct, and keep
   a manual override path available.

---

## Examples

Minimal, copy-pasteable setups (3-speed VMC, a climate zone, a shutter by facade)
live in **[`docs/EXAMPLES.md`](docs/EXAMPLES.md)**.

---

## Technical documentation

> The deep specs below are written in Spanish.

- [`docs/SPEC_DC.md`](docs/SPEC_DC.md) — climate algorithm (target, biases, bus).
- [`docs/SPEC_DV.md`](docs/SPEC_DV.md) — ventilation algorithm (IAQ, EMA, failsafe).
- [`docs/SPEC_DS.md`](docs/SPEC_DS.md) — shutter algorithm (cascade + caps).
- [`docs/INTEGRATION.md`](docs/INTEGRATION.md) — port architecture and how to test.
- [`docs/REQUIREMENTS.md`](docs/REQUIREMENTS.md) · [`docs/BACKLOG.md`](docs/BACKLOG.md) · [`docs/ROADMAP.md`](docs/ROADMAP.md)

---

## Development & tests

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-test.txt
pytest -q
```

The decision logic lives in **pure, HA-independent modules** (`*_engine.py`) with
unit tests; the HA wrappers only translate state. CI runs the full suite, `ruff`,
`hassfest` and HACS validation on every push.

---

## Known limitations

- **Bus arbitration** picks a single winner per target by priority/TTL; a
  higher-priority intent can mask a concurrent one on the same target.
- **Mold and open-window inference are heuristics** (humidity hours with decay /
  temperature trend against demand), not certified safety functions.
- **Energy / PV / battery / EV** features are still on the roadmap and not
  validated by the author.
- **No example dashboards** are packaged yet (screenshots pending).
- Deep technical docs (`SPEC_*`, `REQUIREMENTS`, `BACKLOG`) are in Spanish.

The original YAML suite v4.2 (reference / legacy) lives on the
[`archive/v4.2-source`](https://github.com/woody-box/Dynamic-Home/tree/archive/v4.2-source)
branch, kept off `main` to keep the repo light.

---

## Safety

Dynamic Home can act on relays, motors, valves, fans and climate equipment. An
incorrect configuration can cause unwanted behaviour of that equipment.

Minimum recommendations:

- Test first with dummy entities.
- Use **Observe only** before allowing real actuation.
- Verify each relay and entity manually.
- Do not act on critical equipment without supervision.
- Respect the applicable electrical and HVAC regulations.
- Use independent physical protections where appropriate.

The software does **not** replace electrical, thermal, mechanical or certified
safety systems.

---

## License

MIT — see [`LICENSE`](LICENSE).
