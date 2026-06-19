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

# --- Options keys (tunables, mirror the engine *Config dataclasses) ---
# VMC (Dv).
OPT_CO2_V2 = "co2_v2"
OPT_CO2_V3 = "co2_v3"
OPT_PM_V2 = "pm_v2"
OPT_PM_V3 = "pm_v3"

# Shutter (DS).
OPT_DS_WIND_LIMIT = "ds_wind_limit_kmh"
OPT_DS_WEATHER_MAX_OPEN = "ds_weather_max_open_pct"
OPT_DS_SHIELD_MAX_OPEN = "ds_shield_max_open_pct"
OPT_DS_WINTER_NIGHT = "ds_winter_night_pct"
OPT_DS_SLEW_STEP = "ds_slew_step_pct"

# Climate (DC).
OPT_DC_BASE_HEAT = "dc_base_heat_day"
OPT_DC_BASE_COOL = "dc_base_cool_day"
OPT_DC_DELTA_NIGHT = "dc_delta_night"
OPT_DC_DEW_SPREAD = "dc_dew_spread_min"
OPT_DC_MAX_MODS_HEAT = "dc_max_mods_heat"
OPT_DC_MAX_MODS_COOL = "dc_max_mods_cool"

# Defaults for the tunables above (must match the engine dataclass defaults).
DS_DEFAULTS = {
    OPT_DS_WIND_LIMIT: 40.0,
    OPT_DS_WEATHER_MAX_OPEN: 30,
    OPT_DS_SHIELD_MAX_OPEN: 30,
    OPT_DS_WINTER_NIGHT: 0,
    OPT_DS_SLEW_STEP: 10,
}
DC_DEFAULTS = {
    OPT_DC_BASE_HEAT: 22.5,
    OPT_DC_BASE_COOL: 26.5,
    OPT_DC_DELTA_NIGHT: 0.5,
    OPT_DC_DEW_SPREAD: 2.0,
    OPT_DC_MAX_MODS_HEAT: 0.8,
    OPT_DC_MAX_MODS_COOL: 0.8,
}

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
