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

from . import const
from .bus import SdhbHub
from .ds_engine import DsConfig, DsDecision, DsInputs, DsState, decide_cover

_LOGGER = logging.getLogger(__name__)


class DsCoordinator(DataUpdateCoordinator):
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
        winner = self.hub.winner(self._listen_targets(), now_ts)
        sun_az, sun_el, sun_above = self._sun()

        ins = DsInputs(
            hvac_mode=self._hvac_mode(),
            t_in=self._num(const.CONF_DS_T_IN),
            t_out=self._num(const.CONF_DS_T_OUT),
            weather_protect_enabled=bool(self._hw(const.CONF_WIND) or
                                         self._hw(const.CONF_RAIN)),
            raining=self._is_on(const.CONF_RAIN),
            wind=self._num(const.CONF_WIND),
            current_pos=self._current_pos(),
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
