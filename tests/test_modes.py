"""Tests for house modes (F01): pure helpers + DV engine + HA integration."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..",
                                "custom_components", "dynamic_home"))

import modes  # noqa: E402
import zones  # noqa: E402
from dv_engine import DvConfig, DvInputs, DvState, decide  # noqa: E402
from homeassistant.core import HomeAssistant  # noqa: E402
from pytest_homeassistant_custom_component.common import (  # noqa: E402
    MockConfigEntry,
)

from custom_components.dynamic_home import const  # noqa: E402


# --- pure helpers ---
def test_effective_mode_zone_override_wins():
    assert modes.effective_mode("home", "sleep") == "sleep"
    assert modes.effective_mode("away", "auto") == "away"     # auto inherits house
    assert modes.effective_mode("eco", None) == "eco"


def test_effective_mode_for_entry():
    t = zones.assign_modules(zones.add_zone({}, "Salon"), "salon", ["dv1"])
    assert modes.effective_mode_for_entry(t, "home", {"salon": "sleep"}, "dv1") \
        == "sleep"
    assert modes.effective_mode_for_entry(t, "eco", {}, "dv1") == "eco"
    assert modes.effective_mode_for_entry(t, "boost", {}, "ghost") == "boost"


def test_dv_cap_and_flags():
    assert modes.dv_cap("sleep") == 1
    assert modes.dv_cap("home") is None
    assert modes.dv_cap("eco", {"eco": 2}) == 2
    assert modes.is_away("away") and modes.is_boost("boost")


def test_is_paused_global_and_per_module():
    assert modes.is_paused(None, "climate") is False
    assert modes.is_paused({"pause": {"shutter": True}}, "shutter") is True
    assert modes.is_paused({"pause": {"shutter": True}}, "climate") is False
    # Global pause hits every module.
    assert modes.is_paused({"pause": {"all": True}}, "vmc") is True
    assert modes.is_paused({"pause": {"all": True}}, "climate") is True


# --- DV engine: mode cap / boost on the auto path ---
def _dv():
    return _cfg(), DvState()


def _cfg(**kw):
    c = DvConfig(co2_ema_enabled=False, pm_ema_enabled=False)
    for k, v in kw.items():
        setattr(c, k, v)
    return c


def test_mode_cap_lowers_speed():
    cfg, st = _dv()
    ins = DvInputs(co2_raw=1400, pm_raw=5, current_speed=3, trigger_is_iaq=True,
                   mode_cap=1)                       # 1400 -> V3 but not critical
    d = decide(cfg, st, ins)
    assert d.speed == 1 and d.reason == "mode_cap"


def test_mode_cap_yields_to_critical_air():
    cfg, st = _dv()
    ins = DvInputs(co2_raw=cfg.quiet_critical_co2 + 100, pm_raw=5,
                   current_speed=3, trigger_is_iaq=True, mode_cap=1)
    d = decide(cfg, st, ins)
    assert d.speed == 3                    # health overrides the mode cap


def test_mode_boost_forces_v3():
    cfg, st = _dv()
    ins = DvInputs(co2_raw=400, pm_raw=2, current_speed=1, trigger_is_iaq=True,
                   mode_boost=True)
    d = decide(cfg, st, ins)
    assert d.speed == 3 and d.reason == "mode_boost"


# --- integration ---
async def test_house_mode_select_and_publish(hass: HomeAssistant) -> None:
    from homeassistant.helpers import entity_registry as er
    tree = zones.add_zone({}, "Salon")
    entry = MockConfigEntry(
        domain=const.DOMAIN, title="Zonas", unique_id="zones_singleton",
        data={const.CONF_NAME: "Zonas", const.CONF_MODULE: const.MODULE_ZONES},
        options={const.CONF_ZONES_TREE: tree})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    reg = er.async_get(hass)
    house_id = reg.async_get_entity_id("select", const.DOMAIN,
                                       f"{entry.entry_id}_house_mode")
    assert house_id is not None
    assert reg.async_get_entity_id("select", const.DOMAIN,
                                   f"{entry.entry_id}_mode_salon") is not None

    await hass.services.async_call(
        "select", "select_option",
        {"entity_id": house_id, "option": "sleep"}, blocking=True)
    await hass.async_block_till_done()
    assert hass.data[const.DOMAIN][const.DATA_MODE]["house"] == "sleep"


_VMC = {
    const.CONF_NAME: "VMC", const.CONF_MODULE: const.MODULE_VMC,
    const.CONF_SW_PWR: "switch.p", const.CONF_SW_V2: "switch.v2",
    const.CONF_SW_V3: "switch.v3", const.CONF_CO2: "sensor.co2",
    const.CONF_PM25: "sensor.pm",
}


async def test_sleep_caps_vmc_and_away_sets_dc_vacation(
        hass: HomeAssistant) -> None:
    from pytest_homeassistant_custom_component.common import async_mock_service
    async_mock_service(hass, "switch", "turn_on")
    async_mock_service(hass, "switch", "turn_off")
    for e in ("switch.p", "switch.v2", "switch.v3"):
        hass.states.async_set(e, "off")
    hass.states.async_set("sensor.co2", "1400")       # -> V3 but not critical
    hass.states.async_set("sensor.pm", "5")
    hass.states.async_set("sensor.dc_temp", "18")

    dv = MockConfigEntry(domain=const.DOMAIN, data=_VMC, options={}, title="VMC")
    dv.add_to_hass(hass)
    assert await hass.config_entries.async_setup(dv.entry_id)
    dc = MockConfigEntry(domain=const.DOMAIN, title="Salon", data={
        const.CONF_NAME: "Salon", const.CONF_MODULE: const.MODULE_CLIMATE,
        const.CONF_DC_T_INT: "sensor.dc_temp", const.CONF_DC_TARGET: "ds"})
    dc.add_to_hass(hass)
    assert await hass.config_entries.async_setup(dc.entry_id)
    await hass.async_block_till_done()

    # A zone holding both modules.
    tree = zones.assign_modules(zones.add_zone({}, "Salon"), "salon",
                                [dv.entry_id, dc.entry_id])
    zentry = MockConfigEntry(
        domain=const.DOMAIN, title="Zonas", unique_id="zones_singleton",
        data={const.CONF_NAME: "Zonas", const.CONF_MODULE: const.MODULE_ZONES},
        options={const.CONF_ZONES_TREE: tree})
    zentry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(zentry.entry_id)
    await hass.async_block_till_done()

    from homeassistant.helpers import entity_registry as er
    house_id = er.async_get(hass).async_get_entity_id(
        "select", const.DOMAIN, f"{zentry.entry_id}_house_mode")

    # Sleep -> the zone's VMC auto speed is capped (acceptance #1).
    await hass.services.async_call(
        "select", "select_option",
        {"entity_id": house_id, "option": "sleep"}, blocking=True)
    await hass.async_block_till_done()
    assert hass.data[const.DOMAIN][dv.entry_id].data.speed == 1

    # Away -> DC enters vacation without its own switch (acceptance #2).
    await hass.services.async_call(
        "select", "select_option",
        {"entity_id": house_id, "option": "away"}, blocking=True)
    await hass.async_block_till_done()
    dc_co = hass.data[const.DOMAIN][dc.entry_id]
    assert dc_co.vacation_enabled is False
    assert modes.is_away(dc_co._mode()) is True


# --- F23: comfort↔economy presets ---
async def _setup_zone_with_dv_dc(hass: HomeAssistant):
    """A zone holding one VMC + one DC, plus the zones entry. Returns the ids."""
    from pytest_homeassistant_custom_component.common import async_mock_service
    async_mock_service(hass, "switch", "turn_on")
    async_mock_service(hass, "switch", "turn_off")
    for e in ("switch.p", "switch.v2", "switch.v3"):
        hass.states.async_set(e, "off")
    hass.states.async_set("sensor.co2", "500")
    hass.states.async_set("sensor.pm", "5")
    hass.states.async_set("sensor.dc_temp", "21")

    dv = MockConfigEntry(domain=const.DOMAIN, data=_VMC, options={}, title="VMC")
    dv.add_to_hass(hass)
    assert await hass.config_entries.async_setup(dv.entry_id)
    dc = MockConfigEntry(domain=const.DOMAIN, title="Salon", data={
        const.CONF_NAME: "Salon", const.CONF_MODULE: const.MODULE_CLIMATE,
        const.CONF_DC_T_INT: "sensor.dc_temp", const.CONF_DC_TARGET: "ds"})
    dc.add_to_hass(hass)
    assert await hass.config_entries.async_setup(dc.entry_id)
    await hass.async_block_till_done()

    tree = zones.assign_modules(zones.add_zone({}, "Salon"), "salon",
                                [dv.entry_id, dc.entry_id])
    zentry = MockConfigEntry(
        domain=const.DOMAIN, title="Zonas", unique_id="zones_singleton",
        data={const.CONF_NAME: "Zonas", const.CONF_MODULE: const.MODULE_ZONES},
        options={const.CONF_ZONES_TREE: tree})
    zentry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(zentry.entry_id)
    await hass.async_block_till_done()
    return dv, dc, zentry


async def _select(hass, entry, uid_suffix, option):
    from homeassistant.helpers import entity_registry as er
    eid = er.async_get(hass).async_get_entity_id(
        "select", const.DOMAIN, f"{entry.entry_id}_{uid_suffix}")
    assert eid is not None
    await hass.services.async_call(
        "select", "select_option", {"entity_id": eid, "option": option},
        blocking=True)
    await hass.async_block_till_done()


async def test_comfort_global_shifts_dc_and_dv(hass: HomeAssistant) -> None:
    from dc_engine import DcConfig
    from dv_engine import DvConfig
    dv, dc, zentry = await _setup_zone_with_dv_dc(hass)
    dv_co = hass.data[const.DOMAIN][dv.entry_id]
    dc_co = hass.data[const.DOMAIN][dc.entry_id]

    # Default (balanced) -> config untouched.
    assert dc_co._cfg().base_heat_day == DcConfig().base_heat_day
    assert dv_co._cfg().co2_v2 == DvConfig().co2_v2

    # Eco -> wider DC band + higher DV thresholds (less ventilation).
    await _select(hass, zentry, "comfort", "eco")
    assert dc_co._cfg().base_heat_day < DcConfig().base_heat_day
    assert dc_co._cfg().base_cool_day > DcConfig().base_cool_day
    assert dv_co._cfg().co2_v2 > DvConfig().co2_v2

    # Back to balanced restores the defaults.
    await _select(hass, zentry, "comfort", "balanced")
    assert dc_co._cfg().base_heat_day == DcConfig().base_heat_day


async def test_comfort_zone_override_and_eco_mode_link(hass: HomeAssistant) -> None:
    from dc_engine import DcConfig
    dv, dc, zentry = await _setup_zone_with_dv_dc(hass)
    dc_co = hass.data[const.DOMAIN][dc.entry_id]

    # Per-zone override: Comfort tightens the band even with global balanced.
    await _select(hass, zentry, "comfort_salon", "comfort")
    assert dc_co._cfg().base_heat_day > DcConfig().base_heat_day

    # F01 link: with the dials neutral, the Eco house mode pulls the eco preset.
    await _select(hass, zentry, "comfort_salon", "auto")
    await _select(hass, zentry, "house_mode", "eco")
    assert dc_co._cfg().base_heat_day < DcConfig().base_heat_day
