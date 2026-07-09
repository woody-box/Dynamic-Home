"""Cover platform — the managed shutter (DS).

Represents one window. In auto it drives the underlying physical cover to the
position decided by the DS engine (and the shared SDHB bus); manual
``set_cover_position`` passes straight through to the underlying cover.
"""

from __future__ import annotations

from homeassistant.components.cover import (
    ATTR_POSITION,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

from . import const
from .coordinator import DsCoordinator

# A settled position within this many % of DH's last command counts as "our move"
# (covers don't always land on the exact target); beyond it, it was external.
_EXTERNAL_TOL_PCT = 4


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry,
                            async_add_entities: AddEntitiesCallback) -> None:
    coordinator: DsCoordinator = hass.data[const.DOMAIN][entry.entry_id]
    async_add_entities([DsCover(coordinator, entry)])


class DsCover(CoordinatorEntity[DsCoordinator], CoverEntity):
    """Managed shutter driven by the DS cascade."""

    _attr_has_entity_name = True
    # The device name leads (has_entity_name); append the short module code so this
    # managed cover reads as "<device> · DS" and is told apart from the physical
    # cover it drives, without the cryptic "- DH-DS".
    _attr_name = f"· {const.MODULE_TAG[const.MODULE_SHUTTER].removeprefix('DH-')}"
    _attr_supported_features = (
        CoverEntityFeature.OPEN
        | CoverEntityFeature.CLOSE
        | CoverEntityFeature.SET_POSITION
    )

    def __init__(self, coordinator: DsCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._last_pos: int | None = None  # last position pushed to the hardware
        self._driving = False           # a DH command is travelling right now
        self._external_moving = False   # someone ELSE is moving the cover now
        self._attr_unique_id = f"{entry.entry_id}_cover"
        # Keep the clean object_id (cover.<window>) even though the name carries
        # the "· DS" suffix — so the entity_id stays stable and the suffix is
        # display-only. Existing entities keep their registered id regardless.
        self.entity_id = f"cover.{slugify(entry.title)}"
        self._attr_device_info = DeviceInfo(
            identifiers={(const.DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Dynamic Home",
            model="Dynamic Shutter",
        )

    async def async_added_to_hass(self) -> None:
        """Reflect the underlying cover's real position promptly when it moves."""
        await super().async_added_to_hass()
        target = self._entry.data.get(const.CONF_COVER)
        if target:
            # Baseline so the first external move has a reference to compare against.
            self._last_pos = self._real_position()
            self.async_on_remove(
                async_track_state_change_event(
                    self.hass, [target], self._on_real_cover_change))

    @callback
    def _on_real_cover_change(self, event) -> None:
        self.async_write_ha_state()
        new = event.data.get("new_state")
        state = new.state if new else None
        if state in ("opening", "closing"):
            # Travelling. If DH has no command in flight, someone else started
            # this move (wall button / other automation): hold the auto logic
            # off until it settles — the override only arms on the settled
            # position, and a tick in that window used to issue a counter-order
            # that reversed the user's move mid-travel.
            if not self._driving and self.coordinator.track_external:
                self._external_moving = True
            return
        if state in (None, "unavailable", "unknown"):
            return                          # no usable state yet
        # Settled (open/closed): the travel is over, whoever started it.
        self._driving = False
        self._external_moving = False
        if self.coordinator.track_external:
            self._detect_external_move(event)

    @callback
    def _detect_external_move(self, event) -> None:
        """Arm a manual override when the cover settles where DH didn't ask.

        Any command from outside the integration (a physical button, a wall
        switch, another automation) moves the underlying cover directly. DH only
        drives that cover, so it never sees those as 'manual'. Here we compare the
        settled position against the last one DH commanded (``_last_pos``): a
        mismatch means someone else moved it, so we pause the comfort logic with a
        timed override (it expires on its own, like the integration button).
        Only called on settled states (the caller filters mid-travel ones).
        """
        new = event.data.get("new_state")
        pos = new.attributes.get("current_position")
        if pos is not None:
            real = int(pos)
        elif new.state == "closed" and (self._last_pos or 0) > 0:
            real = 0        # positionless cover, qualitative contradiction: closed
        elif new.state == "open" and self._last_pos == 0:
            real = 100      # ...or opened while we had it closed
        else:
            # A positionless "open" can mean ANY partial position: mapping it to
            # 100 turned DH's own 40% target into a false manual@100.
            return
        if self._last_pos is None:
            self._last_pos = real           # first reading: just take the baseline
            return
        if abs(real - self._last_pos) <= _EXTERNAL_TOL_PCT:
            return                          # settled where DH asked -> our own move
        self._last_pos = real               # adopt it so we don't re-fire/re-drive
        self.coordinator.arm_manual_override(real)

    def _real_position(self) -> int | None:
        """Actual position reported by the physical cover (None if unknown)."""
        target = self._entry.data.get(const.CONF_COVER)
        if not target:
            return None
        st = self.hass.states.get(target)
        if st is None:
            return None
        pos = st.attributes.get("current_position")
        return int(pos) if pos is not None else None

    @property
    def _target_position(self) -> int | None:
        data = self.coordinator.data
        return data.pos if data else None

    @property
    def current_cover_position(self) -> int | None:
        # Report the REAL physical position; only fall back to the computed
        # target when the underlying cover gives no position feedback.
        real = self._real_position()
        return real if real is not None else self._target_position

    @property
    def is_closed(self) -> bool | None:
        pos = self.current_cover_position
        return None if pos is None else pos == 0

    @property
    def extra_state_attributes(self) -> dict:
        attrs = {"facade": self.coordinator.facade_key,
                 "target_position": self._target_position,
                 "peak_reason": self.coordinator.peak_reason}
        data = self.coordinator.data
        if data:
            attrs["reason"] = data.reason
            attrs.update(data.details)
        return attrs

    # --- commands pass through to the underlying cover ---
    # A user command also arms the manual hold so the comfort logic won't undo it
    # (no getting trapped). The auto path drives via _drive directly, never here.
    async def async_set_cover_position(self, **kwargs) -> None:
        pos = kwargs[ATTR_POSITION]
        self.coordinator.arm_manual_override(pos)
        await self._drive(pos)

    async def async_open_cover(self, **kwargs) -> None:
        self.coordinator.arm_manual_override(100)
        await self._drive(100)

    async def async_close_cover(self, **kwargs) -> None:
        self.coordinator.arm_manual_override(0)
        await self._drive(0)

    async def _drive(self, position: int) -> None:
        self._last_pos = position
        target = self._entry.data.get(const.CONF_COVER)
        # Observe (dry-run) or paused: track the target but never move the cover.
        if target and not self.coordinator.observe_effective:
            # Expect travel only when the command should actually move the cover,
            # so our own opening/closing is told apart from an external (manual)
            # move; cleared when the cover settles.
            real = self._real_position()
            if real is None or abs(real - position) > _EXTERNAL_TOL_PCT:
                self._driving = True
            await self.hass.services.async_call(
                "cover", "set_cover_position",
                {"entity_id": target, ATTR_POSITION: position}, blocking=True)

    @callback
    def _handle_coordinator_update(self) -> None:
        data = self.coordinator.data
        # Only command the hardware when the target actually changed, so we
        # don't re-issue (and interrupt) the cover every cycle. And never while
        # an external (manual) move is travelling: the settled position arms the
        # manual hold, which then refreshes us — fighting it mid-travel reversed
        # a wall-button press before the override could arm.
        if (data is not None and data.pos != self._last_pos
                and not self._external_moving):
            self.hass.async_create_task(self._drive(data.pos))
        super()._handle_coordinator_update()
