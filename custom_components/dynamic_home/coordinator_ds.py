"""DS coordinator: evaluates the shutter (DS) cascade.

Shares the same :class:`SdhbHub` as the other coordinators: when another module
(e.g. DC) publishes ``request_solar_shield`` to the bus, this coordinator
consumes it and clamps the cover.
"""

from __future__ import annotations

import logging
import zlib
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from . import comfort, const, energy, events, modes, repairs, zones
from .bus import SdhbHub
from .ds_engine import (
    PROTECTED,
    DsConfig,
    DsDecision,
    DsInputs,
    DsState,
    alert_active,
    decide_cover,
    solar_impact,
)
from .options_spec import apply_options

_LOGGER = logging.getLogger(__name__)

# Rolling-window energy: keep at most one snapshot per 5 min, over 30 days.
_ENERGY_BUCKET_S = 300.0
_ENERGY_WINDOW_MAX_S = 30 * 86400.0
# Hold the last valid wind reading through a sensor dropout (seconds).
_WIND_TTL_S = 600.0


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
        # Manual override: a hand command holds its position (auto paused) until it
        # expires (``override_hours``) or the user resumes auto.
        self.manual_pos: int | None = None
        self.manual_until = 0.0
        # Weather alert (F17): anticipatory protection hold state.
        self._alert_hold_until = 0.0
        self._last_alert_pos = 0
        # Night-purge latch (F16): open once genuinely cooler outside, close once
        # warmer, hold in between (see _night_iso).
        self._purge_active = False
        # Wind dropout TTL: hold the last valid reading a few minutes so an
        # anemometer going unavailable mid-storm doesn't silently drop the cap.
        self._wind_last: float | None = None
        self._wind_last_ts = 0.0
        # Where the alert comes from, for observability: local / dynamic_weather / none.
        self.alert_source = "none"
        # Weather protection master switch for THIS shutter (rain + alert + wind cap).
        # On by default; turn off for a covered terrace that must never close on weather.
        self.weather_protect = True
        # Treat a move of the underlying cover that DH didn't command (a physical
        # button, a wall switch, another automation) as a manual override. On by
        # default so any hand command pauses the comfort logic, like the integration
        # button does.
        self.track_external = True
        # Seasonal night insulation (F16): opt-in.
        self.night_iso_enabled = False
        # Geometric shading (F15): opt-in real solar-penetration model.
        self.geo_shade_enabled = False
        # Thermal shield: opt-in protection against ambient heat/cold with no
        # direct sun (cool: stay shut if hotter out; heat by day: insulate if
        # colder out, else open for light).
        self.heat_shield_enabled = False
        # Direct-sun shield: opt-in. In cooling, shade against direct sun on the
        # facade even when the outdoor air is cooler (solar gain through glazing
        # still heats the room). Off by default (legacy: shade only when hotter out).
        self.sun_shield_enabled = False
        # Presence simulation (Away): exclude THIS shutter from the simulation when
        # on (set/restored by its switch). Plus the jittered day/night latch state.
        self.sim_excluded = False
        self._sim_day: bool | None = None       # current simulated phase
        self._sim_pending_since = 0.0           # when the sun started differing
        self._sim_seed = zlib.crc32(entry.entry_id.encode())  # per-shutter jitter
        self.sun_impact = 0.0
        self.sun_az: float | None = None        # last sun azimuth/elevation and
        self.sun_el: float | None = None        # whether it's above the horizon,
        self.sun_above = False                  # for the observability sun sensor
        # Electrical-peak staging (F03): opt-in; stagger mass shutter starts.
        self.peak_enabled = False
        self.peak_reason = "off"
        # Energy (F06): cumulative kWh of (marginal) motor movements.
        self.energy_kwh = 0.0
        self.power_w = 0.0             # F06/REQ-ENE-5: ~0 steady (motor moves briefly)
        self._energy_last_pos: int | None = None
        # Rolling-window energy: down-sampled (ts, cumulative_kWh) snapshots to
        # derive the last-24h and last-30d consumption. In-memory (rebuilds after a
        # restart); the cumulative total itself is restored by its own sensor.
        self._energy_hist: list[tuple[float, float]] = []
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

    def _paused(self) -> bool:
        """Master pause for this module (global or per-module, from Zones)."""
        return modes.is_paused(
            self.hass.data.get(const.DOMAIN, {}).get(const.DATA_MODE), "shutter")

    @property
    def observe_effective(self) -> bool:
        """Don't actuate when in observe OR while paused."""
        return self.observe_enabled or self._paused()

    def _peak_params(self, cfg: DsConfig) -> tuple[int, float, float]:
        """(max_zones, max_power_w, stagger_s): the global peak config (Zones)
        wins when set, else this shutter's own values."""
        gp = (self.hass.data.get(const.DOMAIN, {}).get(const.DATA_MODE)
              or {}).get("ds_peak") or {}
        return (gp.get("max_zones", cfg.peak_max_zones),
                gp.get("max_power_w", cfg.peak_max_power_w),
                gp.get("stagger_s", cfg.peak_stagger_s))

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

    def _alert_on(self, key: str, kind: str, cfg: DsConfig) -> bool:
        """Is the alert source for ``key`` firing? Accepts a binary_sensor,
        a numeric sensor (threshold) or a condition/weather sensor (keyword)."""
        ent = self._hw(key)
        if not ent:
            return False
        st = self.hass.states.get(ent)
        return alert_active(st.state if st else None, kind, cfg)

    def _cfg(self) -> DsConfig:
        cfg = DsConfig()
        apply_options(cfg, self.entry.options, const.MODULE_SHUTTER)
        # Facade orientation comes from the config entry (its own selectors).
        az = self.entry.data.get(const.CONF_FACADE_AZIMUTH)
        if az is not None:
            cfg.facade_azimuth_deg = float(az)
        cfg.facade_span_deg = self.facade_span
        # F23: comfort↔economy preset scales the solar aggressiveness by scope.
        comfort.apply_ds(cfg, comfort.effective_from_published(
            self.hass.data.get(const.DOMAIN, {}).get(const.DATA_MODE),
            self.entry.entry_id))
        return cfg

    def arm_manual_override(self, pos: int) -> None:
        """A hand command holds ``pos`` (auto paused) for ``override_hours``.

        Called by the managed cover on a user open/close/set-position. Re-arms the
        timer on every manual command. ``override_hours == 0`` means no expiry
        (hold until the user resumes auto).
        """
        hours = self._cfg().override_hours
        self.manual_pos = max(0, min(100, int(pos)))
        self.manual_until = (dt_util.utcnow().timestamp() + hours * 3600.0
                             if hours > 0 else float("inf"))
        self.hass.async_create_task(self.async_request_refresh())

    def clear_manual_override(self) -> None:
        """Resume automatic control now (the 'back to auto' button)."""
        self.manual_pos = None
        self.manual_until = 0.0
        self.hass.async_create_task(self.async_request_refresh())

    @property
    def override_remaining_min(self) -> float:
        """Minutes left on the manual hold (0 if none, 0 also when no-expiry)."""
        if self.manual_pos is None or self.manual_until in (0.0, float("inf")):
            return 0.0
        left = self.manual_until - dt_util.utcnow().timestamp()
        return round(max(0.0, left) / 60.0, 1)

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

    def _house_changeover(self) -> str | None:
        """F37: the seasonal direction for this shutter — per-zone override else house.

        Mirrors ``coordinator_dc._house_changeover``: reads ``DATA_CHANGEOVER`` and,
        if the changeover is split per zone, the shutter's own zone wins. ``None``
        when no changeover is configured (back-compat: DS keeps its own mode).
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

    def _hvac_mode(self) -> str:
        """The heat/cool season driving the seasonal branches (F16/free-cool/shield).

        A real per-room thermostat (linked ``climate``) wins when it actively calls
        heat/cool; otherwise the shutter follows the **house changeover** (F37), so a
        communal install with no per-shutter thermostat still gets solar protection in
        cooling season and solar gain in heating. No changeover configured -> "off"
        (identical to the legacy behaviour, where the engine idles to ``default``).
        """
        ent = self._hw(const.CONF_CLIMATE)
        if ent:
            st = self.hass.states.get(ent)
            if st and st.state in ("heat", "cool"):
                return st.state
        co = self._house_changeover()
        return co if co in ("heat", "cool") else "off"

    def _climate_attr(self, attr: str) -> float | None:
        """A numeric attribute of the linked ``climate`` (setpoint / current temp)."""
        ent = self._hw(const.CONF_CLIMATE)
        if not ent:
            return None
        st = self.hass.states.get(ent)
        if st is None:
            return None
        val = st.attributes.get(attr)
        try:
            return float(val) if val is not None else None
        except (TypeError, ValueError):
            return None

    @property
    def climate_mode(self) -> str | None:
        """Raw mode of the linked ``climate`` (heat/cool/off/...), or None."""
        ent = self._hw(const.CONF_CLIMATE)
        if not ent:
            return None
        st = self.hass.states.get(ent)
        if st is None or st.state in ("unknown", "unavailable", ""):
            return None
        return st.state

    @property
    def climate_setpoint(self) -> float | None:
        return self._climate_attr("temperature")

    @property
    def climate_temp(self) -> float | None:
        return self._climate_attr("current_temperature")

    def _current_pos(self) -> int | None:
        ent = self._hw(const.CONF_COVER)
        if not ent:
            return None
        st = self.hass.states.get(ent)
        if st is None:
            return None
        pos = st.attributes.get("current_position")
        return int(pos) if pos is not None else None

    def _weather_alert(self, cfg: DsConfig, now_ts: float,
                       raining: bool = False) -> int | None:
        """Anticipatory weather protection (F17): position to protect at, or None.

        Picks the most protective position among the active alert sensors
        (generic / hail / wind). When all clear, keeps protecting for
        ``alert_hold_min`` before releasing.
        """
        # This shutter opted out of weather protection (e.g. a covered terrace).
        if not self.weather_protect:
            self.alert_source = "off"
            return None
        positions: list[int] = []
        if self._alert_on(const.CONF_DS_ALERT, "generic", cfg):
            positions.append(cfg.alert_pct)
        if self._alert_on(const.CONF_DS_ALERT_HAIL, "hail", cfg):
            positions.append(cfg.alert_hail_pct)
        if self._alert_on(const.CONF_DS_ALERT_WIND, "wind", cfg):
            positions.append(cfg.alert_wind_pct)
        # Auto: with no per-shutter alert sensor configured, follow the Dynamic
        # Weather module's alert if one exists (a local alert always overrides).
        local_alert = any(self._hw(k) for k in (
            const.CONF_DS_ALERT, const.CONF_DS_ALERT_HAIL, const.CONF_DS_ALERT_WIND))
        wx = self.hass.data.get(const.DOMAIN, {}).get(const.DATA_WEATHER) or {}
        # Where this shutter's alert comes from (observability, not "faith"):
        self.alert_source = ("local" if local_alert
                             else "dynamic_weather" if const.DATA_WEATHER in
                             self.hass.data.get(const.DOMAIN, {}) else "none")
        if not local_alert:
            if wx.get("alert"):
                positions.append(cfg.alert_pct)
            # Anticipatory protection from the Dynamic Weather probabilities: a high
            # storm chance closes (alert_pct), a high rain chance takes the rain
            # protection position — both before the phenomenon, with the same hold.
            wxv = wx.get("values") or {}
            storm = wxv.get("storm_prob")
            rain = wxv.get("precip_prob")
            if (cfg.storm_prob_alert > 0 and storm is not None
                    and storm >= cfg.storm_prob_alert):
                positions.append(cfg.alert_pct)
            if (cfg.precip_prob_alert > 0 and rain is not None
                    and rain >= cfg.precip_prob_alert):
                positions.append(cfg.rain_close_pct)
        if positions:
            if raining:
                # Simultaneous wind alert (e.g. 50% open) + active rain: the
                # rain-protection position joins the min(), or the alert branch
                # (higher in the cascade) would let the water in half-open.
                positions.append(cfg.rain_close_pct)
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
            self._purge_active = False
            return None
        if hvac == "heat":
            return cfg.night_iso_close_pct
        if hvac == "cool":
            if t_in is None or t_out is None:
                return None
            # Purge with a latch (reuses freecool_delta as the entry band): open
            # when the outside is genuinely cooler, close once it's warmer, hold
            # in between — otherwise ±0.1 °C of sensor noise around t_in cycles
            # the bedroom shutter up and down all night.
            if t_out <= t_in - cfg.freecool_delta:
                self._purge_active = True
            elif t_out > t_in:
                self._purge_active = False
            return (cfg.night_iso_open_pct if self._purge_active
                    else cfg.night_iso_close_pct)
        return None

    def _mode(self) -> str:
        """Effective house/zone mode for this shutter (home/away/sleep/...)."""
        data = self.hass.data.get(const.DOMAIN, {}).get(const.DATA_MODE)
        return modes.effective_from_published(data, self.entry.entry_id)

    def _sim_active(self) -> bool:
        """Presence simulation runs for THIS shutter: global on + Away + included."""
        data = self.hass.data.get(const.DOMAIN, {}).get(const.DATA_MODE)
        if not data or not data.get("presence_sim") or self.sim_excluded:
            return False
        return modes.is_away(self._mode())

    def _sleep_pos(self, cfg: DsConfig) -> int | None:
        """Closed position while the shutter's scope is in Sleep, else None."""
        return cfg.sleep_pct if self._mode() == "sleep" else None

    def _sim_jitter_s(self, cfg: DsConfig, opening: bool, now_ts: float) -> float:
        """Per-day, per-shutter delay (0..jitter) after dawn/dusk — stable within
        the day, varying day to day, staggered across shutters."""
        day = int(now_ts // 86400)
        seed = (day * 2654435761 + self._sim_seed
                + (40503 if opening else 0)) & 0xFFFFFFFF
        return (seed % 1000) / 1000.0 * max(0.0, cfg.sim_jitter_min) * 60.0

    def _sim_step(self, cfg: DsConfig, sun_above: bool,
                  now_ts: float) -> int | None:
        """Occupant-like position while in Away (day open / night close), with a
        jittered delay on the dawn/dusk transitions. ``None`` when inactive."""
        if not self._sim_active():
            self._sim_day = None
            self._sim_pending_since = 0.0
            return None
        raw_day = bool(sun_above)
        if self._sim_day is None:               # first activation: snap, no jitter
            self._sim_day = raw_day
            self._sim_pending_since = 0.0
        elif raw_day == self._sim_day:
            self._sim_pending_since = 0.0
        else:                                   # sun flipped -> hold for the jitter
            if self._sim_pending_since == 0.0:
                self._sim_pending_since = now_ts
            if now_ts - self._sim_pending_since >= self._sim_jitter_s(
                    cfg, raw_day, now_ts):
                self._sim_day = raw_day
                self._sim_pending_since = 0.0
        return cfg.sim_open_pct if self._sim_day else cfg.sim_close_pct

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
        if (prev is not None and prev <= trig < sun_el and not self._dawn_active
                and current_pos is not None):
            # No position feedback -> no ramp: assuming "0" could command a
            # 10-20% step DOWN onto a shutter that was actually open at dawn.
            start = current_pos
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

    def _wind_with_ttl(self, now_ts: float) -> float | None:
        """The wind reading, holding the last valid value through a dropout.

        An anemometer flapping to unavailable in the middle of a gale would
        otherwise silently disable the wind cap (the shutter could reopen to
        100 in a storm). Hold the last reading up to _WIND_TTL_S, then give up.
        """
        wind = self._num(const.CONF_WIND)
        if wind is not None:
            self._wind_last, self._wind_last_ts = wind, now_ts
            return wind
        if (self._hw(const.CONF_WIND) and self._wind_last is not None
                and now_ts - self._wind_last_ts <= _WIND_TTL_S):
            return self._wind_last
        return None

    def _sun(self) -> tuple[float | None, float | None, bool]:
        st = self.hass.states.get("sun.sun")
        if st is None:
            return None, None, False
        az = st.attributes.get("azimuth")
        el = st.attributes.get("elevation")
        above = st.state == "above_horizon"
        return az, el, above

    def _peak_gate(self, cfg: DsConfig, decision: DsDecision,
                   current_pos: int | None, now_ts: float) -> DsDecision:
        """F03: stagger mass shutter starts under the house motor-inrush budget.

        A move is a transient pulse (the travel time); when the budget/stagger
        defers it, hold the current position this cycle and retry next cycle. The
        slew limiter still shapes the move once it is allowed.
        """
        ph = self.hass.data.get(const.DOMAIN, {}).get("_peak_ds")
        # Observe/pause: this shutter never moves, so it must not consume budget
        # or stagger slots that would block shutters that DO move.
        if self.observe_effective:
            if ph is not None:
                ph.clear(self.entry.entry_id)
            self.peak_reason = "off"
            return decision
        # Safety/manual first (the trap incidents): a PROTECTED decision — manual
        # hold, lock, weather alert, rain, wind cap — is never deferred, and never
        # snapped back to a mid-travel snapshot of current_pos by the inrush budget.
        if decision.reason in PROTECTED:
            if ph is not None:
                ph.clear(self.entry.entry_id)
            self.peak_reason = "protected"
            return decision
        if ph is None or not self.peak_enabled or current_pos is None:
            if ph is not None and not self.peak_enabled:
                ph.clear(self.entry.entry_id)
            self.peak_reason = "off"
            return decision
        wants_move = decision.pos != current_pos
        max_zones, max_power_w, stagger_s = self._peak_params(cfg)
        power_mode = max_power_w > 0
        units = cfg.est_w_motor if power_mode else 1.0
        max_units = max_power_w if power_mode else float(max_zones)
        allowed, self.peak_reason = ph.evaluate(
            self.entry.entry_id, demand=wants_move, units=units, sustained=False,
            hold_s=cfg.full_travel_s, now_ts=now_ts, max_units=max_units,
            stagger_s=stagger_s)
        if wants_move and not allowed:
            return DsDecision(pos=current_pos, reason="peak_stagger",
                              details={**decision.details,
                                       "peak_deferred_pos": decision.pos})
        return decision

    async def _async_update_data(self) -> DsDecision:
        cfg = self._cfg()
        cfg.privacy_pos_pct = int(self.privacy_pct)
        now_ts = dt_util.utcnow().timestamp()
        self._refresh_bus_explain(now_ts)
        self.degraded = self._update_degraded(self._missing_required(), now_ts)
        winner = self.bus_explain["winner"]
        sun_az, sun_el, sun_above = self._sun()
        self.sun_az, self.sun_el, self.sun_above = sun_az, sun_el, sun_above
        # Direct sun on this facade (orientation + horizon + overhang), for the
        # "In sun" binary sensor. 0 when the sun isn't reaching the window.
        self.sun_impact = (solar_impact(cfg, sun_az, sun_el, sun_above)
                           if sun_az is not None and sun_el is not None else 0.0)
        current_pos = self._current_pos()
        dawn_pos = self._dawn_step(cfg, sun_el, current_pos, now_ts)
        t_in = self._num(const.CONF_DS_T_IN)
        t_out = self._num(const.CONF_DS_T_OUT)
        hvac = self._hvac_mode()
        night_pos = self._night_iso(cfg, hvac, sun_el, t_in, t_out)
        # Purge = cool night opening because the outside is cooler (vents heat);
        # any other active night case closes to insulate/protect.
        night_purge = (night_pos is not None and hvac == "cool"
                       and self._purge_active)
        raining = (self.weather_protect
                   and self._alert_on(const.CONF_RAIN, "rain", cfg))
        alert_pos = self._weather_alert(cfg, now_ts, raining=raining)
        sim_pos = self._sim_step(cfg, sun_above, now_ts)
        sleep_pos = self._sleep_pos(cfg)
        # Manual hold expiry: drop it once the "tiempo prudencial" elapses.
        if self.manual_pos is not None and now_ts >= self.manual_until:
            self.manual_pos = None
            self.manual_until = 0.0

        wxv = ((self.hass.data.get(const.DOMAIN, {}).get(const.DATA_WEATHER) or {})
               .get("values") or {})
        gust = wxv.get("gust")
        # Wind feeding the cap: the local sensor (with its dropout TTL) first, then
        # Dynamic Weather's regional mean wind when there's no usable local reading
        # (no sensor, or the sensor died past its TTL). So the proportional wind cap
        # works from the weather provider alone, not only from a gust value.
        wind = self._wind_with_ttl(now_ts)
        if wind is None:
            wind = wxv.get("wind")
        ins = DsInputs(
            hvac_mode=hvac,
            t_in=t_in,
            t_out=t_out,
            # Weather protection runs when a local wind/rain sensor is set, or when
            # Dynamic Weather supplies wind or a gust (so it protects even with no
            # local sensor).
            weather_protect_enabled=(self.weather_protect and bool(
                self._hw(const.CONF_WIND) or self._hw(const.CONF_RAIN)
                or gust is not None or wind is not None)),
            raining=raining,
            wind=wind,
            gust=gust,
            current_pos=current_pos,
            dawn_pos=dawn_pos,
            # Night for the free-cool branch (F: open on cool summer nights).
            # Sun data missing -> not night (conservative: the branch stays off,
            # same as before it was wired).
            night=(sun_el is not None and sun_el <= 0),
            night_pos=night_pos,
            night_purge=night_purge,
            sim_pos=sim_pos,
            sleep_pos=sleep_pos,
            alert_pos=alert_pos,
            manual_pos=self.manual_pos,
            geo_shade=self.geo_shade_enabled,
            heat_shield=self.heat_shield_enabled,
            sun_gain_shield=self.sun_shield_enabled,
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
        decision = decide_cover(cfg, self.ds_state, ins)
        decision = self._peak_gate(cfg, decision, current_pos, now_ts)

        # Energy (F06): a shutter move lasts seconds (missed by 60 s sampling), so
        # estimate the marginal motor energy per commanded position change. In
        # observe/pause the motor never runs — no phantom kWh into the dashboard.
        moved = (not self.observe_effective
                 and self._energy_last_pos is not None
                 and decision.pos != self._energy_last_pos)
        if moved:
            self.energy_kwh += energy.ds_move_kwh(
                decision.pos - self._energy_last_pos,
                cfg.est_w_motor, cfg.full_travel_s)
        self._energy_last_pos = decision.pos
        # Instantaneous power: a real meter if configured, else the motor draw on
        # the tick it moves (0 while idle — the honest steady state for a shutter).
        meter = self._num(const.CONF_POWER_METER)
        self.power_w = (meter if meter is not None
                        else (cfg.est_w_motor if moved else 0.0))
        self._record_energy(now_ts)
        # Poke the house-wide count sensors (on the "Común" entry) so they re-arm
        # their cover tracking and refresh — no idle timer of their own.
        async_dispatcher_send(self.hass, const.SIGNAL_DS_COVERS)
        return decision

    def _record_energy(self, now_ts: float) -> None:
        """Snapshot the cumulative kWh once per bucket for the rolling windows.

        Append-only (the bucket-start value is the baseline a later window reads
        against); the live total is kept separately, so within a bucket the
        baseline is preserved. Prunes snapshots past the longest window.
        """
        hist = self._energy_hist
        if not hist or now_ts - hist[-1][0] >= _ENERGY_BUCKET_S:
            hist.append((now_ts, self.energy_kwh))
        cutoff = now_ts - _ENERGY_WINDOW_MAX_S - _ENERGY_BUCKET_S
        while len(hist) > 1 and hist[0][0] < cutoff:
            hist.pop(0)

    def energy_window_kwh(self, window_s: float) -> float:
        """Energy consumed in the last ``window_s`` (rolling)."""
        now_ts = dt_util.utcnow().timestamp()
        return energy.window_kwh(self._energy_hist, self.energy_kwh,
                                 now_ts, window_s)
