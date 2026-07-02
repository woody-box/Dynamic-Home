"""DV coordinator: bridges Home Assistant state into the pure DV engine.

It reads the configured hardware entities, builds :class:`dv_engine.DvInputs`,
runs :func:`dv_engine.decide`, and exposes the resulting logical speed. The fan
entity drives the physical relays from this result.
"""

from __future__ import annotations

import logging
from collections import deque
from datetime import time as dtime
from datetime import timedelta

import homeassistant.helpers.issue_registry as ir
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from . import comfort, const, energy, events, modes, repairs, schedule, zones
from .bus import SdhbHub
from .dc_engine import dew_point
from .dv_engine import (
    DvConfig,
    DvDecision,
    DvInputs,
    DvState,
    decide,
    filter_life_pct,
    hood_speed,
    hrv_efficiency,
    hrv_state,
)
from .options_spec import apply_options

_LOGGER = logging.getLogger(__name__)


class DvCoordinator(repairs.DegradedTracker, DataUpdateCoordinator[DvDecision]):
    """Periodically evaluates the DV pipeline and tracks source-entity changes."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry,
                 hub: SdhbHub) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{const.DOMAIN}_dv",
            update_interval=timedelta(seconds=const.UPDATE_INTERVAL_S),
        )
        self.entry = entry
        self.hub = hub
        self.state_data = DvState()
        self.current_speed = 1
        self.auto_mode = True
        # Extractor hood (F35): auto speed from indoor PM + last applied speed.
        self.hood_speed_auto = 0
        self.hood_current = 0
        self.preset = "auto"            # mirrored from the fan, for the mode sensor
        self.in_grace = False           # within startup grace (observability)
        self.observe_enabled = False    # dry-run: compute but do not act on hw
        # Manual-override auto-revert: minutes (0 disables) + expiry timestamp.
        self.override_minutes = const.OVERRIDE_MIN_DEFAULT
        self.override_until: float | None = None
        self._iaq_dirty = False
        self._setup_ts = dt_util.utcnow().timestamp()
        # Telemetry (hours), accumulated between updates; persisted by sensors.
        self.speed_hours = {1: 0.0, 2: 0.0, 3: 0.0}
        self.machine_hours = 0.0
        self.filter_hours = 0.0
        self.energy_kwh = 0.0           # F06: cumulative energy (real or estimated)
        self.power_w = 0.0              # F06/REQ-ENE-5: instantaneous power (W)
        self._accum_ts: float | None = None
        # "Filter due" event arming (hysteresis so it fires once per crossing)
        # and the matching Repairs issue id (F08).
        self._filter_due_armed = True
        self._filter_issue_id = f"filter_{entry.entry_id}"
        # Startup bootstrap kick (opt-in, hardware quirk).
        self.bootstrap_enabled = False
        # Dry-mode (anti-condensation ventilation) toggle.
        self.dry_mode_enabled = False
        # Free-cooling master toggle (on by default = legacy behaviour); the
        # feature still needs both temp probes to actually run.
        self.freecool_enabled = True
        # Weekly schedule (same daily window every day).
        self.schedule_enabled = False
        self.schedule_on = dtime(7, 0)
        self.schedule_off = dtime(23, 0)
        # Quiet hours (F12): night cap window + max level.
        self.quiet_enabled = False
        self.quiet_max_level = 1
        self.quiet_start = dtime(23, 0)
        self.quiet_end = dtime(7, 0)
        # Timed V3 boost (F14): epoch until which boost is active (None = off).
        self.boost_until: float | None = None
        self.shower_bathroom: str | None = None   # F13: which bathroom triggered
        self._bath_baseline: dict[str, float] = {}  # slow RH baseline per bathroom
        # Observability snapshots (filled each cycle for the diagnostic sensors).
        self.shower_rise: float | None = None     # bathroom RH rise over its baseline
        self.shower_effective = True              # outside drier -> expelling helps
        self.shower_gate = False                  # shower boost prerequisites met
        self.iaq_snapshot: dict = {}              # live IAQ values vs thresholds
        # Adaptive thresholds: rolling history (~7 days @ 1 sample/min).
        self.adaptive_enabled = False
        # Learned thresholds (None until mature) + sample count, for observability.
        self.adaptive_co2_v2: float | None = None
        self.adaptive_co2_v3: float | None = None
        self.adaptive_pm_v2: float | None = None
        self.adaptive_pm_v3: float | None = None
        self.adaptive_samples = 0
        # Anticipatory ventilation (F11): pre-boost on a steep CO2/PM rise.
        self.anticip_enabled = False
        self._co2_hist: deque[float] = deque(maxlen=10080)
        self._pm_hist: deque[float] = deque(maxlen=10080)
        # Bus-conflict observability.
        self.bus_explain: dict = self.hub.explain(self.bus_listen_targets())
        self._prev_winner: str | None = None
        # Degraded / repair-issue tracking for required hardware (F07).
        self._module = const.MODULE_VMC
        self.init_degraded(entry)

    def bus_listen_targets(self):
        """Targets this VMC consumes from the bus."""
        return "dv"

    def _refresh_bus_explain(self, now_ts: float | None) -> None:
        """Recompute the consumed bus intent and fire a conflict event on change."""
        self.bus_explain = self.hub.explain(self.bus_listen_targets(), now_ts)
        winner = self.bus_explain["winner"]
        if winner != self._prev_winner:
            if not (self._prev_winner is None and winner == "none"):
                events.fire_conflict(self.hass, self.entry,
                                     const.MODULE_VMC, self.bus_explain)
            self._prev_winner = winner

    def _accumulate(self, now_ts: float, cfg: DvConfig) -> None:
        """Add elapsed time to the running-hours counters and energy (F06)."""
        if self._accum_ts is not None:
            dt_s = now_ts - self._accum_ts
            dt_h = dt_s / 3600.0
            spd = self.current_speed
            if spd in (1, 2, 3) and dt_h > 0:
                self.speed_hours[spd] += dt_h
                self.machine_hours += dt_h
                self.filter_hours += dt_h
            # Energy: a real power meter if configured, else the per-speed estimate.
            power = self._num(const.CONF_POWER_METER)
            if power is None:
                power = energy.vmc_power_w(
                    spd, (cfg.est_w_v1, cfg.est_w_v2, cfg.est_w_v3))
            self.energy_kwh = energy.add_kwh(self.energy_kwh, power, dt_s)
            self.power_w = float(power or 0.0)
        self._accum_ts = now_ts

    def reset_filter_hours(self) -> None:
        self.filter_hours = 0.0
        self._filter_due_armed = True
        self.clear_filter_issue()       # the filter is fresh again (F08)

    def start_boost(self, minutes: float) -> None:
        """Force V3 for ``minutes`` (F14); auto-reverts when the window elapses."""
        self.boost_until = dt_util.now().timestamp() + minutes * 60

    # --- Heat-recovery efficiency (F28) ---
    def has_hrv(self) -> bool:
        """Whether the 3 recuperator probes are configured (else no sensor)."""
        return all(self._hw(k) for k in (const.CONF_HRV_SUPPLY,
                                         const.CONF_HRV_INTAKE,
                                         const.CONF_HRV_EXTRACT))

    def _hrv_temps(self) -> tuple:
        return (self._num(const.CONF_HRV_SUPPLY), self._num(const.CONF_HRV_INTAKE),
                self._num(const.CONF_HRV_EXTRACT))

    @property
    def hrv_temperatures(self) -> dict:
        """All configured recuperator temperatures (°C) for observability.

        Supply/intake/extract drive the efficiency; exhaust (optional) is exposed
        too. Only the configured probes appear.
        """
        roles = (("supply", const.CONF_HRV_SUPPLY), ("intake", const.CONF_HRV_INTAKE),
                 ("extract", const.CONF_HRV_EXTRACT), ("exhaust", const.CONF_HRV_EXHAUST))
        return {name: self._num(key) for name, key in roles if self._hw(key)}

    @property
    def hrv_efficiency_pct(self) -> float | None:
        eff = hrv_efficiency(*self._hrv_temps())
        return None if eff is None else round(eff * 100, 1)

    @property
    def hrv_state(self) -> str | None:
        return hrv_state(*self._hrv_temps(), self._cfg())

    # --- Dew points (observability): the dry-mode (F13) gate at a glance ---
    def has_dew_in(self) -> bool:
        return bool(self._hw(const.CONF_T_IN) and self._hw(const.CONF_HUM_IN))

    def has_dew_out(self) -> bool:
        return bool(self._hw(const.CONF_T_EXT) and self._hw(const.CONF_HUM_EXT))

    @property
    def dew_point_in(self) -> float | None:
        return dew_point(self._num(const.CONF_T_IN), self._num(const.CONF_HUM_IN))

    @property
    def dew_point_out(self) -> float | None:
        return dew_point(self._num(const.CONF_T_EXT), self._num(const.CONF_HUM_EXT))

    @property
    def dew_point_diff(self) -> float | None:
        """dp_in - dp_out: > dry_margin means outside is drier (drying works)."""
        dp_in, dp_out = self.dew_point_in, self.dew_point_out
        return None if (dp_in is None or dp_out is None) else round(dp_in - dp_out, 2)

    # --- Extended IAQ (F30): VOC/NOx are observation-only, never enter decide() ---
    def has_voc(self) -> bool:
        return bool(self._hw(const.CONF_VOC))

    def has_nox(self) -> bool:
        return bool(self._hw(const.CONF_NOX))

    # --- Extractor hood (F35) ---
    def has_hood(self) -> bool:
        return any(self._hw(k) for k in (const.CONF_HOOD_V1, const.CONF_HOOD_V2,
                                         const.CONF_HOOD_V3))

    @property
    def voc_level(self) -> float | None:
        return self._num(const.CONF_VOC)

    @property
    def nox_level(self) -> float | None:
        return self._num(const.CONF_NOX)

    @property
    def filter_life_pct(self) -> float:
        """Remaining filter life (0..100 %) for the filter-life sensor."""
        return filter_life_pct(self.filter_hours, self._cfg().filter_life_hours)

    def _check_filter_due(self, cfg: DvConfig) -> None:
        """Fire the event and raise a Repairs issue once life drops below threshold.

        The event fires once per crossing (hysteresis); the Repairs issue (F08)
        is raised alongside it and removed when the filter recovers (i.e. after
        a reset takes life back above the clear threshold).
        """
        pct = filter_life_pct(self.filter_hours, cfg.filter_life_hours)
        if pct <= const.FILTER_DUE_PCT and self._filter_due_armed:
            events.fire_filter_due(self.hass, self.entry, const.MODULE_VMC,
                                   pct, self.filter_hours, cfg.filter_life_hours)
            ir.async_create_issue(
                self.hass, const.DOMAIN, self._filter_issue_id,
                is_fixable=False, severity=ir.IssueSeverity.WARNING,
                translation_key=const.ISSUE_FILTER_DUE,
                translation_placeholders={"name": self.entry.title,
                                          "pct": str(round(pct)),
                                          "life": str(round(cfg.filter_life_hours))},
                learn_more_url=const.LEARN_MORE_URL)
            self._filter_due_armed = False
        elif pct >= const.FILTER_CLEAR_PCT:
            self._filter_due_armed = True
            self.clear_filter_issue()

    def clear_filter_issue(self) -> None:
        """Remove this VMC's filter-due repair issue (no-op if absent)."""
        ir.async_delete_issue(self.hass, const.DOMAIN, self._filter_issue_id)

    # --- config helpers ---
    def _hw(self, key: str) -> str | None:
        return self.entry.data.get(key)

    def _paused(self) -> bool:
        """Master pause for this module (global or per-module, from Zones)."""
        return modes.is_paused(
            self.hass.data.get(const.DOMAIN, {}).get(const.DATA_MODE), "vmc")

    @property
    def observe_effective(self) -> bool:
        """Don't actuate when in observe OR while paused."""
        return self.observe_enabled or self._paused()

    def _cfg(self) -> DvConfig:
        cfg = DvConfig()
        apply_options(cfg, self.entry.options, const.MODULE_VMC)
        # Gates driven by hardware presence / switches, not by user options.
        # Free-cooling needs both probes AND the user's switch (v0.95.0: it was
        # not disable-able before — the probes' presence forced it on).
        cfg.freecool_enabled = (self.freecool_enabled
                                and bool(self._hw(const.CONF_T_IN)
                                         and self._hw(const.CONF_T_EXT)))
        cfg.hostile_enabled = bool(self._hw(const.CONF_AQI))
        cfg.shower_enabled = bool(self._bathrooms() and
                                  self._hw(const.CONF_HUM_EXT))
        cfg.adaptive_enabled = self.adaptive_enabled
        cfg.anticip_enabled = self.anticip_enabled
        # Quiet hours (F12): live entities -> engine config (critical thresholds
        # stay in options, overlaid by apply_options above).
        cfg.quiet_enabled = self.quiet_enabled
        cfg.quiet_max_level = int(self.quiet_max_level)
        cfg.quiet_start_min = self.quiet_start.hour * 60 + self.quiet_start.minute
        cfg.quiet_end_min = self.quiet_end.hour * 60 + self.quiet_end.minute
        if self.schedule_enabled and self.schedule_on and self.schedule_off:
            on_m = self.schedule_on.hour * 60 + self.schedule_on.minute
            off_m = self.schedule_off.hour * 60 + self.schedule_off.minute
            cfg.schedule_enabled = True
            cfg.schedule = {d: (on_m, off_m) for d in range(7)}
        # F23: comfort↔economy preset (global + per-zone), resolved like F01.
        comfort.apply_dv(cfg, comfort.effective_from_published(
            self.hass.data.get(const.DOMAIN, {}).get(const.DATA_MODE),
            self.entry.entry_id))
        return cfg

    def _house_changeover(self) -> str | None:
        """F37: the house heating/cooling season — per-zone override else house.

        Mirrors the DC/DS readers: ``DATA_CHANGEOVER`` with a per-zone split resolved
        via ``zones.scope_for_module``. ``None`` when no changeover is configured, so
        DV keeps its plain temperature-driven free-cooling (back-compat).
        """
        data = self.hass.data.get(const.DOMAIN, {}).get(const.DATA_CHANGEOVER)
        if not data:
            return None
        zmap = data.get("zones") or {}
        if zmap:
            tree = self.hass.data.get(const.DOMAIN, {}).get(const.DATA_ZONES)
            zid = (zones.scope_for_module(tree, self.entry.entry_id)["zone"]
                   if tree else None)
            if zid and zid in zmap:
                return zmap[zid]
        return data.get("state")

    def _freecool_changeover_advisory(self, cfg: DvConfig) -> None:
        """F37/F07: warn if free-cooling can vent paid heat with no changeover.

        Free-cooling is purely temperature-driven unless a changeover tells DV the
        season (F37). With free-cooling enabled, **a heating zone active**, and **no
        changeover configured**, a mild winter day (warmer inside than outside) would
        free-cool and vent the heat you are paying for. Raise a non-fixable advisory
        Repairs issue; clear it as soon as any of the three conditions stops holding
        (changeover configured, free-cooling off, or no zone heating).
        """
        issue_id = f"freecool_no_changeover_{self.entry.entry_id}"
        data = self.hass.data.get(const.DOMAIN, {})
        has_changeover = bool(data.get(const.DATA_CHANGEOVER))
        heating = any(getattr(co, "hvac_mode", None) == "heat"
                      for key, co in data.items()
                      if not key.startswith("_") and co is not self)
        if cfg.freecool_enabled and heating and not has_changeover:
            ir.async_create_issue(
                self.hass, const.DOMAIN, issue_id,
                is_fixable=False, severity=ir.IssueSeverity.WARNING,
                translation_key=const.ISSUE_FREECOOL_NO_CHANGEOVER,
                translation_placeholders={"name": self.entry.title},
                learn_more_url=const.LEARN_MORE_URL)
        else:
            ir.async_delete_issue(self.hass, const.DOMAIN, issue_id)

    def _update_adaptive(self, cfg: DvConfig, co2: float | None,
                         pm: float | None) -> tuple:
        """Append readings and derive adaptive thresholds from percentiles.

        Returns (co2_v2, co2_v3, pm_v2, pm_v3), each None until enough samples.
        """
        if co2 is not None and 0 <= co2 <= 5000:
            self._co2_hist.append(co2)
        if pm is not None and 0 <= pm <= 500:
            self._pm_hist.append(pm)
        if not self.adaptive_enabled:
            return (None, None, None, None)

        def pct(hist: deque, p: float) -> float | None:
            if len(hist) < cfg.adaptive_min_samples:
                return None
            s = sorted(hist)
            return s[min(len(s) - 1, int(p / 100.0 * len(s)))]

        return (pct(self._co2_hist, 90), pct(self._co2_hist, 95),
                pct(self._pm_hist, 90), pct(self._pm_hist, 95))

    def _age_s(self, key: str) -> float:
        """Seconds since the source entity last changed (large if missing)."""
        ent = self._hw(key)
        if not ent:
            return 1e9
        st = self.hass.states.get(ent)
        if st is None:
            return 1e9
        return (dt_util.utcnow() - st.last_updated).total_seconds()

    def _num(self, key: str) -> float | None:
        ent = self._hw(key)
        if not ent:
            return None
        st = self.hass.states.get(ent)
        if st is None or st.state in ("unknown", "unavailable", "none", ""):
            return None
        try:
            return float(st.state)
        except (TypeError, ValueError):
            return None

    # --- entity tracking ---
    @callback
    def async_setup_listeners(self) -> None:
        sources = [self._hw(k) for k in (const.CONF_CO2, const.CONF_PM25)]
        sources = [s for s in sources if s]
        if sources:
            self.entry.async_on_unload(
                async_track_state_change_event(
                    self.hass, sources, self._on_iaq_change)
            )

    @callback
    def _on_iaq_change(self, event) -> None:
        self._iaq_dirty = True
        self.hass.async_create_task(self.async_request_refresh())

    # --- the actual update ---
    def _num_entity(self, ent: str | None) -> float | None:
        """Float state of a specific entity id (used for option-stored sensors)."""
        if not ent:
            return None
        st = self.hass.states.get(ent)
        if st is None or st.state in ("unknown", "unavailable", "none", ""):
            return None
        try:
            return float(st.state)
        except (TypeError, ValueError):
            return None

    def _bathrooms(self) -> list[tuple[str | None, str]]:
        """Configured ``(name, humidity entity)`` bathrooms for the shower boost.

        The per-bathroom list (VMC options, F13) takes precedence; if none is
        configured it falls back to the single legacy ``hum_bath`` from the
        initial config (back-compat, one unnamed bathroom).
        """
        o = self.entry.options
        out: list[tuple[str | None, str]] = []
        for i in range(1, const.BATHROOM_MAX + 1):
            ent = o.get(f"{const.CONF_BATH_HUM}_{i}")
            if ent:
                out.append((o.get(f"{const.CONF_BATH_NAME}_{i}") or f"Baño {i}",
                            ent))
        if not out and self._hw(const.CONF_HUM_BATH):
            out.append((None, self._hw(const.CONF_HUM_BATH)))
        return out

    def _shower_signal(self, cfg: DvConfig) -> float | None:
        """Shower-detection signal fed to the engine (F13).

        Detection = the bathroom's own RH **rise** over a slow baseline (a shower
        spikes it; a steady level — even one well above the dry outdoor air —
        does not). The outdoor humidity is only an **effectiveness gate**: boost
        to expel only when the outside air is drier. The baseline EMA is frozen
        while a shower is latched so it keeps the pre-shower level.

        Sets ``shower_rise`` (the real rise), ``shower_bathroom`` and
        ``shower_effective`` for the diagnostic sensor. Returns the value the
        engine latches on (the rise, or 0 when expelling wouldn't help), or
        ``None`` if there's no bathroom reading.
        """
        frozen = self.state_data.shower_active   # keep the pre-shower baseline
        best_rise: float | None = None
        best_name: str | None = None
        best_rh: float | None = None
        for name, ent in self._bathrooms():
            rh = self._num_entity(ent)
            if rh is None:
                continue
            base = self._bath_baseline.get(ent, rh)
            if not frozen:
                base += cfg.shower_baseline_alpha * (rh - base)
            self._bath_baseline[ent] = base
            rise = rh - base
            if best_rise is None or rise > best_rise:
                best_rise, best_name, best_rh = rise, name, rh
        self.shower_rise = best_rise
        self.shower_bathroom = best_name
        if best_rise is None:
            self.shower_effective = True
            return None
        ext = self._num(const.CONF_HUM_EXT)
        self.shower_effective = (ext is None
                                 or (best_rh - ext) > cfg.shower_effective_margin)
        return best_rise if self.shower_effective else 0.0

    def _dew(self, cfg: DvConfig) -> tuple[bool, float | None]:
        """(dew_risk, dp_diff) for dry-mode from indoor/outdoor temp+RH."""
        t_in = self._num(const.CONF_T_IN)
        t_ext = self._num(const.CONF_T_EXT)
        dp_in = dew_point(t_in, self._num(const.CONF_HUM_IN))
        dp_out = dew_point(t_ext, self._num(const.CONF_HUM_EXT))
        risk = dp_in is not None and t_in is not None and \
            (t_in - dp_in) < cfg.dew_spread_min
        dp_diff = (dp_in - dp_out) if (dp_in is not None and dp_out is not None) else None
        return risk, dp_diff

    async def _async_update_data(self) -> DvDecision:
        cfg = self._cfg()
        trigger_is_iaq = self._iaq_dirty
        self._iaq_dirty = False

        now = dt_util.now()  # local time for the weekly schedule
        now_ts = now.timestamp()
        self._refresh_bus_explain(now_ts)
        self._accumulate(now_ts, cfg)
        self._check_filter_due(cfg)
        self.degraded = self._update_degraded(self._missing_required(), now_ts)
        self._freecool_changeover_advisory(cfg)
        grace_active = (now_ts - self._setup_ts) < cfg.startup_grace_s
        self.in_grace = grace_active

        # Timed V3 boost (F14): active until its window elapses, then auto-clears.
        boost_active = self.boost_until is not None and now_ts < self.boost_until
        if self.boost_until is not None and now_ts >= self.boost_until:
            self.boost_until = None

        # House mode (F01): cap the auto speed / force boost by the zone's mode.
        mode_data = self.hass.data.get(const.DOMAIN, {}).get(const.DATA_MODE)
        mode = modes.effective_from_published(mode_data, self.entry.entry_id)
        mode_cap = modes.dv_cap(mode, (mode_data or {}).get("caps"))
        mode_boost = modes.is_boost(mode)

        co2_raw = self._num(const.CONF_CO2)
        pm_raw = self._num(const.CONF_PM25)
        # Extractor hood (F35): auto speed from indoor PM (hysteresis in the engine).
        if self.has_hood():
            self.hood_speed_auto = hood_speed(pm_raw, self.hood_speed_auto, cfg)
        a_co2_v2, a_co2_v3, a_pm_v2, a_pm_v3 = self._update_adaptive(
            cfg, co2_raw, pm_raw)
        # Surface the learned thresholds + sample count for observability (so the
        # user can compare them against the fixed ones before trusting adaptive).
        self.adaptive_co2_v2, self.adaptive_co2_v3 = a_co2_v2, a_co2_v3
        self.adaptive_pm_v2, self.adaptive_pm_v3 = a_pm_v2, a_pm_v3
        self.adaptive_samples = min(len(self._co2_hist), len(self._pm_hist))
        dew_r, dp_diff = self._dew(cfg)

        # Weekly schedule (F21): a non-empty profile drives the base speed/on-off
        # (slot 0 = off, 1/2/3 = floor); empty profile -> legacy on/off gate.
        profile = self.entry.options.get(const.CONF_SCHEDULE)
        sched_speed: int | None = None
        if self.schedule_enabled and not schedule.is_empty(profile):
            v = schedule.active_value(profile, now.weekday(),
                                      now.hour * 60 + now.minute)
            sched_speed = int(v) if v is not None else None

        # Shower detection (rise over baseline) + effectiveness gate; also snapshot
        # the effective IAQ thresholds so the diagnostic sensors show value-vs-threshold.
        rh_delta = self._shower_signal(cfg)
        self.shower_gate = cfg.shower_enabled
        self.iaq_snapshot = {
            "co2": co2_raw,
            "co2_v2": a_co2_v2 if a_co2_v2 is not None else cfg.co2_v2,
            "co2_v3": a_co2_v3 if a_co2_v3 is not None else cfg.co2_v3,
            "pm": pm_raw,
            "pm_v2": a_pm_v2 if a_pm_v2 is not None else cfg.pm_v2,
            "pm_v3": a_pm_v3 if a_pm_v3 is not None else cfg.pm_v3,
            "thresholds": "adaptive" if a_co2_v2 is not None else "fixed",
            "shower_rise": self.shower_rise,
            "shower_on": cfg.shower_rh_delta_on,
            "shower_off": cfg.shower_rh_delta_off,
            "shower_bathroom": self.shower_bathroom,
            "shower_effective": self.shower_effective,
            "shower_enabled": cfg.shower_enabled,
            "dp_diff": dp_diff,
            "dry_margin": cfg.dry_margin,
        }

        ins = DvInputs(
            co2_raw=co2_raw,
            pm_raw=pm_raw,
            adaptive_co2_v2=a_co2_v2,
            adaptive_co2_v3=a_co2_v3,
            adaptive_pm_v2=a_pm_v2,
            adaptive_pm_v3=a_pm_v3,
            t_in=self._num(const.CONF_T_IN),
            t_ext=self._num(const.CONF_T_EXT),
            aqi=self._num(const.CONF_AQI),
            heating_season=self._house_changeover() == "heat",
            current_speed=self.current_speed,
            boost_active=boost_active,
            permitida=None,  # computed by the engine (schedule + failsafe gate)
            auto_mode=self.auto_mode,
            sdhb_intent=self.bus_explain["winner"],
            trigger_is_iaq=trigger_is_iaq,
            now_ts=now_ts,
            weekday=now.weekday(),
            minute_of_day=now.hour * 60 + now.minute,
            schedule_speed=sched_speed,
            co2_age_s=self._age_s(const.CONF_CO2),
            pm_age_s=self._age_s(const.CONF_PM25),
            startup_grace_active=grace_active,
            rh_delta=rh_delta,
            dry_mode=self.dry_mode_enabled,
            dry_requested=(self.bus_explain["winner"] == "request_dry"),
            dew_risk=dew_r,
            dp_diff=dp_diff,
            mode_cap=mode_cap,
            mode_boost=mode_boost,
        )
        return decide(cfg, self.state_data, ins)
