"""Zones coordinator (F24 + F32): parses the tree, publishes modes and presence.

The tree is config-time (it only changes when the user edits the "Zones" entry's
options). Presence (F32) also lives here: per-zone source entities are fused into
Occupied/Empty and the house into occupied/away/sleeping, published to
``hass.data[DOMAIN][DATA_PRESENCE]`` and — when auto-drive is on — folded into the
F01 house mode. When presence is configured the coordinator polls (for per-source
timeouts) and also reacts to source state changes via listeners.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from . import changeover, comfort, const, events, modes, presence, zones

_LOGGER = logging.getLogger(__name__)
_SOURCE_KINDS = (presence.PIR, presence.MMWAVE, presence.DOOR)


class ZonesCoordinator(DataUpdateCoordinator):
    """Holds the zone/group hierarchy + house modes + presence, and publishes them."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        # Poll only when presence or a changeover sensor is configured (for
        # per-source timeouts / water-temp tracking); otherwise config-time only.
        # A per-zone sleep schedule also needs the tick to catch its edges.
        tree = zones.normalize(entry.options.get(const.CONF_ZONES_TREE))
        scheduled = any("sleep_start" in z for z in tree["zones"].values())
        configured = bool(entry.options.get(const.CONF_PRESENCE_SOURCES)
                          or entry.options.get(const.CONF_PRESENCE_PHONES)
                          or entry.options.get(const.CONF_CHANGEOVER_SENSOR)
                          or scheduled)
        super().__init__(
            hass, _LOGGER, name=f"{const.DOMAIN}_zones",
            update_interval=(timedelta(seconds=const.UPDATE_INTERVAL_S)
                             if configured else None))
        self.entry = entry
        # F01: house mode + per-zone overrides (set/restored by the select entities).
        self.house_mode = "home"
        self.zone_modes: dict[str, str] = {}
        # Per-zone sleep schedule: inside-the-window flag per zone this tick and
        # last tick (None until the first reading, so a restart is not an edge).
        self.schedule_in: dict[str, bool] = {}
        self._schedule_prev: dict[str, bool] = {}
        # F23: comfort↔economy preset (global + per-zone overrides), same selects.
        self.comfort_global = "balanced"
        self.zone_comfort: dict[str, str] = {}
        # Presence simulation (anti-burglary): in Away, shutters mimic an occupant
        # (day open / night close, jittered). Set/restored by the switch; off by default.
        self.presence_sim = False
        # Master pause (global + per-module). Paused = the module stops actuating
        # AND stops influencing the bus. Set/restored by the switches; off by default.
        self.pause_all = False
        self.pause_climate = False
        self.pause_vmc = False
        self.pause_shutter = False
        # F32: presence fusion state.
        self.presence_zones: dict[str, presence.ZonePresenceState] = {}
        self.presence_occupied: dict[str, bool] = {}
        self.presence_reasons: dict[str, str] = {}
        self.house_presence = "occupied"
        self._auto_driven_mode: str | None = None   # last mode auto-drive set
        # F37: community changeover (seasonal water direction).
        self.changeover_manual = "auto"     # set/restored by the house select
        self.changeover: str | None = None  # resolved heat/cool/off/None
        self.changeover_zones: dict[str, str] = {}   # per-zone manual overrides

    @property
    def tree(self) -> dict:
        return zones.normalize(self.entry.options.get(const.CONF_ZONES_TREE))

    @property
    def mode_caps(self) -> dict:
        caps = dict(modes.DEFAULT_CAPS)
        caps.update(self.entry.options.get(const.CONF_MODE_CAPS) or {})
        return caps

    def effective_for(self, entry_id: str) -> str:
        """The mode in force for a module entry (zone override ?? house)."""
        return modes.effective_mode_for_entry(
            self.tree, self.house_mode, self.zone_modes, entry_id)

    def effective_comfort_for(self, entry_id: str) -> str:
        """The comfort level in force for a module entry (F23)."""
        return comfort.effective_level_for_entry(
            self.tree, self.comfort_global, self.zone_comfort, entry_id)

    def _schedule_tick(self, minute_of_day: int) -> None:
        """Advance every zone's sleep schedule and publish the result.

        A window edge hands a home/sleep manual pick back to ``auto`` (the
        schedule governs again); the select entities are refreshed so the UI
        shows it. Zones without a schedule are untouched.
        """
        before = self._published_zone_modes()
        for zid, z in self.tree["zones"].items():
            if "sleep_start" not in z:
                self.schedule_in.pop(zid, None)
                self._schedule_prev.pop(zid, None)
                continue
            in_now = modes.in_window(minute_of_day, z["sleep_start"], z["sleep_end"])
            manual = self.zone_modes.get(zid, modes.AUTO)
            new_manual, _ = modes.schedule_step(
                manual, in_now, self._schedule_prev.get(zid))
            if new_manual != manual:
                self.zone_modes[zid] = new_manual
            self.schedule_in[zid] = in_now
            self._schedule_prev[zid] = in_now
        # A window edge re-evaluates the modules right away (not on their tick).
        self.publish_modes(notify=self._published_zone_modes() != before)
        self.async_update_listeners()

    def _published_zone_modes(self) -> dict[str, str]:
        """Zone modes as consumers see them: the manual pick, or the schedule's
        ``sleep`` while an ``auto`` zone is inside its window."""
        out = dict(self.zone_modes)
        for zid, in_now in self.schedule_in.items():
            out[zid] = modes.schedule_step(
                self.zone_modes.get(zid, modes.AUTO), in_now, None)[1]
        return out

    def publish_modes(self, notify: bool = True) -> None:
        """Publish the resolved modes + comfort for consumers, and nudge modules."""
        data = self.hass.data.setdefault(const.DOMAIN, {})
        published = self._published_zone_modes()
        data[const.DATA_MODE] = {"house": self.house_mode,
                                 "zones": published,
                                 "caps": self.mode_caps, "tree": self.tree,
                                 "comfort": self.comfort_global,
                                 "zone_comfort": dict(self.zone_comfort),
                                 "presence_sim": self.presence_sim,
                                 "pause": {"all": self.pause_all,
                                           "climate": self.pause_climate,
                                           "vmc": self.pause_vmc,
                                           "shutter": self.pause_shutter},
                                 "ds_peak": self.entry.options.get(
                                     const.CONF_DS_PEAK)}
        events.fire_mode_changed(self.hass, self.entry, self.house_mode,
                                 self.zone_modes)
        if notify:                          # re-evaluate every module right away
            for key, co in list(data.items()):
                if not key.startswith("_") and co is not self \
                        and hasattr(co, "async_request_refresh"):
                    self.hass.async_create_task(co.async_request_refresh())

    # --- F32 presence ---
    def presence_cfg(self) -> presence.PresenceConfig:
        cfg = presence.PresenceConfig()
        for k, v in (self.entry.options.get(const.CONF_PRESENCE_TUNE) or {}).items():
            if hasattr(cfg, k):
                setattr(cfg, k, type(getattr(cfg, k))(v))
        return cfg

    def _is_on(self, eid: str) -> bool:
        st = self.hass.states.get(eid)
        return bool(st and st.state == "on")

    def _tracker_home(self, eid: str) -> bool | None:
        """Whether this tracker says "home" — or ``None`` when it has no signal.

        A phone that lost connectivity (unavailable/unknown/missing) is "no
        data", never "out of the house": counting it as away flipped the whole
        house to Away at 3 a.m. with the family asleep inside.
        """
        st = self.hass.states.get(eid)
        if st is None or st.state in ("unavailable", "unknown"):
            return None
        return st.state == "home"

    def _num(self, eid: str | None) -> float | None:
        if not eid:
            return None
        st = self.hass.states.get(eid)
        try:
            return float(st.state) if st else None
        except (TypeError, ValueError):
            return None

    def _all_source_eids(self) -> list[str]:
        out: list[str] = []
        for zsrc in (self.entry.options.get(const.CONF_PRESENCE_SOURCES) or {}).values():
            for kind in _SOURCE_KINDS:
                out += zsrc.get(kind, [])
        out += self.entry.options.get(const.CONF_PRESENCE_PHONES) or []
        sensor = self.entry.options.get(const.CONF_CHANGEOVER_SENSOR)
        if sensor:                                     # F37 supply-water sensor
            out.append(sensor)
        return out

    def async_setup_presence_listeners(self) -> None:
        """React to source state changes (responsiveness on top of polling)."""
        sources = self._all_source_eids()
        if sources:
            self.entry.async_on_unload(
                async_track_state_change_event(
                    self.hass, sources, self._on_presence_change))

    @callback
    def _on_presence_change(self, _event) -> None:
        self.hass.async_create_task(self.async_request_refresh())

    def _recompute_presence(self, now_ts: float) -> None:
        sources = self.entry.options.get(const.CONF_PRESENCE_SOURCES) or {}
        cfg = self.presence_cfg()
        occ: dict[str, bool] = {}
        for zid in self.tree["zones"]:
            st = self.presence_zones.setdefault(zid, presence.ZonePresenceState())
            zsrc = sources.get(zid, {})
            for kind in _SOURCE_KINDS:
                if any(self._is_on(eid) for eid in zsrc.get(kind, [])):
                    presence.note_source(st, kind, True, now_ts)
            occ[zid], self.presence_reasons[zid] = presence.zone_occupied(
                st, cfg, now_ts)
        phones = self.entry.options.get(const.CONF_PRESENCE_PHONES) or []
        # Only trackers with a real signal vote; with every phone silent there is
        # no phone evidence, so don't let "not phone_home" force the house Away.
        votes = [v for v in (self._tracker_home(e) for e in phones) if v is not None]
        phone_home = (not votes) or any(votes)
        states = list(self.presence_zones.values())
        now = dt_util.now()
        self.house_presence = presence.house_state(
            occ, phone_home, presence.door_recent(states, cfg, now_ts),
            now.hour * 60 + now.minute,
            presence.motion_recent(states, cfg, now_ts), cfg,
            prev=self.house_presence, phone_present=any(votes))
        self.presence_occupied = occ

    def publish_presence(self, notify: bool = True) -> None:
        data = self.hass.data.setdefault(const.DOMAIN, {})
        blob = {"house": self.house_presence,
                "zones": dict(self.presence_occupied),
                "reasons": dict(self.presence_reasons)}
        changed = data.get(const.DATA_PRESENCE) != blob
        data[const.DATA_PRESENCE] = blob
        if changed:                          # transitions only (const.py contract)
            events.fire_presence_changed(self.hass, self.entry,
                                         self.house_presence,
                                         self.presence_occupied)
        # Auto-drive the house mode along the home/away/sleep axis only — never
        # stomp a manual selection (manual > auto, RNF-3): only drive on a real
        # presence TRANSITION, or while the current mode is still the one this
        # auto-drive set last time.
        if self.entry.options.get(const.CONF_PRESENCE_AUTO):
            target = presence.STATE_TO_MODE.get(self.house_presence)
            manual_pick = (self.house_mode != self._auto_driven_mode
                           and self._auto_driven_mode is not None)
            if (target and target != self.house_mode
                    and self.house_mode in ("home", "away", "sleep")
                    and (changed or not manual_pick)):
                self.house_mode = target
                self._auto_driven_mode = target
                self.publish_modes(notify=notify)

    # --- F37 community changeover ---
    def changeover_cfg(self) -> changeover.ChangeoverConfig:
        cfg = changeover.ChangeoverConfig()
        for k, v in (self.entry.options.get(const.CONF_CHANGEOVER_TUNE) or {}).items():
            if hasattr(cfg, k):
                setattr(cfg, k, type(getattr(cfg, k))(v))
        return cfg

    def _changeover_configured(self) -> bool:
        return bool(self.entry.options.get(const.CONF_CHANGEOVER_SENSOR)
                    or self.changeover_manual != "auto"
                    or any(v != "auto" for v in self.changeover_zones.values()))

    def _recompute_changeover(self) -> None:
        water = self._num(self.entry.options.get(const.CONF_CHANGEOVER_SENSOR))
        # prev = self.changeover gives the hysteresis its memory across cycles.
        self.changeover = changeover.resolve(
            self.changeover_manual, water, self.changeover_cfg(),
            prev=self.changeover)

    def publish_changeover(self, notify: bool = True) -> None:
        self._recompute_changeover()
        data = self.hass.data.setdefault(const.DOMAIN, {})
        # Per-zone overrides: only zones forcing a direction (non-auto) are listed;
        # the rest inherit the house state.
        zmap = {zid: ov for zid, ov in self.changeover_zones.items()
                if ov in ("heat", "cool", "off")}
        data[const.DATA_CHANGEOVER] = {
            "state": self.changeover, "manual": self.changeover_manual,
            "zones": zmap,
            "water_temp": self._num(
                self.entry.options.get(const.CONF_CHANGEOVER_SENSOR))}
        if self.changeover != getattr(self, "_prev_changeover", object()):
            self._prev_changeover = self.changeover
            events.fire_changeover_changed(self.hass, self.entry, self.changeover)
        self.async_update_listeners()
        if notify:                          # community zones must re-evaluate
            for key, co in list(data.items()):
                if not key.startswith("_") and co is not self \
                        and hasattr(co, "async_request_refresh"):
                    self.hass.async_create_task(co.async_request_refresh())

    async def _async_update_data(self) -> dict:
        tree = self.tree
        self.hass.data.setdefault(const.DOMAIN, {})[const.DATA_ZONES] = tree
        now = dt_util.now()                         # local time for the schedules
        self._schedule_tick(now.hour * 60 + now.minute)
        if (self.entry.options.get(const.CONF_PRESENCE_SOURCES)
                or self.entry.options.get(const.CONF_PRESENCE_PHONES)):
            self._recompute_presence(dt_util.utcnow().timestamp())
            self.publish_presence(notify=False)
        if self._changeover_configured():
            self.publish_changeover(notify=False)
        else:
            # De-configured mid-life: drop the blob, or community DC zones (and
            # the DV free-cool advisory) keep following a ghost changeover.
            self.hass.data.get(const.DOMAIN, {}).pop(const.DATA_CHANGEOVER, None)
        return tree
