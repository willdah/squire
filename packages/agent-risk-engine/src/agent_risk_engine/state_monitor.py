"""StateMonitor — Layer 3: System state awareness.

Protocol, stub, and call-tracking implementation.
Framework-agnostic — no imports from squire or any agent framework.
"""

from collections import Counter, deque
from typing import Protocol

from .models import SystemState


class StateMonitor(Protocol):
    """Monitors system health for risk-relevant conditions."""

    def check(self) -> SystemState:
        """Check current system state and return risk-relevant signals.

        Returns:
            SystemState with health status, warnings, and risk adjustment.
        """
        ...


class NullStateMonitor:
    """Stub monitor that always reports healthy state."""

    def check(self) -> SystemState:
        return SystemState()


class CallTracker:
    """Tracks tool call history for loop and repetition detection.

    Implements the StateMonitor protocol. When used with RiskEvaluator,
    calls are recorded automatically before each check().

    Args:
        window: Number of recent calls to retain.
        loop_threshold: Consecutive identical calls needed to flag a loop.
    """

    def __init__(self, window: int = 20, loop_threshold: int = 3) -> None:
        self._history: deque[str] = deque(maxlen=window)
        self._loop_threshold = loop_threshold

    def record(self, tool_name: str) -> None:
        """Record a tool call. Called automatically by RiskEvaluator."""
        self._history.append(tool_name)

    def check(self) -> SystemState:
        warnings: list[str] = []
        adjustment = 0

        # Consecutive repetition: same tool N times in a row
        if len(self._history) >= self._loop_threshold:
            tail = list(self._history)[-self._loop_threshold :]
            if len(set(tail)) == 1:
                warnings.append(
                    f"Possible agent loop: '{tail[0]}' called "
                    f"{self._loop_threshold} times consecutively"
                )
                adjustment += 2

        # High repetition ratio in the window
        if len(self._history) >= 5:
            counts = Counter(self._history)
            name, count = counts.most_common(1)[0]
            ratio = count / len(self._history)
            if ratio > 0.7 and count > 3:
                warnings.append(
                    f"High repetition: '{name}' is "
                    f"{count}/{len(self._history)} recent calls"
                )
                adjustment += 1

        return SystemState(
            healthy=len(warnings) == 0,
            warnings=warnings,
            risk_adjustment=adjustment,
        )

    @property
    def call_count(self) -> int:
        """Total number of calls in the current window."""
        return len(self._history)

    def reset(self) -> None:
        """Clear all recorded history."""
        self._history.clear()
