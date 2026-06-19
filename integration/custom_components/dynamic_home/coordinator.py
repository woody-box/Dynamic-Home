"""Coordinator: bridges Home Assistant state into the pure DV engine.

It reads the configured hardware entities, builds :class:`engine.DvInputs`,
runs :func:`engine.decide`, and exposes the resulting logical speed. The fan
entity drives the physical relays from this result.

A minimal in-memory SDHB hub lives here too (see :class:`SdhbHub`): in the full
suite this is the shared coordination bus across DC/DV/DS. For the PoC it simply
holds the winning intent for the ``dv`` target.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from . import const
from .engine import DvConfig, DvState, DvInputs, DvDecision, decide

_LOGGER = logging.getLogger(__name__)


class SdhbHub:
    """Tiny in-memory intent bus (PoC stand-in for the SDHB package).

    Replaces ~2500 lines of input_text "slots" + template arbitration with a
    dict and a resolver. Intents carry a priority; the highest wins per target.
    """

    def __init__(self) -> None:
        self._slots: dict[str, dict] = {}

    def publish(self, source: str, intent: str, target: str,
                priority: int = 50) -> None:
        self._slots[source] = {"intent": intent, "target": target,
                               "priority": priority}

    def winner(self, target: str) -> str:
        candidates = [
            s for s in self._slots.values()
            if s["target"] in (target, "", "dv")
        ]
        if not candidates:
            return "none"
        return max(candidates, key=lambda s: s["priority"])["intent"]


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
        self._iaq_dirty = False
        self._setup_ts = dt_util.utcnow().timestamp()

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
        return cfg

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

    async def _async_update_data(self) -> DvDecision:
        cfg = self._cfg()
        trigger_is_iaq = self._iaq_dirty
        self._iaq_dirty = False

        now = dt_util.now()  # local time for the weekly schedule
        now_ts = now.timestamp()
        grace_active = (now_ts - self._setup_ts) < cfg.startup_grace_s

        ins = DvInputs(
            co2_raw=self._num(const.CONF_CO2),
            pm_raw=self._num(const.CONF_PM25),
            t_in=self._num(const.CONF_T_IN),
            t_ext=self._num(const.CONF_T_EXT),
            aqi=self._num(const.CONF_AQI),
            current_speed=self.current_speed,
            permitida=None,  # computed by the engine (schedule + failsafe gate)
            auto_mode=self.auto_mode,
            sdhb_intent=self.hub.winner("dv"),
            trigger_is_iaq=trigger_is_iaq,
            now_ts=now_ts,
            weekday=now.weekday(),
            minute_of_day=now.hour * 60 + now.minute,
            co2_age_s=self._age_s(const.CONF_CO2),
            pm_age_s=self._age_s(const.CONF_PM25),
            startup_grace_active=grace_active,
            rh_delta=self._rh_delta(),
        )
        return decide(cfg, self.state_data, ins)
