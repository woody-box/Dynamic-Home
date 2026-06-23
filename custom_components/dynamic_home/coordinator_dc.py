"""DC coordinator: evaluates the climate (DC) pipeline and publishes to the bus.

DC is the brain: while heating it publishes ``request_solar_gain`` and while
cooling ``request_solar_shield`` to its shutter target, so DS reacts. It also
consumes intents aimed at itself (self-bias) from the same shared hub.
"""

from __future__ import annotations

import logging
import math
from datetime import timedelta

import homeassistant.helpers.issue_registry as ir
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from . import (
    comfort,
    const,
    energy,
    events,
    install,
    modes,
    repairs,
    schedule,
    shared_emitter,
    staging,
    zones,
)
from . import (
    emitters as emitters_mod,
)
from .bus import SdhbHub
from .dc_engine import (
    DcConfig,
    DcDecision,
    DcInputs,
    adaptive_lead_target,
    adjacent_advice,
    dew_point,
    dew_risk,
    ema,
    facade_bias,
    mold_index_step,
    on_rate_cph,
    step_toward,
    sunlit_facades,
    window_anomaly,
)
from .dc_engine import (
    decide as decide_climate,
)
from .options_spec import apply_options

_LOGGER = logging.getLogger(__name__)


class DcCoordinator(repairs.DegradedTracker, DataUpdateCoordinator):
    """Evaluates the DC (climate) pipeline and PUBLISHES intents to the bus.

    DC is the brain: while heating it publishes ``request_solar_gain`` and while
    cooling ``request_solar_shield`` to its shutter target, so DS reacts. It also
    consumes intents aimed at itself (self-bias) from the same shared hub.
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry,
                 hub: SdhbHub) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{const.DOMAIN}_dc",
            update_interval=timedelta(seconds=const.UPDATE_INTERVAL_S),
        )
        self.entry = entry
        self.hub = hub
        self.hvac_mode = "off"          # desired mode, set from the climate entity
        self.override_active = False
        self.override_temp: float | None = None
        self.vacation_enabled = False
        self.schedule_enabled = False   # F21: weekly base-setpoint program
        # F09: short-cycle protection (opt-in) over the shared compressor.
        self.anticycle_enabled = False
        self.anticycle_hold = False     # holding this zone off to protect the compressor
        self.anticycle_reason = "off"
        self._channel_holds: dict[str, bool] = {}   # F09 full: hold per compressor
        # F03: electrical-peak staging (opt-in) over the house heating budget.
        self.peak_enabled = False
        self.peak_hold = False          # holding this zone off to stay under the peak budget
        self.peak_reason = "off"
        # F25: multiple emitters per zone (primary + staged support). Empty list
        # keeps the legacy single-device path. emitter_commands: id -> command dict.
        self._emitters: list[dict] = []
        self._staging: dict[str, staging.StagingState] = {}
        self.emitter_commands: dict[str, dict] = {}
        self.observe_enabled = False    # dry-run: compute but do not act on hw
        self.apply_min_delta = 0.0      # anti-jitter gate read by the climate entity
        self._source = f"dc_{entry.entry_id}"
        self._active_sources: set[str] = set()  # bus slots this DC currently owns
        # Bus-conflict observability (the intent THIS zone consumes as self-bias).
        self.bus_explain: dict = self.hub.explain(self.bus_listen_targets())
        self._prev_winner: str | None = None
        self.dew_point_c: float | None = None   # observability
        self.dew_risk_active = False
        # Energy (F06): cumulative kWh while calling for heat/cool (real or est.).
        self.energy_kwh = 0.0
        self.power_w = 0.0              # F06/REQ-ENE-5: instantaneous power (W)
        self._energy_ts: float | None = None
        # Trend (indoor temp derivative) state.
        self._prev_tint: float | None = None
        self._prev_ts: float | None = None
        self._cph: float = 0.0
        # Adaptive lead (learned). Opt-in via the "Adaptive Lead" switch.
        self.adaptive_enabled = False
        self._module = const.MODULE_CLIMATE
        self.init_degraded(entry)       # degraded / repair-issue tracking (F07)
        # Mold-risk index (F22): accumulated hours, hysteresis latch + alert.
        self.mold_index = 0.0
        self._mold_ts: float | None = None
        self._mold_active = False
        self._mold_issue_id = f"mold_{entry.entry_id}"
        self._mold_source = f"dc_{entry.entry_id}__mold_dry"
        # Adjacent warm-space advisory (F31).
        self.adjacent_advice = "none"
        # Open-window inference (F20): latch + debounce/recovery timers.
        self._window_inferred = False
        self._window_anom_since: float | None = None
        self._window_ok_since: float | None = None
        self._window_armed_ts: float | None = None
        self.learn_rate_ema = 0.0        # learned heating/cooling rate (°C/h)
        self.learn_overshoot_ema = 0.0   # learned overshoot beyond setpoint (°C)
        self.learned_lag_h = 0.0         # learned thermal lag OFF->peak (h)
        self.lead_gain_adaptive = 0.0    # learned anticipation horizon (h)
        self.adapt_ok_count = 0
        self.adapt_abort_count = 0
        # Cycle state machine (ON capture -> OFF settling -> peak).
        self._valve_open = False
        self._on_t0: float | None = None
        self._on_t0_ts: float | None = None
        self._settling = False
        self._off_sp: float | None = None
        self._off_peak: float | None = None
        self._off_peak_ts: float | None = None
        self._off_ts: float | None = None
        self._off_hvac: str | None = None

    # --- adaptive lead learning (port of "Adaptive Lead v2.6.1") ---
    def _real_valve_open(self, cfg: DcConfig, hvac: str) -> bool | None:
        """Real heating/cooling demand (F27), priority c > b > a; None = no source.

        (c) real relay/power state — most reliable, also sees the analog backup
        thermostat; (b) explicit heat/cool helpers; (a) the climate's hvac_action.
        """
        # (c) relay / power: numeric -> power threshold; otherwise on/off.
        if self._hw(const.CONF_DC_VALVE):
            v = self._num(const.CONF_DC_VALVE)
            if v is not None:
                return v > cfg.valve_power_min
            return self._is_on(const.CONF_DC_VALVE)
        # (b) explicit demand helper for the active mode.
        if (self._hw(const.CONF_DC_DEMAND_HEAT)
                or self._hw(const.CONF_DC_DEMAND_COOL)):
            key = (const.CONF_DC_DEMAND_HEAT if hvac == "heat"
                   else const.CONF_DC_DEMAND_COOL)
            return bool(self._hw(key)) and self._is_on(key)
        # (a) hvac_action from the climate entity.
        climate = self._hw(const.CONF_DC_CLIMATE)
        if climate:
            st = self.hass.states.get(climate)
            action = st.attributes.get("hvac_action") if st else None
            if action in ("heating", "cooling"):
                return True
            if action in ("idle", "off"):
                return False
        return None

    def _valve_demand(self, cfg: DcConfig, hvac: str, t_int: float | None,
                      target: float | None) -> bool:
        """Whether the zone is actively calling for heat/cool (our 'valve open').

        Prefers a real demand signal (F27) when configured; otherwise falls back
        to inferring it from indoor temperature vs target (legacy behaviour).
        """
        if hvac not in ("heat", "cool"):
            return False
        real = self._real_valve_open(cfg, hvac)
        if real is not None:
            return real
        if t_int is None or target is None:
            return False
        return t_int < target if hvac == "heat" else t_int > target

    # --- F27 diagnostics ---
    def has_real_demand(self) -> bool:
        """Whether a real demand source (c/b, or hvac_action) is available."""
        if any(self._hw(k) for k in (const.CONF_DC_VALVE,
                                     const.CONF_DC_DEMAND_HEAT,
                                     const.CONF_DC_DEMAND_COOL)):
            return True
        climate = self._hw(const.CONF_DC_CLIMATE)
        if climate:
            st = self.hass.states.get(climate)
            return bool(st and st.attributes.get("hvac_action") is not None)
        return False

    @property
    def real_demand_source(self) -> str | None:
        if self._hw(const.CONF_DC_VALVE):
            return "valve"
        if self._hw(const.CONF_DC_DEMAND_HEAT) or self._hw(const.CONF_DC_DEMAND_COOL):
            return "helper"
        climate = self._hw(const.CONF_DC_CLIMATE)
        if climate:
            st = self.hass.states.get(climate)
            if st and st.attributes.get("hvac_action") is not None:
                return "hvac_action"
        return "inferred"

    @property
    def real_demand_open(self) -> bool | None:
        """Real demand for the current mode (None if no real source configured)."""
        return self._real_valve_open(self._cfg(), self.hvac_mode)

    # --- F26 installation profile (declared catalogue; F09/F03 will consume it) ---
    def has_install(self) -> bool:
        """Whether the installation type has been declared (generator + emitter)."""
        o = self.entry.options
        return bool(o.get(const.CONF_GENERATOR) and o.get(const.CONF_EMISSION))

    @property
    def install_profile(self) -> dict | None:
        """Derived install profile (inertia + compressor/peak/community), or None.

        With a multi-emitter zone (F25) the profile comes from the primary
        emitter's triple; otherwise from the single declared F26 triple.
        """
        o = self.entry.options
        src = emitters_mod.profile_source(
            emitters_mod.normalize(o.get("emitters")))
        if src is not None:
            gen, dist, emission = src
            return install.profile(gen, dist, emission)
        gen = o.get(const.CONF_GENERATOR)
        emission = o.get(const.CONF_EMISSION)
        if not gen or not emission:
            return None
        return install.profile(gen, o.get(const.CONF_DISTRIBUTION), emission)

    # --- F37 community changeover (seasonal water direction) ---
    def _house_changeover(self) -> str | None:
        """The changeover for this zone: its per-zone override, else the house state."""
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

    def _effective_hvac(self) -> str:
        """The direction the zone may actually run this cycle.

        A community (central_shared) zone follows the house changeover: the building
        decides heat vs cool, so the zone's own mode only enables/disables it. Off
        season (changeover ``off``) or zone off -> idle. Non-community zones, or no
        changeover configured (``None``), keep their own mode (back-compat).
        """
        base = self.hvac_mode
        profile = self.install_profile
        co = self._house_changeover()
        if profile and profile.get("community") and co is not None:
            if base == "off":
                return "off"
            return co if co in ("heat", "cool") else "off"
        return base

    def _build_emitter_commands(self, cfg: DcConfig, decision, t_int, now_ts):
        """F25: map the single decision onto each emitter (primary + staged support).

        The primary carries the engine target; each support emitter is gated by its
        staging machine. A zone-level hold (anticycle/peak) or an OFF decision drives
        every emitter OFF, matching today's single-device semantics. Empty emitter
        list -> legacy single-device path (the climate entity handles it).
        """
        self._emitters = emitters_mod.normalize(self.entry.options.get("emitters"))
        if not self._emitters:
            self.emitter_commands = {}
            return
        hvac = self._effective_hvac()       # F37: community zones follow the building
        primary = emitters_mod.primary_for(self._emitters, hvac)
        # F03/F25: OFF/safety and the electrical-peak hold gate ALL emitters; the
        # F09 compressor hold gates only heat-pump emitters (per-emitter, below).
        base_off = (self.peak_hold
                    or decision.action not in ("heat", "cool"))
        zone_compressor = bool(self.install_profile
                               and self.install_profile.get("compressor"))
        cmds: dict[str, dict] = {}
        for em in self._emitters:
            # An emitter is compressor-driven if its own generator is a heat pump;
            # a blank generator falls back to the zone profile (legacy/single-emitter).
            em_compressor = (em["generator"] in install.HEATPUMPS
                             if em["generator"] else zone_compressor)
            # F09 full: hold by this emitter's own compressor channel.
            anti_off = self._channel_holds.get(em["compressor_id"],
                                                self.anticycle_hold)
            held = base_off or (anti_off and em_compressor)
            if em is primary:
                on, reason = not held, "primary"
            else:
                st = self._staging.setdefault(em["id"], staging.StagingState())
                sup_on, reason = staging.step(st, hvac, t_int, decision.target,
                                              now_ts, cfg)
                on = sup_on and not held
            # A bare switch/valve emitter has no self-regulating thermostat, so it
            # follows real demand (t_int vs target / F27) once it is not held.
            if on and not em.get("climate") and em.get("switch"):
                on = not held and self._valve_demand(cfg, hvac, t_int,
                                                     decision.target)
            cmds[em["id"]] = {
                "mode": decision.action if on else "off",
                "target": decision.target if on else None,
                "on": on, "primary": em is primary, "reason": reason,
            }
        self.emitter_commands = cmds

    def _default_channel(self) -> str | None:
        """The shared-duct channel a blank emitter falls back to (its group id)."""
        tree = self.hass.data.get(const.DOMAIN, {}).get(const.DATA_ZONES)
        if not tree:
            return None
        return zones.scope_for_module(tree, self.entry.entry_id).get("group")

    def _shared_emitter_step(self, cfg: DcConfig, decision, t_int, now_ts) -> None:
        """F25 Phase B: reconcile a duct shared across the group's zones.

        Each group-sibling reports its demand to the house-level hub; the owner zone
        drives the physical unit from the single reconciled command, others release
        it (a non-owner never touches the shared unit).
        """
        hub = self.hass.data.get(const.DOMAIN, {}).get("_shared_emit")
        if hub is None or not self._emitters:
            return
        for em in self._emitters:
            if em["scope"] == "zone":
                continue
            chan = em["shared_emitter_id"] or self._default_channel()
            if not chan:
                continue
            hub.report(chan, shared_emitter.ZoneDemand(
                entry_id=self.entry.entry_id, hvac=self.hvac_mode, current=t_int,
                target=decision.target, weight=cfg.zone_demand_weight,
                undershoot_margin=cfg.shared_undershoot_margin,
                owner=em.get("owner", False)))
            if hub.is_owner(chan, self.entry.entry_id):
                cmd = hub.reconcile(chan, self.hvac_mode,
                                    em.get("policy", "weighted"),
                                    em["scope"] == "group_grilles")
                self.emitter_commands[em["id"]] = {
                    "mode": cmd["mode"], "target": cmd["target"],
                    "on": cmd["mode"] != "off", "primary": False,
                    "shared": True, "reason": cmd["reason"]}
            else:
                self.emitter_commands.pop(em["id"], None)   # non-owner: hands off

    def _finalize_cycle(self, cfg: DcConfig) -> None:
        """Settling window elapsed: learn overshoot, lag and step the lead gain."""
        if self._off_peak is None or self._off_sp is None or self._off_ts is None:
            return
        overshoot = self._off_peak - self._off_sp
        self.learn_overshoot_ema = ema(self.learn_overshoot_ema, overshoot,
                                       cfg.adapt_alpha)
        lag_h = (max(0.0, (self._off_peak_ts - self._off_ts) / 3600.0)
                 if self._off_peak_ts else 0.0)
        self.learned_lag_h = ema(self.learned_lag_h, lag_h, cfg.adapt_alpha)
        target_lead = adaptive_lead_target(cfg, self.learn_overshoot_ema,
                                           self.learned_lag_h, self.learn_rate_ema)
        self.lead_gain_adaptive = step_toward(self.lead_gain_adaptive, target_lead,
                                              cfg.adapt_gain_lr)
        self.adapt_ok_count += 1

    def _learn_step(self, cfg: DcConfig, now_ts: float, hvac: str,
                    t_int: float | None, target: float | None,
                    window_open: bool, override: bool) -> None:
        """Drive the ON/OFF cycle state machine for one coordinator tick."""
        valve = self._valve_demand(cfg, hvac, t_int, target)
        rising = valve and not self._valve_open
        falling = (not valve) and self._valve_open

        # Settling window in progress (between valve OFF and the temperature peak).
        if self._settling:
            if rising or hvac != self._off_hvac or window_open or override:
                self.adapt_abort_count += 1   # cycle disturbed -> no learning
                self._settling = False
            else:
                if t_int is not None and self._off_peak is not None:
                    peak = (max(self._off_peak, t_int) if self._off_hvac == "heat"
                            else min(self._off_peak, t_int))
                    if peak != self._off_peak:
                        self._off_peak, self._off_peak_ts = peak, now_ts
                if now_ts - self._off_ts >= cfg.adapt_off_window_h * 3600:
                    self._finalize_cycle(cfg)
                    self._settling = False

        # Edges: capture ON baseline / learn the ON-rate and open a settling window.
        if rising:
            self._on_t0, self._on_t0_ts = t_int, now_ts
        elif falling and hvac in ("heat", "cool"):
            if self._on_t0_ts is not None:
                dt_h = (now_ts - self._on_t0_ts) / 3600.0
                rate = on_rate_cph(self._on_t0, t_int, dt_h, cfg)
                if rate is not None:
                    self.learn_rate_ema = ema(self.learn_rate_ema, rate,
                                              cfg.adapt_alpha)
            self._settling = True
            self._off_sp, self._off_peak = target, t_int
            self._off_peak_ts = self._off_ts = now_ts
            self._off_hvac = hvac

        self._valve_open = valve

    def reset_learning(self) -> None:
        """Wipe all learned adaptive-lead state and the cycle state machine.

        Backs the ``reset_learning`` service: lets a user discard a poisoned
        model (e.g. after swapping a heat pump) without deleting the config
        entry. Also clears the in-flight ON/OFF cycle so a mid-cycle reset does
        not leave a stale settling window that would corrupt the next sample.
        """
        self.learn_rate_ema = 0.0
        self.learn_overshoot_ema = 0.0
        self.learned_lag_h = 0.0
        self.lead_gain_adaptive = 0.0
        self.adapt_ok_count = 0
        self.adapt_abort_count = 0
        self._valve_open = False
        self._on_t0 = None
        self._on_t0_ts = None
        self._settling = False
        self._off_sp = None
        self._off_peak = None
        self._off_peak_ts = None
        self._off_ts = None
        self._off_hvac = None

    def bus_listen_targets(self):
        """Targets this zone consumes from the bus (self-bias intents)."""
        return "dc"

    def _refresh_bus_explain(self, now_ts: float | None) -> None:
        """Recompute the consumed bus intent and fire a conflict event on change."""
        self.bus_explain = self.hub.explain(self.bus_listen_targets(), now_ts)
        winner = self.bus_explain["winner"]
        if winner != self._prev_winner:
            if not (self._prev_winner is None and winner == "none"):
                events.fire_conflict(self.hass, self.entry,
                                     const.MODULE_CLIMATE, self.bus_explain)
            self._prev_winner = winner

    def _anticycle_step(self, cfg: DcConfig, decision, now_ts: float) -> None:
        """F09: gate DC's commanded on/off over the shared compressor aggregate.

        ``desired_on`` = DC commands heat/cool this cycle; ``safety_off`` = DC
        wanted to run but a safety branch (condensation/window/…) forced it off,
        so the guard yields. When the aggregate holds this zone off, the climate
        entity drives the thermostat OFF instead of heat/cool.
        """
        ac = self.hass.data.get(const.DOMAIN, {}).get("_anticycle")
        self._channel_holds = {}
        if ac is None:
            self.anticycle_hold = False
            return
        # F26 gating: short-cycle protection only applies to a compressor under
        # the occupant's control. A communal source (just a valve) or a
        # non-compressor generator (gas/electric) never participates.
        profile = self.install_profile
        gated = profile is not None and not profile.get("compressor")
        if not self.anticycle_enabled or gated:
            ac.clear(self.entry.entry_id)     # not participating in the aggregate
            self.anticycle_hold = False
            self.anticycle_reason = "off"
            return
        desired_on = decision.action in ("heat", "cool")
        safety_off = self.hvac_mode in ("heat", "cool") and decision.action == "off"
        # F09 full: a zone drives one compressor channel per distinct heat-pump
        # emitter (compressor_id); legacy/single-device falls to "default" (one
        # house compressor). Reset first so dropped channels stop being reported.
        ac.clear(self.entry.entry_id)
        ems = emitters_mod.normalize(self.entry.options.get("emitters"))
        if ems:
            channels = {e["compressor_id"] for e in ems
                        if e["generator"] in install.HEATPUMPS}
            p = emitters_mod.primary_for(ems, self._effective_hvac())
            primary_ch = (p["compressor_id"] if p
                          and p["generator"] in install.HEATPUMPS else "default")
        else:
            channels, primary_ch = {"default"}, "default"
        if not channels:                  # multi-emitter zone with no heat-pump emitter
            self.anticycle_hold = False
            self.anticycle_reason = "off"
            return
        reason = "off"
        for ch in channels:
            gated_on, ch_reason = ac.evaluate(
                self.entry.entry_id, desired_on, safety_off, now_ts, cfg, channel=ch)
            self._channel_holds[ch] = desired_on and not gated_on
            if ch == primary_ch:
                reason = ch_reason
        self.anticycle_reason = reason
        self.anticycle_hold = self._channel_holds.get(primary_ch, False)

    def _peak_step(self, cfg: DcConfig, decision, t_int, now_ts: float) -> None:
        """F03: stage electric-heating starts under the house peak budget.

        Only engaged when opted in AND the F26 profile says the load is electrical
        (electric direct or an individual heat pump) and not communal. A zone the
        compressor guard (F09) already holds off does not consume a peak slot.
        """
        ph = self.hass.data.get(const.DOMAIN, {}).get("_peak_dc")
        profile = self.install_profile
        eligible = profile is not None and profile.get("peak")
        if ph is None or not self.peak_enabled or not eligible:
            if ph is not None:
                ph.clear(self.entry.entry_id)
            self.peak_hold = False
            self.peak_reason = "off"
            return
        demand = decision.action in ("heat", "cool") and not self.anticycle_hold
        # F03 comfort bypass: a severe deviation from setpoint skips the peak gate
        # entirely (comfort wins over peak-shaving; safety still wins above).
        dev = staging.deviation(decision.action, t_int, decision.target)
        if demand and cfg.peak_comfort_bypass_c > 0 and dev >= cfg.peak_comfort_bypass_c:
            ph.clear(self.entry.entry_id)
            self.peak_hold = False
            self.peak_reason = "peak_comfort_bypass"
            return
        # F34: a live grid meter (Energy module) gives a watt budget = headroom;
        # it tightens any static cap and never loosens it. No meter -> static watt
        # budget if set, else degrade to an N-zones count (REQ-EPK-1).
        energy = self.hass.data.get(const.DOMAIN, {}).get(const.DATA_ENERGY)
        headroom = energy.get("import_headroom_w") if energy else None
        power_mode = headroom is not None or cfg.peak_max_power_w > 0
        units = ((self._num(const.CONF_POWER_METER) or cfg.est_w_on)
                 if power_mode else 1.0)
        if headroom is not None:
            max_units = (min(headroom, cfg.peak_max_power_w)
                         if cfg.peak_max_power_w > 0 else headroom)
        elif power_mode:
            max_units = cfg.peak_max_power_w
        else:
            max_units = float(cfg.peak_max_zones)
        allowed, self.peak_reason = ph.evaluate(
            self.entry.entry_id, demand=demand, units=units, sustained=True,
            hold_s=0.0, now_ts=now_ts, max_units=max_units,
            stagger_s=cfg.peak_stagger_s, priority=max(dev, 0.0))
        self.peak_hold = demand and not allowed

    def _accumulate_energy(self, cfg: DcConfig, now_ts: float) -> None:
        """Integrate energy (F06): real meter if configured, else est. while ON."""
        if self._energy_ts is not None:
            dt_s = now_ts - self._energy_ts
            power = self._num(const.CONF_POWER_METER)
            if power is None:
                valve = self._real_valve_open(cfg, self.hvac_mode)
                on = valve if valve is not None else self.hvac_mode in ("heat", "cool")
                power = energy.dc_power_w(on, cfg.est_w_on)
            self.energy_kwh = energy.add_kwh(self.energy_kwh, power, dt_s)
            self.power_w = float(power or 0.0)
        self._energy_ts = now_ts

    # --- mold-risk index (F22) ---
    def has_mold(self) -> bool:
        """Whether the mold index can be computed (needs an indoor RH source)."""
        return bool(self._hw(const.CONF_DC_HUMIDITY))

    def _mold_step(self, cfg: DcConfig, rh: float | None, now_ts: float) -> None:
        """Integrate the index, flip the hysteresis latch and arm/disarm actions."""
        if self._mold_ts is not None:
            dt_h = max(0.0, (now_ts - self._mold_ts) / 3600.0)
            self.mold_index = mold_index_step(self.mold_index, rh, dt_h, cfg)
        self._mold_ts = now_ts

        was = self._mold_active
        if self.mold_index >= cfg.mold_on_h:
            self._mold_active = True
        elif self.mold_index < cfg.mold_off_h:
            self._mold_active = False

        if self._mold_active != was:
            events.fire_mold(self.hass, self.entry, const.MODULE_CLIMATE,
                             self._mold_active, self.mold_index)

        if self._mold_active:
            ir.async_create_issue(
                self.hass, const.DOMAIN, self._mold_issue_id,
                is_fixable=False, severity=ir.IssueSeverity.WARNING,
                translation_key=const.ISSUE_MOLD_RISK,
                translation_placeholders={"name": self.entry.title,
                                          "index": str(round(self.mold_index, 1))},
                learn_more_url=const.LEARN_MORE_URL)
            # Drying via the bus (DV applies its own dp_diff gate).
            self.hub.publish(source=self._mold_source, intent="request_dry",
                             target="dv", priority=60, ttl_s=1800, now_ts=now_ts)
            self._drive_dehumidifier(True)
        elif was:
            ir.async_delete_issue(self.hass, const.DOMAIN, self._mold_issue_id)
            self.hub.clear(self._mold_source)
            self._drive_dehumidifier(False)

    # --- adjacent warm-space advisory (F31) ---
    def has_adjacent(self) -> bool:
        """Whether the adjacent-space advisory applies (needs its temp sensor)."""
        return bool(self._hw(const.CONF_DC_ADJ_TEMP))

    def _adjacent_step(self, cfg: DcConfig, t_int: float | None) -> None:
        """Evaluate the advisory and fire an event on each transition."""
        t_adj = self._num(const.CONF_DC_ADJ_TEMP)
        door = (self._is_on(const.CONF_DC_ADJ_DOOR)
                if self._hw(const.CONF_DC_ADJ_DOOR) else None)
        advice = adjacent_advice(self.hvac_mode, t_int, t_adj, door, cfg)
        if advice != self.adjacent_advice:
            self.adjacent_advice = advice
            dt = (t_adj - t_int) if (t_adj is not None and t_int is not None) else 0.0
            events.fire_adjacent(self.hass, self.entry, const.MODULE_CLIMATE,
                                 advice, dt)

    # --- open-window inference (F20) ---
    def has_window_infer(self) -> bool:
        """Whether temperature-based window inference applies (no window sensor)."""
        return not self._hw(const.CONF_DC_WINDOW)

    def _infer_window(self, cfg: DcConfig, hvac: str, t_int: float | None,
                      trend_cph: float, now_ts: float) -> bool:
        """Latch an inferred open window: arm on a sustained anomaly, recover on
        stabilisation or a safety timeout. Active only without a window sensor."""
        if not self.has_window_infer() or t_int is None:
            self._window_anom_since = None
            self._window_ok_since = None
            self._window_armed_ts = None
            if self._window_inferred:
                self._window_inferred = False
            return False

        valve = self._real_valve_open(cfg, hvac)
        valve_open = valve if valve is not None else hvac in ("heat", "cool")
        anom = window_anomaly(hvac, valve_open, trend_cph, cfg)

        if not self._window_inferred:
            self._window_ok_since = None
            if anom:
                if self._window_anom_since is None:
                    self._window_anom_since = now_ts
                elif now_ts - self._window_anom_since >= cfg.window_confirm_min * 60:
                    self._window_inferred = True
                    self._window_armed_ts = now_ts
                    events.fire_window(self.hass, self.entry,
                                       const.MODULE_CLIMATE, True, trend_cph)
            else:
                self._window_anom_since = None
        else:
            self._window_anom_since = None
            timed_out = (self._window_armed_ts is not None
                         and now_ts - self._window_armed_ts
                         >= cfg.window_max_lockout_min * 60)
            if not anom:
                if self._window_ok_since is None:
                    self._window_ok_since = now_ts
                stable = now_ts - self._window_ok_since >= cfg.window_release_min * 60
            else:
                self._window_ok_since = None
                stable = False
            if stable or timed_out:
                self._window_inferred = False
                self._window_armed_ts = None
                self._window_ok_since = None
                events.fire_window(self.hass, self.entry, const.MODULE_CLIMATE,
                                   False, trend_cph)
        return self._window_inferred

    def _drive_dehumidifier(self, on: bool) -> None:
        """Turn a configured dehumidifier on/off (skipped in observe/dry-run)."""
        ent = self._hw(const.CONF_DC_DEHUMIDIFIER)
        if not ent or self.observe_enabled:
            return
        service = "turn_on" if on else "turn_off"
        self.hass.async_create_task(self.hass.services.async_call(
            "homeassistant", service, {"entity_id": ent}, blocking=False))

    def clear_mold(self) -> None:
        """Remove the mold repair issue and bus request (called on unload)."""
        ir.async_delete_issue(self.hass, const.DOMAIN, self._mold_issue_id)
        self.hub.clear(self._mold_source)

    def clear_published(self) -> None:
        """Remove all bus slots owned by this zone (called on unload/reload)."""
        for src in self._active_sources:
            self.hub.clear(src)
        self._active_sources = set()

    def _mode(self) -> str:
        """This zone's effective house mode (F01), or 'home' if modes unset."""
        return modes.effective_from_published(
            self.hass.data.get(const.DOMAIN, {}).get(const.DATA_MODE),
            self.entry.entry_id)

    def _tariff_state(self) -> str | None:
        """Published tariff state from the Energy module (F34), or None."""
        energy = self.hass.data.get(const.DOMAIN, {}).get(const.DATA_ENERGY)
        return energy.get("tariff_state") if energy else None

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

    def indoor_temperature(self) -> float | None:
        """Current indoor temperature of the zone (for the climate entity)."""
        return self._num(const.CONF_DC_T_INT)

    def _cfg(self) -> DcConfig:
        """Build the DC config, overlaying UI options then the comfort preset."""
        cfg = DcConfig()
        apply_options(cfg, self.entry.options, const.MODULE_CLIMATE)
        # F23: comfort↔economy preset (global + per-zone), resolved like F01.
        comfort.apply_dc(cfg, comfort.effective_from_published(
            self.hass.data.get(const.DOMAIN, {}).get(const.DATA_MODE),
            self.entry.entry_id))
        return cfg

    def _scheduled_base(self) -> float | None:
        """F21: absolute base setpoint from the active weekly slot, or None."""
        if not self.schedule_enabled:
            return None
        now = dt_util.now()                         # local time for the program
        val = schedule.active_value(
            self.entry.options.get(const.CONF_SCHEDULE),
            now.weekday(), now.hour * 60 + now.minute)
        return None if val is None else float(val)

    def _sun(self) -> tuple[float | None, float | None]:
        st = self.hass.states.get("sun.sun")
        if st is None:
            return None, None
        return st.attributes.get("azimuth"), st.attributes.get("elevation")

    def _registered_facades(self) -> tuple[dict, dict]:
        """({facade_key: azimuth}, {facade_key: span}) of all shutters."""
        reg = self.hass.data.get(const.DOMAIN, {}).get("_facades", {})
        facades = {v["key"]: v["az"] for v in reg.values()}
        spans = {v["key"]: v.get("span", 180.0) for v in reg.values()}
        return facades, spans

    def _publish(self, desired: dict, now_ts: float | None = None) -> None:
        """Reconcile the bus slots this DC owns with ``desired`` (key->(intent,target))."""
        for stale in self._active_sources - set(desired):
            self.hub.clear(stale)
        for src, (intent, target) in desired.items():
            # TTL so a stale zone's intent expires on its own (matches the YAML).
            self.hub.publish(source=src, intent=intent, target=target,
                             priority=70, ttl_s=1800, now_ts=now_ts)
        self._active_sources = set(desired)

    def _vmc_speed(self) -> int | None:
        """VMC speed 1/2/3 from the configured entity (fan percentage or sensor)."""
        ent = self._hw(const.CONF_DC_VMC)
        if not ent:
            return None
        st = self.hass.states.get(ent)
        if st is None or st.state in ("unknown", "unavailable", "none", ""):
            return None
        if ent.startswith("fan."):
            if st.state != "on":
                return None
            pct = st.attributes.get("percentage")
            if not pct:
                return None
            return min(3, max(1, math.ceil(pct / (100 / 3))))
        try:
            v = int(float(st.state))
            return v if v in (1, 2, 3) else None
        except (TypeError, ValueError):
            return None

    def _update_trend(self, cfg: DcConfig, t_int: float | None,
                      now_ts: float) -> float:
        """EMA-smoothed indoor-temp derivative (°C/h), with a deadband."""
        if t_int is None:
            self._prev_tint, self._prev_ts = None, None
            return self._cph
        if self._prev_tint is not None and self._prev_ts is not None:
            dt_h = (now_ts - self._prev_ts) / 3600.0
            if dt_h > 0:
                raw = (t_int - self._prev_tint) / dt_h
                a = cfg.trend_ema_alpha
                self._cph = a * raw + (1 - a) * self._cph
        self._prev_tint, self._prev_ts = t_int, now_ts
        return 0.0 if abs(self._cph) < cfg.trend_deadband_cph else self._cph

    async def _forecast_temp(self, cfg: DcConfig, hvac: str) -> float | None:
        """Extreme forecast temp in the look-ahead window (max heat / min cool)."""
        ent = self._hw(const.CONF_DC_WEATHER)
        if not ent or hvac not in ("heat", "cool"):
            return None
        try:
            resp = await self.hass.services.async_call(
                "weather", "get_forecasts",
                {"entity_id": ent, "type": "hourly"},
                blocking=True, return_response=True)
        except Exception:  # noqa: BLE001 — weather entity may not support it
            return None
        forecasts = (resp or {}).get(ent, {}).get("forecast", [])
        end = dt_util.utcnow() + timedelta(hours=cfg.forecast_window_h)
        temps = []
        for f in forecasts:
            ts = dt_util.parse_datetime(f.get("datetime", "")) if f.get("datetime") else None
            t = f.get("temperature")
            if ts is not None and t is not None and ts <= end:
                temps.append(float(t))
        if not temps:
            return None
        return max(temps) if hvac == "heat" else min(temps)

    def _facade_openness(self, lit: set) -> float:
        """Mean 0..1 shutter opening of the sunlit facades (0 if none)."""
        reg = self.hass.data.get(const.DOMAIN, {}).get("_facades", {})
        vals = []
        for eid, fac in reg.items():
            if fac["key"] in lit:
                ds = self.hass.data[const.DOMAIN].get(eid)
                if ds is not None and ds.data is not None:
                    vals.append(ds.data.pos / 100.0)
        return sum(vals) / len(vals) if vals else 0.0

    async def _async_update_data(self) -> DcDecision:
        cfg = self._cfg()
        self.apply_min_delta = cfg.apply_min_delta
        sun_az, sun_el = self._sun()
        t_int = self._num(const.CONF_DC_T_INT)
        rh = self._num(const.CONF_DC_HUMIDITY)
        now_ts = dt_util.utcnow().timestamp()
        self._refresh_bus_explain(now_ts)

        self.dew_point_c = dew_point(t_int, rh)
        self.dew_risk_active = dew_risk(cfg, self.hvac_mode, t_int, rh)

        # Energy (F06): integrate before the decision (uses the demand signal).
        self._accumulate_energy(cfg, now_ts)

        # Mold-risk index (F22): integrate, alert and drive drying when armed.
        if self.has_mold():
            self._mold_step(cfg, rh, now_ts)

        # Adjacent warm-space advisory (F31): event-only, no actuation.
        if self.has_adjacent():
            self._adjacent_step(cfg, t_int)

        # Open-window inference (F20): only when no window sensor is configured.
        trend = self._update_trend(cfg, t_int, now_ts)
        self._window_inferred = self._infer_window(cfg, self.hvac_mode, t_int,
                                                   trend, now_ts)

        # Degraded when a core source is missing while a mode is demanded; this
        # pauses learning so stale readings don't poison the EMAs and (if
        # sustained) raises a Repairs issue.
        missing = (["indoor temperature"]
                   if self.hvac_mode in ("heat", "cool") and t_int is None
                   else [])
        self.degraded = self._update_degraded(missing, now_ts)

        facades, spans = self._registered_facades()
        lit = sunlit_facades(sun_az, sun_el, facades, spans)
        facade_b = facade_bias(cfg, self.hvac_mode, self._facade_openness(lit))

        # Feed the learned lead only once the loop is enabled, healthy and has
        # completed at least one cycle; otherwise the engine uses its physical model.
        adaptive_lead = (self.lead_gain_adaptive
                         if (self.adaptive_enabled and self.adapt_ok_count > 0
                             and not self.degraded)
                         else None)

        ins = DcInputs(
            hvac_mode=self._effective_hvac(),
            t_int=t_int,
            t_ext=self._num(const.CONF_DC_T_EXT),
            sun_elevation=sun_el,
            sdhb_intent=self.bus_explain["winner"],
            override_active=self.override_active,
            override_temp=self.override_temp,
            vmc_speed=self._vmc_speed(),
            trend_cph=trend,
            forecast_temp=await self._forecast_temp(cfg, self.hvac_mode),
            wind=self._num(const.CONF_DC_WIND),
            vacation=self.vacation_enabled or modes.is_away(self._mode()),
            window_lockout=self._is_on(const.CONF_DC_WINDOW),
            window_inferred=self._window_inferred,
            dew_risk=self.dew_risk_active,
            extra_bias=facade_b,
            adaptive_lead_h=adaptive_lead,
            scheduled_base=self._scheduled_base(),
            tariff_state=self._tariff_state(),
        )
        decision = decide_climate(cfg, ins)
        self._anticycle_step(cfg, decision, now_ts)
        self._peak_step(cfg, decision, t_int, now_ts)
        self._build_emitter_commands(cfg, decision, t_int, now_ts)
        self._shared_emitter_step(cfg, decision, t_int, now_ts)

        # Learn from real cycles (paused while disabled or degraded). An inferred
        # open window also disturbs the cycle, so it aborts learning like the sensor.
        window_open = self._is_on(const.CONF_DC_WINDOW) or self._window_inferred
        if self.adaptive_enabled and not self.degraded:
            self._learn_step(cfg, now_ts, self.hvac_mode, t_int, decision.target,
                             window_open, self.override_active)
        else:
            self._valve_open = self._valve_demand(cfg, self.hvac_mode, t_int,
                                                  decision.target)
            self._settling = False

        intent = decision.published_intent
        if intent == "none":
            desired = {}
        elif lit:
            # Dynamic: target only the sunlit facades.
            desired = {f"{self._source}__{fk}": (intent, fk) for fk in lit}
        elif facades and sun_el is not None:
            # Facades known but none sunlit -> publish nothing.
            desired = {}
        else:
            # Fallback: broadcast to the configured target.
            target = self.entry.data.get(const.CONF_DC_TARGET) or "ds"
            desired = {self._source: (intent, target)}
        self._publish(desired, now_ts)
        return decision
