"""SDHB — in-memory intent bus (pure, no Home Assistant dependencies).

Replaces ~2500 lines of YAML ``input_text`` "slots" + template arbitration with
a dict and a resolver. Each source owns one slot; intents carry a priority, a
target and an optional TTL (they expire on their own). Consumers ask for the
highest-priority, non-expired intent matching their target(s).
"""

from __future__ import annotations


class SdhbHub:
    """Shared coordination bus across DC / DV / DS."""

    def __init__(self) -> None:
        self._slots: dict[str, dict] = {}

    def publish(self, source: str, intent: str, target: str,
                priority: int = 50, ttl_s: float = 0,
                now_ts: float | None = None) -> None:
        expires_at = (now_ts + ttl_s) if (ttl_s and now_ts is not None) else None
        self._slots[source] = {"intent": intent, "target": target,
                               "priority": priority, "expires_at": expires_at}

    def clear(self, source: str) -> None:
        """Remove a source's intent from the bus."""
        self._slots.pop(source, None)

    def _prune(self, now_ts: float | None) -> None:
        if now_ts is None:
            return
        for src in [s for s, v in self._slots.items()
                    if v.get("expires_at") is not None and now_ts >= v["expires_at"]]:
            del self._slots[src]

    def winner(self, targets, now_ts: float | None = None) -> str:
        """Highest-priority, non-expired intent matching the consumer's targets.

        ``targets`` may be a single target string or an iterable of targets the
        consumer listens on (e.g. broadcast ``"ds"`` plus its facade
        ``"ds_f180"``). Broadcast intents (empty target) always match. Pass
        ``now_ts`` (epoch seconds) to honour TTLs.
        """
        self._prune(now_ts)
        listen = {targets} if isinstance(targets, str) else set(targets)
        listen.add("")  # broadcast intents match everyone
        candidates = [s for s in self._slots.values() if s["target"] in listen]
        if not candidates:
            return "none"
        return max(candidates, key=lambda s: s["priority"])["intent"]
