"""Human-readable reason text mapping."""
from custom_components.dynamic_home import reason_text
from custom_components.dynamic_home.const import (
    MODULE_CLIMATE,
    MODULE_SHUTTER,
    MODULE_VMC,
)


def test_humanize_known_codes():
    assert reason_text.humanize(MODULE_CLIMATE, "cool") == "Refrigerando"
    assert reason_text.humanize(MODULE_CLIMATE, "off_dew") == "Parado: riesgo de condensación"
    assert reason_text.humanize(MODULE_SHUTTER, "dawn_ramp") == "Apertura por amanecer"
    assert reason_text.humanize(MODULE_SHUTTER, "summer_solar_geo") == "Sombreado solar (geométrico)"
    assert reason_text.humanize(MODULE_VMC, "dry_mode") == "Modo secado"
    assert reason_text.humanize(MODULE_VMC, "iaq_ok") == "Calidad de aire correcta"


def test_humanize_fallback_and_none():
    # Unknown code -> returned as-is (forward-compatible); None -> None.
    assert reason_text.humanize(MODULE_SHUTTER, "some_future_reason") == "some_future_reason"
    assert reason_text.humanize(MODULE_VMC, None) is None
    assert reason_text.humanize("nope", "cool") == "cool"
