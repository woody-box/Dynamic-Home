"""Constants for the Dynamic Home integration (DV + DS)."""

from __future__ import annotations

DOMAIN = "dynamic_home"

# Module discriminator stored in each config entry.
CONF_MODULE = "module"
MODULE_VMC = "vmc"
MODULE_SHUTTER = "shutter"
MODULE_CLIMATE = "climate_zone"
MODULE_WEATHER = "weather"
MODULE_ZONES = "zones"
MODULE_ENERGY = "energy"

# Short Dynamic Home tag per module. Prefixed onto the hardware mirrors and
# suffixed onto the primary control entities (cover/climate/fan) so everything
# Dynamic Home creates is greppable in dashboards/entity pickers and tells apart
# from the underlying hardware entity it drives.
MODULE_TAG: dict[str, str] = {
    MODULE_VMC: "DH-DV",
    MODULE_SHUTTER: "DH-DS",
    MODULE_CLIMATE: "DH-DC",
}

# Platforms forwarded per module.
PLATFORMS_VMC: list[str] = ["fan", "number", "sensor", "button", "switch",
                            "time", "binary_sensor"]
PLATFORMS_SHUTTER: list[str] = ["cover", "switch", "number", "sensor",
                                "binary_sensor", "button"]
PLATFORMS_CLIMATE: list[str] = ["climate", "switch", "sensor", "binary_sensor"]
PLATFORMS_WEATHER: list[str] = ["weather", "binary_sensor", "sensor"]
PLATFORMS_ZONES: list[str] = ["sensor", "select", "binary_sensor", "switch"]
PLATFORMS_ENERGY: list[str] = ["sensor", "binary_sensor"]

# Shared device that groups the bus-conflict sensors of every module (so the
# whole bus is observable from one place in the HA UI, not scattered per entry).
BUS_DEVICE_ID = "bus"

# Shared device + owner-entry marker for the house-wide shutter counts (how many
# DS-managed covers are open/closed/ajar), created once by the first DS entry.
SHUTTERS_DEVICE_ID = "shutters_summary"
DATA_DS_SUMMARY_OWNER = "_ds_summary_owner"

# --- Config entry keys: VMC (DV) hardware map ---
CONF_NAME = "name"
CONF_SW_PWR = "sw_pwr"
CONF_SW_V2 = "sw_v2"
CONF_SW_V3 = "sw_v3"
CONF_CO2 = "co2"
CONF_PM25 = "pm25"
CONF_T_IN = "t_in"
CONF_T_EXT = "t_ext"
CONF_AQI = "outdoor_aqi_entity"
CONF_HUM_BATH = "hum_bath"
CONF_HUM_EXT = "hum_ext"
CONF_HUM_IN = "hum_in"            # optional: indoor RH for dry-mode/dew
# F13: extra bathrooms for the shower boost (each: name + humidity sensor),
# configured in the VMC options. The engine takes the max RH rise across them.
BATHROOM_MAX = 6
CONF_BATH_HUM = "bath_hum"        # options keys bath_hum_1..N (humidity sensor)
CONF_BATH_NAME = "bath_name"      # options keys bath_name_1..N (label)
# Heat-recovery (HRV) probes (F28). Supply/intake/extract drive the efficiency;
# exhaust is optional (exposed for observability, not used in the η calc).
CONF_HRV_SUPPLY = "hrv_supply"    # supply into the house (after the exchanger)
CONF_HRV_INTAKE = "hrv_intake"    # fresh outdoor air taken in
CONF_HRV_EXTRACT = "hrv_extract"  # stale air extracted from the house
CONF_HRV_EXHAUST = "hrv_exhaust"  # stale air expelled outside (after the exchanger)
CONF_VOC = "voc"                  # F30: VOC index (observation only, does NOT actuate)
CONF_NOX = "nox"                  # NOx index (observation only, does NOT actuate)
# F35: coordinated extractor hood — 3 relays, one per speed (none on = OFF).
CONF_HOOD_V1 = "hood_v1"
CONF_HOOD_V2 = "hood_v2"
CONF_HOOD_V3 = "hood_v3"

REQUIRED_HW = (CONF_SW_PWR, CONF_SW_V2, CONF_SW_V3, CONF_CO2, CONF_PM25)
OPTIONAL_HW = (CONF_T_IN, CONF_T_EXT, CONF_AQI, CONF_HUM_BATH, CONF_HUM_EXT,
               CONF_HRV_EXHAUST, CONF_VOC, CONF_NOX)

# --- Config entry keys: Shutter (DS) ---
CONF_COVER = "cover"
CONF_CLIMATE = "climate"          # optional: source of hvac mode (cool/heat)
CONF_DS_T_IN = "ds_t_in"
CONF_DS_T_OUT = "ds_t_out"
CONF_WIND = "wind"
CONF_RAIN = "rain"
CONF_DS_ALERT = "ds_alert"            # F17: generic weather-alert binary_sensor
CONF_DS_ALERT_HAIL = "ds_alert_hail"  # F17: hail/storm alert (own protect pos)
CONF_DS_ALERT_WIND = "ds_alert_wind"  # F17: wind alert (own protect pos)
CONF_FACADE_AZIMUTH = "facade_azimuth_deg"
CONF_FACADE_SPAN = "facade_span_deg"

# --- Config entry keys: Climate (DC) ---
CONF_DC_T_INT = "dc_t_int"        # required: indoor temperature sensor
CONF_DC_T_EXT = "dc_t_ext"        # optional: outdoor temperature sensor
CONF_DC_TARGET = "ds_target"      # shutter target the zone drives (default "ds")
CONF_DC_CLIMATE = "dc_climate"    # optional: real thermostat DC drives
CONF_DC_VMC = "dc_vmc"            # optional: VMC fan/sensor for the VMC bias
CONF_DC_HUMIDITY = "dc_humidity"  # optional: indoor RH for dew-point protection
CONF_DC_WATER_TEMP = "dc_water_temp"  # optional: radiant water/floor temp (cold surface)
CONF_DC_WEATHER = "dc_weather"    # optional: weather entity for forecast bias
CONF_DC_WIND = "dc_wind"          # optional: wind sensor for the lead model
CONF_DC_WINDOW = "dc_window"      # optional: window binary_sensor -> lockout
# Real heating/cooling demand (F27): optional, replaces the inferred valve signal.
CONF_DC_VALVE = "dc_valve"           # (c) real relay/power state (most reliable)
CONF_DC_DEMAND_HEAT = "dc_demand_heat"  # (b) explicit heat-demand helper
CONF_DC_DEMAND_COOL = "dc_demand_cool"  # (b) explicit cool-demand helper
CONF_DC_DEHUMIDIFIER = "dc_dehumidifier"  # F22: optional dehumidifier to drive
CONF_DC_ADJ_TEMP = "dc_adj_temp"   # F31: adjacent space (terrace/sunroom) temp
CONF_DC_ADJ_DOOR = "dc_adj_door"   # F31: optional door binary_sensor to it
CONF_EXPOSE_MIRRORS = "expose_mirrors"  # F36: expose stable per-role mirror sensors

# --- F26 Installation profile (declared per DC entry, stored in entry.options) ---
# Three independent dimensions; a (generator, distribution, emission) triple
# derives the inertia class + the compressor/peak/community flags F09/F03 consume.
CONF_GENERATOR = "dc_generator"          # heat source (heat pump / boiler / electric)
CONF_DISTRIBUTION = "dc_distribution"    # individual vs central (shared/communal)
CONF_EMISSION = "dc_emission"            # emitter -> thermal inertia class

# --- F06 Energy: optional real power meter (shared key across VMC/DC/DS) ---
# When set, the module integrates this sensor's power instead of the estimate.
CONF_POWER_METER = "power_meter"

# --- F21 Weekly scheduler (shared editor; independent profile per entry) ---
# Stored in entry.options: {"0": [{"start": "HH:MM", "value": x}, ...], ... "6": []}
# value = base setpoint (°C) for DC, base speed 0..3 for DV. Up to 4 slots/day.
CONF_SCHEDULE = "schedule_week"

# --- F33 Weather (resilient multi-source forecast/alert provider) ---
CONF_WX_SOURCE_1 = "wx_source_1"   # primary weather.* entity
CONF_WX_SOURCE_2 = "wx_source_2"   # secondary (fallback)
CONF_WX_SOURCE_3 = "wx_source_3"   # tertiary (fallback)
CONF_WX_TEMP = "wx_temp"           # raw-sensor fallback: temperature
CONF_WX_WIND = "wx_wind"           # raw-sensor fallback: wind (km/h)
CONF_WX_PRECIP = "wx_precip"       # raw-sensor fallback: precipitation (mm)
# Per-field raw-sensor inputs (optional): fill a value the active providers don't
# expose, or plug a dedicated sensor (e.g. Google Weather's individual sensors).
CONF_WX_HUMIDITY = "wx_humidity"        # %
CONF_WX_PRESSURE = "wx_pressure"        # hPa
CONF_WX_GUST = "wx_gust"                # wind gust (km/h)
CONF_WX_UV = "wx_uv"                    # UV index
CONF_WX_CLOUD = "wx_cloud"              # cloud coverage (%)
CONF_WX_DEWPOINT = "wx_dewpoint"        # dew point (°C)
CONF_WX_STORM_PROB = "wx_storm_prob"    # thunderstorm probability (%)
CONF_WX_PRECIP_PROB = "wx_precip_prob"  # precipitation probability (%)
EVENT_WEATHER_SOURCE = f"{DOMAIN}_weather_source"  # active source changed

# --- F24 Zones/groups hierarchy (own structure, not HA Areas) ---
CONF_ZONES_TREE = "zones_tree"     # the whole tree, stored in the entry's options
DATA_ZONES = "_zones_tree"         # published in hass.data[DOMAIN] for consumers

# --- F01 House modes (live on the zones entry; bias modules by scope) ---
CONF_MODE_CAPS = "mode_caps"       # per-mode VMC speed cap (options dict)
CONF_DS_PEAK = "ds_peak"           # global shutter peak limit (Zones options dict)
DATA_MODE = "_mode"                # resolved modes published in hass.data[DOMAIN]
EVENT_MODE_CHANGED = f"{DOMAIN}_mode_changed"

# --- F32 Presence (lives on the zones entry; fuses sources -> per-zone + house) ---
CONF_PRESENCE_SOURCES = "presence_sources"  # {zid: {pir:[], mmwave:[], door:[]}}
CONF_PRESENCE_PHONES = "presence_phones"    # house-global device_tracker/person ids
CONF_PRESENCE_AUTO = "presence_auto"        # auto-drive the house mode (home/away/sleep)
CONF_PRESENCE_TUNE = "presence_tune"        # optional PresenceConfig overrides (dict)
DATA_PRESENCE = "_presence"                 # resolved presence published in hass.data
EVENT_PRESENCE_CHANGED = f"{DOMAIN}_presence_changed"

# --- F37 Community changeover (seasonal water mode; lives on the zones entry) ---
# A 2-pipe community radiant system sends hot OR cold water to the whole building;
# the house changeover direction gates the community (central_shared) zones.
CONF_CHANGEOVER_SENSOR = "changeover_sensor"  # supply-water temperature sensor
CONF_CHANGEOVER_TUNE = "changeover_tune"      # threshold overrides (dict)
DATA_CHANGEOVER = "_changeover"               # resolved changeover published in hass.data
EVENT_CHANGEOVER_CHANGED = f"{DOMAIN}_changeover_changed"

# --- F33 Dynamic Weather: published so DC/DS auto-consume it when it exists ---
DATA_WEATHER = "_weather"          # {"source": weather.* for forecast, "alert": bool}

# --- F34 Dynamic Energy (singleton module; publishes house energy context) ---
CONF_ENERGY_GRID = "energy_grid"          # grid import power (W)
CONF_ENERGY_PRICE = "energy_price"        # electricity price sensor (€/kWh)
CONF_ENERGY_CONTRACTED = "energy_contracted_w"  # contracted power / ICP (W)
CONF_ENERGY_TOTAL = "energy_total"        # optional whole-house consumption (W)
CONF_ENERGY_PV = "energy_pv"              # optional PV production (W) — gated (⚠️)
CONF_ENERGY_BATT_SOC = "energy_batt_soc"  # optional battery SoC (%) — gated (⚠️)
DATA_ENERGY = "_energy"                   # resolved energy context published in hass.data
EVENT_ENERGY_CHANGED = f"{DOMAIN}_energy_changed"

# --- Options keys (VMC IAQ thresholds; mirror DvConfig field names) ---
# The full catalogue of UI-tunable parameters lives in ``options_spec.py``;
# these aliases are kept because the number platform references them directly.
OPT_CO2_V2 = "co2_v2"
OPT_CO2_V3 = "co2_v3"
OPT_PM_V2 = "pm_v2"
OPT_PM_V3 = "pm_v3"
OPT_FILTER_LIFE_HOURS = "filter_life_hours"

# Filter life: replacement interval default + due/clear thresholds (% remaining,
# with hysteresis so the "filter due" event fires once per crossing).
FILTER_LIFE_DEFAULT = 3650.0
FILTER_DUE_PCT = 10.0
FILTER_CLEAR_PCT = 15.0

# --- Services (dynamic_home.*) ---
SERVICE_RESET_LEARNING = "reset_learning"
SERVICE_SET_OBSERVE = "set_observe"
SERVICE_RESET_FILTER = "reset_filter"
SERVICE_RECALIBRATE = "recalibrate"
SERVICE_BOOST = "boost"
SERVICE_EXPORT_OPTIONS = "export_options"
SERVICE_IMPORT_OPTIONS = "import_options"
ATTR_ENABLED = "enabled"
ATTR_MINUTES = "minutes"
ATTR_VALUES = "values"
BOOST_MIN_DEFAULT = 15.0

# --- Native events (fired on transitions only, never every cycle) ---
EVENT_DEGRADED = f"{DOMAIN}_degraded"
EVENT_CONFLICT = f"{DOMAIN}_conflict"
EVENT_FILTER_DUE = f"{DOMAIN}_filter_due"
EVENT_MOLD = f"{DOMAIN}_mold"
EVENT_WINDOW = f"{DOMAIN}_window"
EVENT_ADJACENT = f"{DOMAIN}_adjacent"

# Guard key in hass.data[DOMAIN]: services are registered once for the whole
# integration (not per entry) and removed when the last entry unloads.
DATA_SERVICES_REGISTERED = "_services_registered"

# --- Repairs (HA issue registry) ---
# A DC zone is "degraded" when a mode is demanded but its required indoor source
# is missing. Once it stays degraded longer than ISSUE_STALE_S we raise a repair
# issue (a transient blip on restart should not nag the user).
ISSUE_REQUIRED_SOURCE = "required_source_missing"
# F37/F07: free-cooling can vent paid heat when no changeover is configured.
ISSUE_FREECOOL_NO_CHANGEOVER = "freecool_no_changeover"
ISSUE_STALE_S = 300.0
# A DC zone whose mold-risk index stays armed raises a (health) repair issue.
ISSUE_MOLD_RISK = "mold_risk"
ISSUE_COND_UNPROTECTED = "cond_unprotected"
# A VMC whose filter life crossed the replacement threshold raises a repair (F08).
ISSUE_FILTER_DUE = "filter_due"
LEARN_MORE_URL = "https://github.com/woody-box/dynamic-home"

# How often the coordinator re-evaluates the control pipeline (seconds).
UPDATE_INTERVAL_S = 60

# Fan preset modes. "off" is a manual stop that the engine will NOT override
# (unlike turning the power switch off while still in auto).
PRESET_AUTO = "auto"
PRESET_V1 = "v1"
PRESET_V2 = "v2"
PRESET_V3 = "v3"
PRESET_OFF = "off"
PRESET_MODES = [PRESET_AUTO, PRESET_V1, PRESET_V2, PRESET_V3, PRESET_OFF]

# 3 logical speeds -> percentage steps for the fan entity.
SPEED_COUNT = 3

# Break-before-make settle time between speed relays (s): never energise V2 and
# V3 at once. Drop both, wait, then close only the wanted one.
RELAY_SETTLE_S = 0.3

# Manual override: minutes after which a manual preset auto-reverts to auto
# (0 disables the timer). Bounds for the configuring number entity.
OVERRIDE_MIN_DEFAULT = 0
OVERRIDE_MIN_MAX = 480
