"""CallTracker — Standalone loop and repetition detection utility.

Not a pipeline layer — used by frameworks to build context before calling
RiskEvaluator. Returns a dict suitable for merging into Action.metadata.
Framework-agnostic — no external dependencies.
"""

from collections import Counter, deque


class CallTracker:
    """Tracks action call history for loop and repetition detection.

    Standalone utility — not part of the evaluation pipeline. Frameworks
    use this to build temporal context before calling RiskEvaluator.

    Args:
        window: Number of recent calls to retain.
        loop_threshold: Consecutive identical calls needed to flag a loop.
        repetition_ratio: Fraction of calls to a single action that triggers
            a high-repetition warning (default 0.7).
    """

    def __init__(
        self,
        window: int = 20,
        loop_threshold: int = 3,
        repetition_ratio: float = 0.7,
    ) -> None:
        self._history: deque[str] = deque(maxlen=window)
        self._loop_threshold = loop_threshold
        self._repetition_ratio = repetition_ratio

    def record(self, action_name: str) -> None:
        """Record an action call."""
        self._history.append(action_name)

    def check(self) -> dict:
        """Check for loops and repetition patterns.

        Returns:
            Dict with keys 'healthy' (bool) and 'warnings' (list[str]),
            suitable for merging into Action.metadata.
        """
        warnings: list[str] = []

        if len(self._history) >= self._loop_threshold:
            tail = list(self._history)[-self._loop_threshold :]
            if len(set(tail)) == 1:
                warnings.append(f"Possible agent loop: '{tail[0]}' called {self._loop_threshold} times consecutively")

        if len(self._history) >= 5:
            counts = Counter(self._history)
            name, count = counts.most_common(1)[0]
            ratio = count / len(self._history)
            if ratio > self._repetition_ratio and count > 3:
                warnings.append(f"High repetition: '{name}' is {count}/{len(self._history)} recent calls")

        return {
            "healthy": len(warnings) == 0,
            "warnings": warnings,
        }

    @property
    def call_count(self) -> int:
        """Total number of calls in the current window."""
        return len(self._history)

    def reset(self) -> None:
        """Clear all recorded history."""
        self._history.clear()
