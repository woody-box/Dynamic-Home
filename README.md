# Dynamic Home

<p align="center">
  <img src="https://raw.githubusercontent.com/woody-box/Dynamic-Home/main/docs/img/dynamic_home.png" alt="Dynamic Home" width="280">
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

| | Module | Entity | Controls |
|---|--------|--------|----------|
| <img src="https://raw.githubusercontent.com/woody-box/Dynamic-Home/main/docs/brand/dynamic_climate.png" alt="DC" width="72"> | **DC** · Dynamic Climate | `climate` | Heating and radiant cooling (per-zone setpoint) |
| <img src="https://raw.githubusercontent.com/woody-box/Dynamic-Home/main/docs/brand/dynamic_ventilation.png" alt="DV" width="72"> | **DV** · Dynamic Ventilation | `fan` | Dual-flow HRV (speed by air quality) |
| <img src="https://raw.githubusercontent.com/woody-box/Dynamic-Home/main/docs/brand/dynamic_shutter.png" alt="DS" width="72"> | **DS** · Dynamic Shutter | `cover` | Shutters (position by sun, climate and weather) |
| <img src="https://raw.githubusercontent.com/woody-box/Dynamic-Home/main/docs/brand/dynamic_weather.png" alt="Weather" width="72"> | **Dynamic Weather** | `weather` | Optional: resilient multi-source forecast/alert provider (fallback) |
| <img src="https://raw.githubusercontent.com/woody-box/Dynamic-Home/main/docs/brand/dynamic_zones.png" alt="Zones" width="72"> | **Dynamic Home · Zones** | `select` · `sensor` | House hub: zones, modes, comfort, presence, changeover, pause, global shutter peak |
| <img src="https://raw.githubusercontent.com/woody-box/Dynamic-Home/main/docs/brand/dynamic_energy.png" alt="Energy" width="72"> | **Dynamic Energy** | `sensor` | House power brain: ICP headroom, tariff, scarcity, kWh/€ totals |

The last two are optional, **one-per-house** ("singleton") coordination hubs. You
can run DC/DV/DS standalone, or add Zones/Energy to coordinate the whole house.

DC, DV and DS share the **SDHB** bus (in memory). **DC is the brain**: while heating
it asks the shutters for *solar gain*, and while cooling it asks for *solar
shield*; DS and DV react. Each shutter listens on its **facade**
(`ds_f<azimuth>`), so a climate zone can request shielding only on the sunlit
facade and leave the rest untouched. This logic used to live in thousands of YAML
helpers; it is now a native integration you add from the UI.

---

## House coordination & energy

Beyond the per-zone modules, two optional singleton hubs coordinate the whole house.

<img src="https://raw.githubusercontent.com/woody-box/Dynamic-Home/main/docs/brand/dynamic_zones.png" alt="Dynamic Home / Zones" width="96" align="left">

**Dynamic Home (Zones)** — the house brain:

- **Zones & groups** — organize modules into a `zone → group → house` hierarchy so
  the settings below can target a room, not just the whole house.
- **House modes** (`Home / Away / Sleep / Boost / Eco`, global + per-zone override):
  DC enters vacation on *Away*, DV caps its speed, and DS reacts too — *Away* runs
  **presence simulation** and *Sleep* closes the shutters in that scope.
- **Comfort presets** (`Eco / Balanced / Comfort`) scale the aggressiveness of DC
  (bands, lead) and DV (thresholds), and DS solar shading, per scope.
- **Presence** — fuses occupancy sensors (PIR / mmWave / door / phones) into per-zone
  and house presence, and can drive the house mode.
- **Presence simulation** (anti-burglary) — in *Away*, shutters mimic an occupant
  (open by day, close by night, jittered & staggered); weather and manual still win.
- **Community changeover** — for 2-pipe shared radiant systems, a seasonal water
  direction (`heat / cool / off`) that the *community* climate zones follow.
- **Master pause** (global + per-module) — stop DC / DV / DS actuating **and**
  influencing the bus (a centralized, per-module *Observe only*) — e.g. to drive the
  thermostats by hand.
- **Global shutter peak limiting** — set the motor-inrush budget (max simultaneous
  starts / power / stagger) **once** for every shutter.

<br clear="left">

<img src="https://raw.githubusercontent.com/woody-box/Dynamic-Home/main/docs/brand/dynamic_energy.png" alt="Dynamic Energy" width="96" align="left">

**Dynamic Energy** — the house power brain. It aggregates and publishes energy
context that the other modules read (it never commands — each module stays sovereign,
safety first):

- **Import headroom** under the contracted power (ICP) — tightens the **electric
  peak-shaving** budget of climate zones so several loads don't trip the breaker.
- **Tariff state** (`cheap / normal / peak`) from a price sensor or fixed bands.
- **Scarcity** binary, and **house kWh / € totals** that feed Home Assistant's Energy
  dashboard. PV / battery / EV fields exist but are **gated / experimental**.

<br clear="left">

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

Current release: **v0.98.0**. This is a personal, single-maintainer, pre-1.0
project: nothing is "final" in a broad-production sense, so the scale below is
relative. The key axis is **not test count** but **real-world soak** — how much
each module has actually run on hardware, not just in the (606+) unit tests.

- **Beta (mature)** — well covered by tests **and** in daily real-world use.
- **Beta** — complete and tested, with modest real-world soak.
- **Experimental** — works but little real-world validation, or parts unbuilt.

| Module | Maturity | Notes |
|--------|----------|-------|
| Dynamic Ventilation (DV) | 🟢 Beta (mature) | Battle-tested on real relays; IAQ speed + failsafe proven |
| Dynamic Shutter (DS) | 🟢 Beta (mature) | Battle-tested; safety-hardened after real incidents (give it soak time) |
| Dynamic Weather (DW) | 🟢 Beta (stable) | Simple provider mirror + alerts; low complexity, low risk |
| Dynamic Climate (DC) | 🟡 Beta / Experimental | Core (base+biases, condensation, changeover) functional; advanced paths (multi-emitter, shared duct, anti-peak, compressor anti-cycle) tested-only, little real-world use |
| Dynamic Home (Zones) | 🟡 Beta | Zones, modes, presence, changeover in use; comfort presets less exercised |
| Dynamic Energy | 🟠 Experimental | Newest module; core (headroom/tariff/cost) tested; PV/battery/EV deferred and unvalidated |
| SDHB bus | 🟢 Beta (stable) | In-memory intent arbitration, deterministic tie-break |
| Config flow (UI) | Functional | Setup + options by category; reconfigure & clone; shutter "Común" auto-created |
| PV / battery / EV | 🟠 Experimental | Fields present but gated; not validated by the author |
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

New here? Start with **[`docs/QUICKSTART.md`](docs/QUICKSTART.md)** — stand up a dummy
climate zone and read the decision *reason codes* in ~10 minutes, without touching any
hardware. Then **[`docs/PROFILES.md`](docs/PROFILES.md)** has one recipe per real install
type (communal radiant, 3-speed VMC, motorized shutters, heat pump with a tariff). To make
sense of the many tunables, **[`docs/TUNING.md`](docs/TUNING.md)** groups them by goal
("make it anticipate more", "stop it oscillating", "respect the main breaker") and says
which knobs move together.

---

## Technical documentation

> The deep specs below are written in Spanish.

- [`docs/SPEC_DC.md`](docs/SPEC_DC.md) — climate algorithm (target, biases, bus).
- [`docs/SPEC_DV.md`](docs/SPEC_DV.md) — ventilation algorithm (IAQ, EMA, failsafe).
- [`docs/SPEC_DS.md`](docs/SPEC_DS.md) — shutter algorithm (cascade + caps).
- [`docs/INTEGRATION.md`](docs/INTEGRATION.md) — port architecture and how to test.
- [`docs/QUICKSTART.md`](docs/QUICKSTART.md) — 10-min dummy zone + reason codes (onboarding).
- [`docs/PROFILES.md`](docs/PROFILES.md) — recipes per real install profile.
- [`docs/TUNING.md`](docs/TUNING.md) — parameter guide by goal (what to move, what to watch together).
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
- **Dynamic Energy** provides tariff state, ICP import headroom and electric
  peak-shaving; **PV / battery / EV** fields are present but **gated and not
  validated** by the author.
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
