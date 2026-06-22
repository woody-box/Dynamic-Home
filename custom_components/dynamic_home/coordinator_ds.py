"""DS coordinator: evaluates the shutter (DS) cascade.

Shares the same :class:`SdhbHub` as the other coordinators: when another module
(e.g. DC) publishes ``request_solar_shield`` to the bus, this coordinator
consumes it and clamps the cover.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from . import const, events, repairs
from .bus import SdhbHub
from .ds_engine import DsConfig, DsDecision, DsInputs, DsState, decide_cover
from .options_spec import apply_options

_LOGGER = logging.getLogger(__name__)


class DsCoordinator(repairs.DegradedTracker, DataUpdateCoordinator):
    """Evaluates the DS (shutter) cascade and tracks the source entities.

    Shares the same :class:`SdhbHub` as the VMC coordinators: when another
    module (e.g. DC) publishes ``request_solar_shield`` to the bus, this
    coordinator consumes it and clamps the cover.
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry,
                 hub: SdhbHub) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{const.DOMAIN}_ds",
            update_interval=timedelta(seconds=const.UPDATE_INTERVAL_S),
        )
        self.entry = entry
        self.hub = hub
        self.ds_state = DsState()
        self.observe_enabled = False    # dry-run: compute but do not act on hw
        # UI-controlled state (set by the shutter's switch/number entities).
        self.privacy_enabled = False
        self.privacy_pct = 40
        self.lock_enabled = False
        self.lock_pct = 50
        # Weather alert (F17): anticipatory protection hold state.
        self._alert_hold_until = 0.0
        self._last_alert_pos = 0
        # Seasonal night insulation (F16): opt-in.
        self.night_iso_enabled = False
        # Gradual sunrise (F19): opt-in ramp state.
        self.dawn_enabled = False
        self._dawn_active = False
        self._dawn_start_ts: float | None = None
        self._dawn_start_pos = 0
        self._prev_sun_el: float | None = None
        # Bus-conflict observability.
        self.bus_explain: dict = self.hub.explain(self.bus_listen_targets())
        self._prev_winner: str | None = None
        # Degraded / repair-issue tracking for the required cover (F07).
        self._module = const.MODULE_SHUTTER
        self.init_degraded(entry)

    def bus_listen_targets(self) -> set[str]:
        """Targets this shutter consumes: broadcast ``ds`` plus its facade."""
        return self._listen_targets()

    def _refresh_bus_explain(self, now_ts: float | None) -> None:
        """Recompute the consumed bus intent and fire a conflict event on change."""
        self.bus_explain = self.hub.explain(self.bus_listen_targets(), now_ts)
        winner = self.bus_explain["winner"]
        if winner != self._prev_winner:
            if not (self._prev_winner is None and winner == "none"):
                events.fire_conflict(self.hass, self.entry,
                                     const.MODULE_SHUTTER, self.bus_explain)
            self._prev_winner = winner

    def _hw(self, key: str) -> str | None:
        return self.entry.data.get(key)

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

    def _is_on(self, key: str) -> bool:
        ent = self._hw(key)
        return bool(ent) and self.hass.states.is_state(ent, "on")

    def _cfg(self) -> DsConfig:
        cfg = DsConfig()
        apply_options(cfg, self.entry.options, const.MODULE_SHUTTER)
        # Facade orientation comes from the config entry (its own selectors).
        az = self.entry.data.get(const.CONF_FACADE_AZIMUTH)
        if az is not None:
            cfg.facade_azimuth_deg = float(az)
        cfg.facade_span_deg = self.facade_span
        return cfg

    @property
    def facade_key(self) -> str:
        """Bus target for this shutter's facade, e.g. ``ds_f180`` (3-digit azimuth)."""
        az = int(round(self.entry.data.get(const.CONF_FACADE_AZIMUTH, 0))) % 360
        return f"ds_f{az:03d}"

    @property
    def facade_span(self) -> float:
        """Acceptance angle of this facade (degrees)."""
        return float(self.entry.data.get(const.CONF_FACADE_SPAN, 180.0))

    def _listen_targets(self) -> set[str]:
        """Targets this shutter consumes: broadcast ``ds`` plus its facade."""
        return {"ds", self.facade_key}

    def _hvac_mode(self) -> str:
        ent = self._hw(const.CONF_CLIMATE)
        if not ent:
            return "off"
        st = self.hass.states.get(ent)
        return st.state if st else "off"

    def _current_pos(self) -> int | None:
        ent = self._hw(const.CONF_COVER)
        if not ent:
            return None
        st = self.hass.states.get(ent)
        if st is None:
            return None
        pos = st.attributes.get("current_position")
        return int(pos) if pos is not None else None

    def _weather_alert(self, cfg: DsConfig, now_ts: float) -> int | None:
        """Anticipatory weather protection (F17): position to protect at, or None.

        Picks the most protective position among the active alert sensors
        (generic / hail / wind). When all clear, keeps protecting for
        ``alert_hold_min`` before releasing.
        """
        positions: list[int] = []
        if self._is_on(const.CONF_DS_ALERT):
            positions.append(cfg.alert_pct)
        if self._is_on(const.CONF_DS_ALERT_HAIL):
            positions.append(cfg.alert_hail_pct)
        if self._is_on(const.CONF_DS_ALERT_WIND):
            positions.append(cfg.alert_wind_pct)
        if positions:
            self._last_alert_pos = min(positions)        # most protective wins
            self._alert_hold_until = now_ts + cfg.alert_hold_min * 60.0
            return self._last_alert_pos
        if now_ts < self._alert_hold_until:
            return self._last_alert_pos                  # hold after it clears
        return None

    def _night_iso(self, cfg: DsConfig, hvac: str, sun_el: float | None,
                   t_in: float | None, t_out: float | None) -> int | None:
        """Seasonal night insulation (F16): position at night, or None.

        Night = sun below the horizon. ``heat`` closes to insulate; ``cool``
        opens to purge the thermal mass when the outside is cooler, else closes
        to protect it. Disabled, daytime or unknown sun -> None (cascade decides).
        """
        if not self.night_iso_enabled or sun_el is None or sun_el > 0:
            return None
        if hvac == "heat":
            return cfg.night_iso_close_pct
        if hvac == "cool":
            if t_in is None or t_out is None:
                return None
            return (cfg.night_iso_open_pct if t_out <= t_in
                    else cfg.night_iso_close_pct)
        return None

    def _dawn_step(self, cfg: DsConfig, sun_el: float | None,
                   current_pos: int | None, now_ts: float) -> int | None:
        """Gradual sunrise (F19): stepped opening target, or None when inactive.

        Starts when the sun crosses ``dawn_trigger_elevation`` upward and the
        shutter isn't already (near) open; then climbs ``dawn_step_pct`` every
        ``dawn_step_min`` up to ``dawn_target_pct``. Only ever raises the
        position (never closes), so it doesn't fight free-cooling or the user.
        """
        prev = self._prev_sun_el
        self._prev_sun_el = sun_el
        if not self.dawn_enabled or sun_el is None:
            self._dawn_active = False
            return None
        trig = cfg.dawn_trigger_elevation
        if (prev is not None and prev <= trig < sun_el and not self._dawn_active):
            start = current_pos if current_pos is not None else 0
            if start < cfg.dawn_target_pct:               # skip if already open
                self._dawn_active = True
                self._dawn_start_ts = now_ts
                self._dawn_start_pos = start
        if not self._dawn_active:
            return None
        if current_pos is not None and current_pos >= cfg.dawn_target_pct:
            self._dawn_active = False                       # opened by other means
            return None
        steps = int((now_ts - self._dawn_start_ts) / (cfg.dawn_step_min * 60.0)) + 1
        target = self._dawn_start_pos + steps * cfg.dawn_step_pct
        if target >= cfg.dawn_target_pct:                  # ramp complete
            self._dawn_active = False
            return None
        if current_pos is not None:                        # rising floor only
            target = max(target, current_pos)
        return int(target)

    def _sun(self) -> tuple[float | None, float | None, bool]:
        st = self.hass.states.get("sun.sun")
        if st is None:
            return None, None, False
        az = st.attributes.get("azimuth")
        el = st.attributes.get("elevation")
        above = st.state == "above_horizon"
        return az, el, above

    async def _async_update_data(self) -> DsDecision:
        cfg = self._cfg()
        cfg.privacy_pos_pct = int(self.privacy_pct)
        now_ts = dt_util.utcnow().timestamp()
        self._refresh_bus_explain(now_ts)
        self.degraded = self._update_degraded(self._missing_required(), now_ts)
        winner = self.bus_explain["winner"]
        sun_az, sun_el, sun_above = self._sun()
        current_pos = self._current_pos()
        dawn_pos = self._dawn_step(cfg, sun_el, current_pos, now_ts)
        t_in = self._num(const.CONF_DS_T_IN)
        t_out = self._num(const.CONF_DS_T_OUT)
        night_pos = self._night_iso(cfg, self._hvac_mode(), sun_el, t_in, t_out)
        alert_pos = self._weather_alert(cfg, now_ts)

        ins = DsInputs(
            hvac_mode=self._hvac_mode(),
            t_in=t_in,
            t_out=t_out,
            weather_protect_enabled=bool(self._hw(const.CONF_WIND) or
                                         self._hw(const.CONF_RAIN)),
            raining=self._is_on(const.CONF_RAIN),
            wind=self._num(const.CONF_WIND),
            current_pos=current_pos,
            dawn_pos=dawn_pos,
            night_pos=night_pos,
            alert_pos=alert_pos,
            privacy_active=self.privacy_enabled,
            override_mode="lock" if self.lock_enabled else "none",
            override_pos=int(self.lock_pct),
            sdhb_allow_override=winner not in ("none", "unknown", ""),
            sdhb_request_solar_shield=winner == "request_solar_shield",
            sdhb_request_quiet=winner == "request_quiet",
            sun_azimuth=sun_az,
            sun_elevation=sun_el,
            sun_effective=sun_above,
        )
        return decide_cover(cfg, self.ds_state, ins)
