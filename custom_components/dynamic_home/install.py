"""Installation profile (F26) — pure catalogue of the heating/cooling install.

Three *independent* dimensions are declared per DC (climate) entry:

* **Generator** — the heat source: air-to-water/geothermal/air-air heat pumps,
  gas/oil/biomass/wood boilers, or direct electric.
* **Distribution** — individual vs central (shared/communal). Direct-electric and
  air-air are always individual (the wizard does not ask).
* **Emission** — the emitter, which sets the thermal *inertia* (underfloor is
  slow/high, fan-coil is fast/low, ...).

From a ``(generator, distribution, emission)`` triple we derive a *profile* that
F09/F03 will consume:

* ``community`` — central shared distribution: the occupant only opens a valve and
  the building owns the generator, so per-zone compressor/peak management does not
  apply.
* ``compressor`` — a heat-pump generator under the occupant's control (not
  community). F09 (short-cycle protection over the compressor) applies.
* ``peak`` — an electrically-driven load under the occupant's control: direct
  electric, or an *individual* heat pump. F03 (electrical-peak shaving) applies.
  Combustion boilers (gas/oil/pellets/wood) only drive a pump, so they never trip
  peak.

Choosing a triple also pre-loads coherent option *defaults* by inertia (earlier,
gentler lead and longer anti-cycle for slow emitters), merged into
``entry.options`` and fully editable afterwards. Everything here is pure (no HA
imports); :func:`defaults` only emits valid ``options_spec`` keys (guard test).
"""

from __future__ import annotations

# Generator id -> (label_en, label_es).
GENERATORS: dict[str, tuple[str, str]] = {
    "heatpump_air_water": ("Air-to-water heat pump (aerothermal)",
                           "Aerotermia (aire-agua)"),
    "heatpump_geothermal": ("Geothermal heat pump", "Geotermia"),
    "heatpump_air_air": ("Air-to-air (AC / split)", "Aire-aire (AC / split)"),
    "gas_boiler": ("Gas boiler", "Caldera de gas"),
    "oil_boiler": ("Oil boiler (diesel)", "Caldera de gasoil"),
    "biomass_boiler": ("Biomass boiler (pellets)",
                       "Caldera de biomasa (pellets)"),
    "wood_boiler": ("Wood boiler", "Caldera de leña"),
    "electric_direct": ("Direct electric (radiant / storage)",
                        "Eléctrica directa (radiante / acumuladores)"),
}

# Distribution id -> (label_en, label_es).
DISTRIBUTIONS: dict[str, tuple[str, str]] = {
    "individual": ("Individual", "Individual"),
    "central_shared": ("Central / communal (shared)",
                       "Central / comunitaria (compartida)"),
}

# Emission id -> (label_en, label_es, inertia). Inertia in {"high","medium","low"}.
EMISSIONS: dict[str, tuple[str, str, str]] = {
    "underfloor": ("Underfloor radiant", "Suelo radiante", "high"),
    "ceiling_radiant": ("Ceiling radiant", "Techo radiante", "high"),
    "radiators": ("Radiators", "Radiadores", "medium"),
    "towel_rail": ("Towel rail / skirting", "Toallero / zócalo", "low"),
    "convectors": ("Electric convectors", "Convectores", "low"),
    "ducts": ("Ducted air (heating)", "Conductos (calor)", "low"),
    "radiant_cooling": ("Radiant cooling", "Radiante refrescante", "high"),
    "fancoil": ("Fan-coil", "Fancoil", "low"),
    "split": ("Wall split", "Split de pared", "low"),
    "ducts_cooling": ("Ducted air (cooling)", "Conductos (frío)", "low"),
}

# Compressor-driven generators (heat pumps).
HEATPUMPS = frozenset({"heatpump_air_water", "heatpump_geothermal",
                       "heatpump_air_air"})
# Generators that are always individual (the wizard skips the distribution step).
_FORCED_INDIVIDUAL = frozenset({"electric_direct", "heatpump_air_air"})


def is_generator(gen: str) -> bool:
    return gen in GENERATORS


def is_emission(emission: str) -> bool:
    return emission in EMISSIONS


def forced_individual(gen: str) -> bool:
    """Whether the generator is always individual (no distribution choice)."""
    return gen in _FORCED_INDIVIDUAL


def is_electric(gen: str) -> bool:
    """Whether the generator is an electrical heating load (heat pump or direct)."""
    return gen in HEATPUMPS or gen == "electric_direct"


def inertia(emission: str) -> str:
    """Thermal inertia class of an emitter ('high'/'medium'/'low')."""
    e = EMISSIONS.get(emission)
    return e[2] if e else "medium"


def distribution_for(gen: str, distribution: str | None) -> str:
    """Resolve the effective distribution (forced individual when applicable)."""
    if forced_individual(gen):
        return "individual"
    return distribution if distribution in DISTRIBUTIONS else "individual"


def profile(generator: str, distribution: str | None, emission: str) -> dict:
    """Derive ``{inertia, compressor, peak, community}`` from a triple."""
    dist = distribution_for(generator, distribution)
    community = dist == "central_shared"
    compressor = (generator in HEATPUMPS) and not community
    peak = (not community) and is_electric(generator)
    return {
        "inertia": inertia(emission),
        "compressor": compressor,
        "peak": peak,
        "community": community,
    }


# Option overrides pre-loaded per inertia class (valid ``options_spec`` keys
# only). Slow/high-inertia emitters lead earlier and tolerate longer min ON/OFF;
# fast/low-inertia emitters react quickly, so they lead late and cycle shorter.
_DEFAULTS_BY_INERTIA: dict[str, dict[str, float]] = {
    "high": {
        "lead_base_h": 2.0, "trend_lead_h": 1.5,
        "lead_min_h": 1.0, "lead_max_h": 4.0,
        "anticycle_min_on_s": 900.0, "anticycle_min_off_s": 900.0,
    },
    "medium": {
        "lead_base_h": 1.0, "trend_lead_h": 1.0,
        "lead_min_h": 0.5, "lead_max_h": 3.0,
        "anticycle_min_on_s": 600.0, "anticycle_min_off_s": 600.0,
    },
    "low": {
        "lead_base_h": 0.4, "trend_lead_h": 0.5,
        "lead_min_h": 0.2, "lead_max_h": 1.5,
        "anticycle_min_on_s": 300.0, "anticycle_min_off_s": 300.0,
    },
}


def defaults(generator: str, distribution: str | None, emission: str) -> dict:
    """Coherent option pre-loads for the chosen triple (driven by inertia)."""
    return dict(_DEFAULTS_BY_INERTIA.get(inertia(emission),
                                         _DEFAULTS_BY_INERTIA["medium"]))


def label(catalog: dict, key: str, lang: str) -> str:
    """Localized label for a generator/distribution/emission id."""
    item = catalog.get(key)
    if not item:
        return key
    return item[1] if lang.startswith("es") else item[0]
