"""Shared degraded-source tracking + HA Repairs issues (F07).

A module is *degraded* when one of its **required** sources is configured but
absent/renamed or stale (``unavailable``/``unknown``). On any transition we fire
the ``dynamic_home_degraded`` event immediately; once the degraded state has
lasted longer than :data:`const.ISSUE_STALE_S` we raise a (non-fixable) Repairs
issue listing the missing sources, so a brief blip on restart never nags.

The logic lives in a mixin so DV, DS and DC share one path: the host coordinator
sets ``self._module`` and calls :meth:`DegradedTracker.init_degraded` from its
``__init__``, then each cycle calls
``self._update_degraded(self._missing_required(), now_ts)``.
"""

from __future__ import annotations

import homeassistant.helpers.issue_registry as ir
from homeassistant.config_entries import ConfigEntry

from . import const, events

# A configured source counts as dead (missing/renamed or stale) in these states.
_DEAD_STATES = ("unknown", "unavailable", "none", "")

# Human labels for each module's required roles, used in the issue/event text.
# (DC computes its own ``missing`` inline — only "indoor temperature", and only
# while a mode is demanded — so it is not listed here.)
REQUIRED_LABELS: dict[str, dict[str, str]] = {
    const.MODULE_VMC: {
        const.CONF_SW_PWR: "power relay",
        const.CONF_SW_V2: "V2 relay",
        const.CONF_SW_V3: "V3 relay",
        const.CONF_CO2: "CO₂",
        const.CONF_PM25: "PM2.5",
    },
    const.MODULE_SHUTTER: {
        const.CONF_COVER: "cover",
    },
}

# Friendly Spanish labels for *every* configurable source per module, used by the
# live health breakdown (:meth:`DegradedTracker.health_report`) so a user can see
# at a glance why something reads "No disponible": configured-but-down vs simply
# not configured. Ordered required-first. Roles absent here (pure config like the
# facade azimuth or the bus target) are intentionally skipped.
SOURCE_LABELS: dict[str, dict[str, str]] = {
    const.MODULE_VMC: {
        const.CONF_SW_PWR: "Relé de potencia",
        const.CONF_SW_V2: "Relé V2",
        const.CONF_SW_V3: "Relé V3",
        const.CONF_CO2: "CO₂",
        const.CONF_PM25: "PM2.5",
        const.CONF_T_IN: "Temperatura interior",
        const.CONF_T_EXT: "Temperatura exterior",
        const.CONF_AQI: "AQI exterior",
        const.CONF_HUM_IN: "Humedad interior",
        const.CONF_HUM_BATH: "Humedad baño",
        const.CONF_HUM_EXT: "Humedad exterior",
        const.CONF_HRV_SUPPLY: "HRV impulsión",
        const.CONF_HRV_INTAKE: "HRV toma exterior",
        const.CONF_HRV_EXTRACT: "HRV extracción",
        const.CONF_HRV_EXHAUST: "HRV expulsión",
        const.CONF_VOC: "VOC",
        const.CONF_NOX: "NOx",
        const.CONF_HOOD_V1: "Campana V1",
        const.CONF_HOOD_V2: "Campana V2",
        const.CONF_HOOD_V3: "Campana V3",
        const.CONF_POWER_METER: "Medidor de potencia",
    },
    const.MODULE_SHUTTER: {
        const.CONF_COVER: "Persiana",
        const.CONF_CLIMATE: "Clima (modo/consigna)",
        const.CONF_DS_T_IN: "Temperatura interior",
        const.CONF_DS_T_OUT: "Temperatura exterior",
        const.CONF_WIND: "Viento",
        const.CONF_RAIN: "Lluvia",
        const.CONF_DS_ALERT: "Alerta meteo",
        const.CONF_DS_ALERT_HAIL: "Alerta granizo",
        const.CONF_DS_ALERT_WIND: "Alerta viento",
        const.CONF_POWER_METER: "Medidor de potencia",
    },
    const.MODULE_CLIMATE: {
        const.CONF_DC_T_INT: "Temperatura interior",
        const.CONF_DC_T_EXT: "Temperatura exterior",
        const.CONF_DC_CLIMATE: "Termostato (climate)",
        const.CONF_DC_VMC: "VMC asociada",
        const.CONF_DC_HUMIDITY: "Humedad",
        const.CONF_DC_WEATHER: "Weather",
        const.CONF_DC_WIND: "Viento",
        const.CONF_DC_WINDOW: "Ventana",
        const.CONF_DC_VALVE: "Válvula/relé real",
        const.CONF_DC_DEMAND_HEAT: "Demanda calor",
        const.CONF_DC_DEMAND_COOL: "Demanda frío",
        const.CONF_DC_DEHUMIDIFIER: "Deshumidificador",
        const.CONF_DC_ADJ_TEMP: "Temperatura adyacente",
        const.CONF_DC_ADJ_DOOR: "Puerta adyacente",
        const.CONF_POWER_METER: "Medidor de potencia",
    },
}


class DegradedTracker:
    """Mixin that raises/clears a Repairs issue for missing required sources.

    The host coordinator must provide ``self.hass``, ``self.entry``,
    ``self._hw(key)`` and set ``self._module`` before any update runs.
    """

    def init_degraded(self, entry: ConfigEntry) -> None:
        """Initialise the degraded-tracking state (call from ``__init__``)."""
        self.degraded = False
        self._prev_degraded = False
        self._degraded_since: float | None = None
        self._issue_id = f"degraded_{entry.entry_id}"

    def _source_dead(self, key: str) -> bool:
        """True if a *configured* source is absent/renamed or stale.

        Unconfigured (optional) sources return ``False`` — only required roles
        are ever passed here, and they are always configured at setup time.
        """
        ent = self._hw(key)
        if not ent:
            return False
        st = self.hass.states.get(ent)
        return st is None or st.state in _DEAD_STATES

    def _missing_required(self) -> list[str]:
        """Human labels of this module's required sources that are dead."""
        labels = REQUIRED_LABELS.get(self._module, {})
        return [lbl for key, lbl in labels.items() if self._source_dead(key)]

    def health_report(self) -> dict:
        """Per-source status so a user can tell *why* something reads unavailable.

        Walks every configurable source of this module (see :data:`SOURCE_LABELS`)
        and classifies it: ``ok`` (configured and live), ``no disponible``
        (configured but missing/renamed or ``unavailable``/``unknown``), or
        ``sin configurar`` (optional role left blank — the usual reason a derived
        entity never appears). Returned as plain dicts/lists so it can sit on a
        diagnostic entity's attributes (no translation layer needed).
        """
        labels = SOURCE_LABELS.get(self._module, {})
        fuentes: dict[str, str] = {}
        sin_configurar: list[str] = []
        no_disponibles: list[str] = []
        for key, lbl in labels.items():
            ent = self._hw(key)
            if not ent:
                sin_configurar.append(lbl)
                continue
            st = self.hass.states.get(ent)
            if st is None or st.state in _DEAD_STATES:
                fuentes[lbl] = "no disponible"
                no_disponibles.append(lbl)
            else:
                fuentes[lbl] = "ok"
        ok_n = sum(1 for v in fuentes.values() if v == "ok")
        if no_disponibles:
            resumen = f"{len(no_disponibles)} sin datos: " + ", ".join(no_disponibles)
        elif fuentes:
            resumen = f"{ok_n} fuentes OK"
        else:
            resumen = "sin fuentes configuradas"
        return {
            "resumen": resumen,
            "fuentes": fuentes,
            "no_disponibles": no_disponibles,
            "sin_configurar": sin_configurar,
        }

    def _update_degraded(self, missing: list[str], now_ts: float) -> bool:
        """Track the degraded state: fire on transition, raise a repair if sustained.

        ``missing`` is the list of human-readable required sources currently
        absent (empty == healthy). The event fires immediately on any flip; the
        Repairs issue only appears once the module has been degraded longer than
        :data:`const.ISSUE_STALE_S`.
        """
        degraded = bool(missing)
        if degraded != self._prev_degraded:
            events.fire_degraded(self.hass, self.entry, self._module,
                                 degraded, missing)
            self._prev_degraded = degraded
        if degraded:
            if self._degraded_since is None:
                self._degraded_since = now_ts
            elif now_ts - self._degraded_since >= const.ISSUE_STALE_S:
                ir.async_create_issue(
                    self.hass, const.DOMAIN, self._issue_id,
                    is_fixable=False, severity=ir.IssueSeverity.WARNING,
                    translation_key=const.ISSUE_REQUIRED_SOURCE,
                    translation_placeholders={"name": self.entry.title,
                                              "missing": ", ".join(missing)},
                    learn_more_url=const.LEARN_MORE_URL)
        else:
            self._degraded_since = None
            self.clear_issue()
        return degraded

    def clear_issue(self) -> None:
        """Remove this module's degraded repair issue (no-op if absent)."""
        ir.async_delete_issue(self.hass, const.DOMAIN, self._issue_id)
