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

    def _candidates(self, targets, now_ts: float | None) -> list[tuple[str, dict]]:
        """Non-expired (source, slot) pairs whose target matches the consumer."""
        self._prune(now_ts)
        listen = {targets} if isinstance(targets, str) else set(targets)
        listen.add("")  # broadcast intents match everyone
        return [(src, s) for src, s in self._slots.items()
                if s["target"] in listen]

    def winner(self, targets, now_ts: float | None = None) -> str:
        """Highest-priority, non-expired intent matching the consumer's targets.

        ``targets`` may be a single target string or an iterable of targets the
        consumer listens on (e.g. broadcast ``"ds"`` plus its facade
        ``"ds_f180"``). Broadcast intents (empty target) always match. Pass
        ``now_ts`` (epoch seconds) to honour TTLs.
        """
        candidates = self._candidates(targets, now_ts)
        if not candidates:
            return "none"
        return max(candidates, key=lambda kv: kv[1]["priority"])[1]["intent"]

    def explain(self, targets, now_ts: float | None = None) -> dict:
        """Same arbitration as :meth:`winner`, but return the *why*.

        Returns ``{winner, source, priority, candidates, reason, target,
        ttl_remaining, runner_up, runner_up_priority}`` for the consumer's
        targets — used to surface bus decisions as diagnostic sensors and
        ``dynamic_home_conflict`` events. ``ttl_remaining`` is the winner's
        seconds left (``None`` if it never expires or ``now_ts`` is unknown);
        ``runner_up`` is the next-highest intent that lost (``None`` if it was
        the only candidate), for debugging a conflict without the full list.
        """
        candidates = self._candidates(targets, now_ts)
        if not candidates:
            return {"winner": "none", "source": None, "priority": None,
                    "candidates": 0, "reason": "no_candidates", "target": None,
                    "ttl_remaining": None, "runner_up": None,
                    "runner_up_priority": None}
        # Stable sort by priority desc picks the same slot as winner() (the
        # first maximal in insertion order) and exposes the runner-up for free.
        ranked = sorted(candidates, key=lambda kv: -kv[1]["priority"])
        src, slot = ranked[0]
        runner = ranked[1][1] if len(ranked) > 1 else None
        expires_at = slot.get("expires_at")
        ttl_remaining = (max(0.0, expires_at - now_ts)
                         if expires_at is not None and now_ts is not None
                         else None)
        return {"winner": slot["intent"], "source": src,
                "priority": slot["priority"], "candidates": len(candidates),
                "reason": "single" if len(candidates) == 1 else "priority",
                "target": slot["target"], "ttl_remaining": ttl_remaining,
                "runner_up": runner["intent"] if runner else None,
                "runner_up_priority": runner["priority"] if runner else None}
