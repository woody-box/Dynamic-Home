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


# --- Per-zone sleep schedule -------------------------------------------------
def test_in_window_wraps_midnight_and_empty_is_off():
    assert modes.in_window(23 * 60, 22 * 60 + 30, 8 * 60) is True
    assert modes.in_window(7 * 60, 22 * 60 + 30, 8 * 60) is True
    assert modes.in_window(8 * 60, 22 * 60 + 30, 8 * 60) is False   # end excluded
    assert modes.in_window(15 * 60, 22 * 60 + 30, 8 * 60) is False
    assert modes.in_window(14 * 60, 13 * 60, 16 * 60) is True       # same-day
    assert modes.in_window(0, 600, 600) is False                    # start == end
    assert modes.in_window(0, None, 480) is False                   # no schedule


def test_schedule_applies_only_while_zone_is_auto():
    # auto + inside the window -> sleep; outside -> inherits (auto).
    assert modes.schedule_step("auto", True, True) == ("auto", "sleep")
    assert modes.schedule_step("auto", False, False) == ("auto", "auto")
    # A manual pick wins while no window edge happens.
    assert modes.schedule_step("home", True, True) == ("home", "home")
    assert modes.schedule_step("sleep", False, False) == ("sleep", "sleep")


def test_window_edge_clears_home_sleep_picks_only():
    # Stayed up ("home") during the window: the morning edge hands back to auto.
    assert modes.schedule_step("home", False, True) == ("auto", "auto")
    # An afternoon nap ("sleep"): the evening edge hands it to the schedule.
    assert modes.schedule_step("sleep", True, False) == ("auto", "sleep")
    # Long-lived picks (away / eco / boost) survive the edges.
    assert modes.schedule_step("away", True, False) == ("away", "away")
    assert modes.schedule_step("eco", False, True) == ("eco", "eco")


def test_first_reading_is_not_an_edge():
    # A restart must never wipe a restored manual pick.
    assert modes.schedule_step("home", True, None) == ("home", "home")


def test_zone_tree_keeps_sleep_schedule():
    tree = zones.normalize({"zones": {"h2": {
        "name": "H2", "modules": ["e1"], "sleep_start": 1350, "sleep_end": 480}}})
    z = tree["zones"]["h2"]
    assert (z["sleep_start"], z["sleep_end"]) == (1350, 480)
    # A half-configured schedule is dropped (both ends or nothing).
    tree = zones.normalize({"zones": {"h2": {"name": "H2", "sleep_start": 1350}}})
    assert "sleep_start" not in tree["zones"]["h2"]


async def test_zone_sleep_schedule_drives_published_mode(
        hass: HomeAssistant) -> None:
    """Zone "h2" (22:30–08:00): auto sleeps in the window; a manual "home" at
    night lasts until the morning edge; the house mode rules outside."""
    from custom_components.dynamic_home import const
    tree = {"zones": {"h2": {"name": "H2", "modules": ["ds1"],
                             "sleep_start": 22 * 60 + 30, "sleep_end": 8 * 60}},
            "groups": {}}
    entry = MockConfigEntry(
        domain=const.DOMAIN, title="Zonas",
        data={const.CONF_NAME: "Zonas", const.CONF_MODULE: const.MODULE_ZONES},
        options={const.CONF_ZONES_TREE: tree})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    co = hass.data[const.DOMAIN][entry.entry_id]
    assert co.update_interval is not None           # a schedule needs polling

    def mode_for_ds1():
        return modes.effective_from_published(
            hass.data[const.DOMAIN][const.DATA_MODE], "ds1")

    co._schedule_tick(15 * 60)                       # afternoon: house mode
    assert mode_for_ds1() == "home"
    co._schedule_tick(23 * 60)                       # inside the window
    assert mode_for_ds1() == "sleep"
    assert co.zone_modes.get("h2", "auto") == "auto"  # the pick stays auto
    # Staying up: a manual "home" wins for the rest of the night...
    co.zone_modes["h2"] = "home"
    co._schedule_tick(23 * 60 + 30)
    assert mode_for_ds1() == "home"
    # ...until the morning edge hands it back to the schedule (auto).
    co._schedule_tick(8 * 60)
    assert co.zone_modes["h2"] == "auto"
    assert mode_for_ds1() == "home"                  # house mode again
    co._schedule_tick(22 * 60 + 30)                  # next night: sleeps alone
    assert mode_for_ds1() == "sleep"
