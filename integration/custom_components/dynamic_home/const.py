"""Constants for the Dynamic Home integration (DV + DS)."""

from __future__ import annotations

DOMAIN = "dynamic_home"

# Module discriminator stored in each config entry.
CONF_MODULE = "module"
MODULE_VMC = "vmc"
MODULE_SHUTTER = "shutter"

# Platforms forwarded per module.
PLATFORMS_VMC: list[str] = ["fan", "number"]
PLATFORMS_SHUTTER: list[str] = ["cover"]

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

# --- Options keys (tunables, mirror engine.DvConfig) ---
OPT_CO2_V2 = "co2_v2"
OPT_CO2_V3 = "co2_v3"
OPT_PM_V2 = "pm_v2"
OPT_PM_V3 = "pm_v3"

# How often the coordinator re-evaluates the control pipeline (seconds).
UPDATE_INTERVAL_S = 60

# Fan preset modes.
PRESET_AUTO = "auto"
PRESET_V1 = "v1"
PRESET_V2 = "v2"
PRESET_V3 = "v3"
PRESET_MODES = [PRESET_AUTO, PRESET_V1, PRESET_V2, PRESET_V3]

# 3 logical speeds -> percentage steps for the fan entity.
SPEED_COUNT = 3
