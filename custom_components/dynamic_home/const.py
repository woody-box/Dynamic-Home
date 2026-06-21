"""Constants for the Dynamic Home integration (DV + DS)."""

from __future__ import annotations

DOMAIN = "dynamic_home"

# Module discriminator stored in each config entry.
CONF_MODULE = "module"
MODULE_VMC = "vmc"
MODULE_SHUTTER = "shutter"
MODULE_CLIMATE = "climate_zone"

# Platforms forwarded per module.
PLATFORMS_VMC: list[str] = ["fan", "number", "sensor", "button", "switch", "time"]
PLATFORMS_SHUTTER: list[str] = ["cover", "switch", "number"]
PLATFORMS_CLIMATE: list[str] = ["climate", "switch", "sensor", "binary_sensor"]

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

REQUIRED_HW = (CONF_SW_PWR, CONF_SW_V2, CONF_SW_V3, CONF_CO2, CONF_PM25)
OPTIONAL_HW = (CONF_T_IN, CONF_T_EXT, CONF_AQI, CONF_HUM_BATH, CONF_HUM_EXT)

# --- Config entry keys: Shutter (DS) ---
CONF_COVER = "cover"
CONF_CLIMATE = "climate"          # optional: source of hvac mode (cool/heat)
CONF_DS_T_IN = "ds_t_in"
CONF_DS_T_OUT = "ds_t_out"
CONF_WIND = "wind"
CONF_RAIN = "rain"
CONF_FACADE_AZIMUTH = "facade_azimuth_deg"
CONF_FACADE_SPAN = "facade_span_deg"

# --- Config entry keys: Climate (DC) ---
CONF_DC_T_INT = "dc_t_int"        # required: indoor temperature sensor
CONF_DC_T_EXT = "dc_t_ext"        # optional: outdoor temperature sensor
CONF_DC_TARGET = "ds_target"      # shutter target the zone drives (default "ds")
CONF_DC_CLIMATE = "dc_climate"    # optional: real thermostat DC drives
CONF_DC_VMC = "dc_vmc"            # optional: VMC fan/sensor for the VMC bias
CONF_DC_HUMIDITY = "dc_humidity"  # optional: indoor RH for dew-point protection
CONF_DC_WEATHER = "dc_weather"    # optional: weather entity for forecast bias
CONF_DC_WIND = "dc_wind"          # optional: wind sensor for the lead model
CONF_DC_WINDOW = "dc_window"      # optional: window binary_sensor -> lockout

# --- Options keys (VMC IAQ thresholds; mirror DvConfig field names) ---
# The full catalogue of UI-tunable parameters lives in ``options_spec.py``;
# these aliases are kept because the number platform references them directly.
OPT_CO2_V2 = "co2_v2"
OPT_CO2_V3 = "co2_v3"
OPT_PM_V2 = "pm_v2"
OPT_PM_V3 = "pm_v3"

# --- Services (dynamic_home.*) ---
SERVICE_RESET_LEARNING = "reset_learning"
SERVICE_SET_OBSERVE = "set_observe"
SERVICE_RESET_FILTER = "reset_filter"
SERVICE_RECALIBRATE = "recalibrate"
ATTR_ENABLED = "enabled"

# --- Native events (fired on transitions only, never every cycle) ---
EVENT_DEGRADED = f"{DOMAIN}_degraded"
EVENT_CONFLICT = f"{DOMAIN}_conflict"
EVENT_FILTER_DUE = f"{DOMAIN}_filter_due"
EVENT_MODE_CHANGED = f"{DOMAIN}_mode_changed"

# Guard key in hass.data[DOMAIN]: services are registered once for the whole
# integration (not per entry) and removed when the last entry unloads.
DATA_SERVICES_REGISTERED = "_services_registered"

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
