"""Series type detection: cumulative (monotonic) vs interval."""

from __future__ import annotations


def detect_series_type(values: list[float]) -> str:
    """Detect whether a series is cumulative or interval.

    Cumulative: values are monotonically non-decreasing (with small tolerance for meter resets).
    Interval: values fluctuate around a level.

    Returns 'cumulative' or 'interval'.
    """
    if len(values) < 3:
        return "interval"

    # Check monotonic non-decreasing
    increases = 0
    decreases = 0
    for i in range(1, len(values)):
        diff = values[i] - values[i - 1]
        if diff > 0:
            increases += 1
        elif diff < 0:
            decreases += 1

    total = increases + decreases
    if total == 0:
        return "interval"

    # If >90% of changes are increases, likely cumulative
    if increases / total > 0.9:
        return "cumulative"
    return "interval"
