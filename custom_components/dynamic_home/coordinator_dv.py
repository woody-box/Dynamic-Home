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

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from . import const
from .bus import SdhbHub
from .dc_engine import dew_point
from .dv_engine import DvConfig, DvDecision, DvInputs, DvState, decide

_LOGGER = logging.getLogger(__name__)


class DvCoordinator(DataUpdateCoordinator[DvDecision]):
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
        self.preset = "auto"            # mirrored from the fan, for the mode sensor
        self._iaq_dirty = False
        self._setup_ts = dt_util.utcnow().timestamp()
        # Telemetry (hours), accumulated between updates; persisted by sensors.
        self.speed_hours = {1: 0.0, 2: 0.0, 3: 0.0}
        self.machine_hours = 0.0
        self.filter_hours = 0.0
        self._accum_ts: float | None = None
        # Startup bootstrap kick (opt-in, hardware quirk).
        self.bootstrap_enabled = False
        # Dry-mode (anti-condensation ventilation) toggle.
        self.dry_mode_enabled = False
        # Weekly schedule (same daily window every day).
        self.schedule_enabled = False
        self.schedule_on = dtime(7, 0)
        self.schedule_off = dtime(23, 0)
        # Adaptive thresholds: rolling history (~7 days @ 1 sample/min).
        self.adaptive_enabled = False
        self._co2_hist: deque[float] = deque(maxlen=10080)
        self._pm_hist: deque[float] = deque(maxlen=10080)

    def _accumulate(self, now_ts: float) -> None:
        """Add elapsed time to the running-hours counters."""
        if self._accum_ts is not None:
            dt_h = (now_ts - self._accum_ts) / 3600.0
            spd = self.current_speed
            if spd in (1, 2, 3) and dt_h > 0:
                self.speed_hours[spd] += dt_h
                self.machine_hours += dt_h
                self.filter_hours += dt_h
        self._accum_ts = now_ts

    def reset_filter_hours(self) -> None:
        self.filter_hours = 0.0

    # --- config helpers ---
    def _hw(self, key: str) -> str | None:
        return self.entry.data.get(key)

    def _cfg(self) -> DvConfig:
        o = self.entry.options
        cfg = DvConfig()
        cfg.co2_v2 = o.get(const.OPT_CO2_V2, cfg.co2_v2)
        cfg.co2_v3 = o.get(const.OPT_CO2_V3, cfg.co2_v3)
        cfg.pm_v2 = o.get(const.OPT_PM_V2, cfg.pm_v2)
        cfg.pm_v3 = o.get(const.OPT_PM_V3, cfg.pm_v3)
        cfg.freecool_enabled = bool(self._hw(const.CONF_T_IN) and
                                    self._hw(const.CONF_T_EXT))
        cfg.hostile_enabled = bool(self._hw(const.CONF_AQI))
        cfg.shower_enabled = bool(self._hw(const.CONF_HUM_BATH) and
                                  self._hw(const.CONF_HUM_EXT))
        cfg.adaptive_enabled = self.adaptive_enabled
        if self.schedule_enabled and self.schedule_on and self.schedule_off:
            on_m = self.schedule_on.hour * 60 + self.schedule_on.minute
            off_m = self.schedule_off.hour * 60 + self.schedule_off.minute
            cfg.schedule_enabled = True
            cfg.schedule = {d: (on_m, off_m) for d in range(7)}
        return cfg

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
    def _rh_delta(self) -> float | None:
        bath = self._num(const.CONF_HUM_BATH)
        ext = self._num(const.CONF_HUM_EXT)
        if bath is None or ext is None:
            return None
        return bath - ext

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
        self._accumulate(now_ts)
        grace_active = (now_ts - self._setup_ts) < cfg.startup_grace_s

        co2_raw = self._num(const.CONF_CO2)
        pm_raw = self._num(const.CONF_PM25)
        a_co2_v2, a_co2_v3, a_pm_v2, a_pm_v3 = self._update_adaptive(
            cfg, co2_raw, pm_raw)
        dew_r, dp_diff = self._dew(cfg)

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
            current_speed=self.current_speed,
            permitida=None,  # computed by the engine (schedule + failsafe gate)
            auto_mode=self.auto_mode,
            sdhb_intent=self.hub.winner("dv", now_ts),
            trigger_is_iaq=trigger_is_iaq,
            now_ts=now_ts,
            weekday=now.weekday(),
            minute_of_day=now.hour * 60 + now.minute,
            co2_age_s=self._age_s(const.CONF_CO2),
            pm_age_s=self._age_s(const.CONF_PM25),
            startup_grace_active=grace_active,
            rh_delta=self._rh_delta(),
            dry_mode=self.dry_mode_enabled,
            dew_risk=dew_r,
            dp_diff=dp_diff,
        )
        return decide(cfg, self.state_data, ins)
