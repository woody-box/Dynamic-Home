"""SDHB — in-memory intent bus (pure, no Home Assistant dependencies).

Replaces ~2500 lines of YAML ``input_text`` "slots" + template arbitration with
a dict and a resolver. Each source owns one slot; intents carry a priority and a
target. Consumers ask for the highest-priority intent matching their target(s).
"""

from __future__ import annotations


class SdhbHub:
    """Shared coordination bus across DC / DV / DS."""

    def __init__(self) -> None:
        self._slots: dict[str, dict] = {}

    def publish(self, source: str, intent: str, target: str,
                priority: int = 50) -> None:
        self._slots[source] = {"intent": intent, "target": target,
                               "priority": priority}

    def clear(self, source: str) -> None:
        """Remove a source's intent from the bus."""
        self._slots.pop(source, None)

    def winner(self, targets) -> str:
        """Highest-priority intent matching the consumer's targets.

        ``targets`` may be a single target string or an iterable of targets the
        consumer listens on (e.g. broadcast ``"ds"`` plus its facade
        ``"ds_f180"``). Broadcast intents (empty target) always match.
        """
        listen = {targets} if isinstance(targets, str) else set(targets)
        listen.add("")  # broadcast intents match everyone
        candidates = [s for s in self._slots.values() if s["target"] in listen]
        if not candidates:
            return "none"
        return max(candidates, key=lambda s: s["priority"])["intent"]
