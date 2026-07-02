"""Energy coordinator (F34): publishes the house energy context to hass.data.

Reads the user's own entities (grid import, price, optional PV/consumption), runs the
pure :mod:`energy_engine`, and publishes a ``DATA_ENERGY`` blob (import headroom, tariff
state, scarcity, optional PV surplus) that other modules read live. It **does not
command** anyone; consumers decide and safety wins (RNF-3/4). Read-only, agnostic
(RNF-6) and degrades to whatever is available (RNF-7).
"""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from . import const, energy_engine, events
from .energy_engine import EnergyConfig
from .options_spec import apply_options

_LOGGER = logging.getLogger(__name__)
_UNAVAILABLE = ("unknown", "unavailable", "none", "")
_INPUTS = (const.CONF_ENERGY_GRID, const.CONF_ENERGY_PRICE,
           const.CONF_ENERGY_TOTAL, const.CONF_ENERGY_PV)


class EnergyCoordinator(DataUpdateCoordinator):
    """Resolves and publishes the house energy context."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass, _LOGGER, name=f"{const.DOMAIN}_energy",
            update_interval=timedelta(seconds=const.UPDATE_INTERVAL_S))
        self.entry = entry
        self._module = const.MODULE_ENERGY   # import_options routing
        self.context: dict = {}
        self.house_kwh: float = 0.0          # F34 §8.2: aggregated house energy
        self.house_cost: float = 0.0         # gross cost (€), accumulated
        self.house_power_w: float = 0.0      # F06/REQ-ENE-5: instantaneous total (W)
        self._contrib_prev: dict[str, float] = {}   # entry_id -> last kwh seen

    def has_pv(self) -> bool:
        return bool(self._hw(const.CONF_ENERGY_PV))

    def _cfg(self) -> EnergyConfig:
        cfg = EnergyConfig()
        contracted = self._num(const.CONF_ENERGY_CONTRACTED)
        if contracted is not None:                  # entry-data override (config flow)
            cfg.contracted_w = contracted
        apply_options(cfg, self.entry.options, const.MODULE_ENERGY)
        return cfg

    def _hw(self, key: str) -> str | None:
        return self.entry.data.get(key)

    def _num(self, key: str):
        val = self.entry.data.get(key)
        if isinstance(val, (int, float)):           # numeric entry-data (contracted W)
            return float(val)
        if not val:
            return None
        st = self.hass.states.get(val)
        if st is None or st.state in _UNAVAILABLE:
            return None
        try:
            return float(st.state)
        except (TypeError, ValueError):
            return None

    def async_setup_listeners(self) -> None:
        sources = [self._hw(k) for k in _INPUTS]
        sources = [s for s in sources if s]
        if sources:
            self.entry.async_on_unload(
                async_track_state_change_event(
                    self.hass, sources, self._on_input_change))

    @callback
    def _on_input_change(self, _event) -> None:
        self.hass.async_create_task(self.async_request_refresh())

    def _aggregate(self) -> None:
        """Sum each module's ``energy_kwh``/``power_w`` into house totals (§8.2, §ENE-5).

        Reads every module coordinator (non-``_`` keys in ``hass.data``) that keeps
        an ``energy_kwh`` counter (DC/DV/DS via F06). The cost integrates ΔkWh×price
        each cycle; the first cycle only seeds the previous total so the modules'
        restored kWh don't show up as a one-off cost jump. Instantaneous ``power_w``
        is summed live into the house total (REQ-ENE-5).
        """
        data = self.hass.data.get(const.DOMAIN, {})
        total = 0.0
        power = 0.0
        delta = 0.0
        contrib: dict[str, float] = {}
        for key, co in list(data.items()):
            if key.startswith("_") or co is self:
                continue
            kwh = getattr(co, "energy_kwh", None)
            if isinstance(kwh, (int, float)):
                kwh = float(kwh)
                total += kwh
                # Cost deltas are tracked PER CONTRIBUTOR: a module's first
                # sample, its restore jump (0 -> historic kWh after a restart)
                # and a removed/reset module must never enter the cost as if the
                # house had just consumed those kWh.
                if getattr(co, "energy_kwh_restored", False):
                    co.energy_kwh_restored = False       # consume: reseed only
                elif key in self._contrib_prev:
                    delta += max(0.0, kwh - self._contrib_prev[key])
                contrib[key] = kwh
            pw = getattr(co, "power_w", None)
            if isinstance(pw, (int, float)):
                power += float(pw)
        self.house_kwh = total
        self.house_power_w = power
        if delta > 0.0:
            price = self._num(const.CONF_ENERGY_PRICE)
            self.house_cost = energy_engine.add_cost(self.house_cost, delta, price)
        self._contrib_prev = contrib

    def publish_energy(self, notify: bool = True) -> None:
        prev = self.context
        cfg = self._cfg()
        self._aggregate()
        self.context = energy_engine.resolve_context({
            "grid_w": self._num(const.CONF_ENERGY_GRID),
            "price": self._num(const.CONF_ENERGY_PRICE),
            "pv_w": self._num(const.CONF_ENERGY_PV),
            "consumption_w": self._num(const.CONF_ENERGY_TOTAL),
        }, cfg)
        self.context["house_kwh"] = round(self.house_kwh, 3)
        self.context["house_cost"] = round(self.house_cost, 4)
        self.context["house_power_w"] = round(self.house_power_w, 1)
        data = self.hass.data.setdefault(const.DOMAIN, {})
        data[const.DATA_ENERGY] = dict(self.context)
        if self.context != prev:                    # transitions only (const.py)
            events.fire_energy_changed(self.hass, self.entry, self.context)
            self.async_update_listeners()
            if notify:                              # nudge consumers (DC peak budget)
                for key, co in list(data.items()):
                    if not key.startswith("_") and co is not self \
                            and hasattr(co, "async_request_refresh"):
                        self.hass.async_create_task(co.async_request_refresh())

    async def _async_update_data(self) -> dict:
        # notify=True is safe here: publish_energy only nudges consumers when
        # the context materially changed, and the DC peak budget must react to
        # a tariff/headroom change without waiting out its own poll.
        self.publish_energy(notify=True)
        return self.context
