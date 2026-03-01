"""Date and time format detection from sample values.

Strategy:
1. Try explicit pattern matching (DATETIME_FORMATS / DATE_FORMATS / TIME_FORMATS)
2. Fallback: colon-heuristic — the colon ':' appears exclusively in time
   portions (H:MM or H:MM:SS). We locate the time tail via regex, split
   off the date part and separator, then detect each half independently.
   This handles arbitrary separators and single-digit hours (e.g. 0:15)
   without needing a dedicated pattern for every combination.
"""

from __future__ import annotations

import re
from datetime import datetime

# Date format candidates ordered by priority
DATE_FORMATS = [
    ("%d.%m.%Y", r"\d{2}\.\d{2}\.\d{4}"),      # German: DD.MM.YYYY
    ("%Y-%m-%d", r"\d{4}-\d{2}-\d{2}"),          # ISO: YYYY-MM-DD
    ("%m/%d/%Y", r"\d{2}/\d{2}/\d{4}"),          # US: MM/DD/YYYY
    ("%d/%m/%Y", r"\d{2}/\d{2}/\d{4}"),          # EU: DD/MM/YYYY
    ("%d.%m.%y", r"\d{2}\.\d{2}\.\d{2}"),        # German 2-digit year: DD.MM.YY
]

TIME_FORMATS = [
    ("%H:%M", r"\d{1,2}:\d{1,2}"),                 # 24h: H:M, H:MM, HH:MM
    ("%H:%M:%S", r"\d{1,2}:\d{1,2}:\d{1,2}"),      # 24h with seconds
    ("%I:%M %p", r"\d{1,2}:\d{1,2}\s*[AaPp][Mm]"), # 12h AM/PM
]

# Combined datetime patterns (single column)
DATETIME_FORMATS = [
    # With seconds (check before without-seconds to avoid partial match)
    ("%Y-%m-%d %H:%M:%S", r"\d{4}-\d{2}-\d{2}\s+\d{1,2}:\d{1,2}:\d{1,2}"),
    ("%Y-%m-%dT%H:%M:%S", r"\d{4}-\d{2}-\d{2}T\d{1,2}:\d{1,2}:\d{1,2}"),
    ("%d.%m.%Y %H:%M:%S", r"\d{2}\.\d{2}\.\d{4}\s+\d{1,2}:\d{1,2}:\d{1,2}"),
    ("%d.%m.%Y:%H:%M:%S", r"\d{2}\.\d{2}\.\d{4}:\d{1,2}:\d{1,2}:\d{1,2}"),
    # Without seconds
    ("%Y-%m-%d %H:%M", r"\d{4}-\d{2}-\d{2}\s+\d{1,2}:\d{1,2}$"),
    ("%Y-%m-%dT%H:%M", r"\d{4}-\d{2}-\d{2}T\d{1,2}:\d{1,2}$"),
    ("%d.%m.%Y %H:%M", r"\d{2}\.\d{2}\.\d{4}\s+\d{1,2}:\d{1,2}$"),
    ("%d.%m.%Y:%H:%M", r"\d{2}\.\d{2}\.\d{4}:\d{1,2}:\d{1,2}$"),
    ("%d.%m.%y %H:%M", r"\d{2}\.\d{2}\.\d{2}\s+\d{1,2}:\d{1,2}$"),
    ("%d.%m.%y:%H:%M", r"\d{2}\.\d{2}\.\d{2}:\d{1,2}:\d{1,2}$"),
]

# Regex to find a time tail at the end of a string.
# (?<!\d) prevents matching inside a year (e.g. "2024" in "2024:0:15").
_TIME_TAIL_RE = re.compile(r"(?<!\d)(\d{1,2}:\d{1,2}(?::\d{1,2})?)$")


def detect_date_format(samples: list[str]) -> str:
    """Detect date format from sample date strings. Returns strftime format."""
    for fmt, pattern in DATE_FORMATS:
        matches = sum(1 for s in samples if re.match(pattern, s.strip()))
        if matches >= len(samples) * 0.8:
            # Validate by actually parsing
            try:
                for s in samples[:5]:
                    datetime.strptime(s.strip(), fmt)
                return fmt
            except ValueError:
                continue
    raise ValueError(f"Cannot detect date format from samples: {samples[:3]}")


def detect_time_format(samples: list[str]) -> str:
    """Detect time format from sample time strings. Returns strftime format."""
    for fmt, pattern in TIME_FORMATS:
        matches = sum(1 for s in samples if re.match(pattern, s.strip()))
        if matches >= len(samples) * 0.8:
            try:
                for s in samples[:5]:
                    datetime.strptime(s.strip(), fmt)
                return fmt
            except ValueError:
                continue
    raise ValueError(f"Cannot detect time format from samples: {samples[:3]}")


def _split_datetime_by_colon(s: str) -> tuple[str, str, str] | None:
    """Split a combined datetime string into (date, separator, time) using colon heuristic.

    The colon ':' appears exclusively in time portions (H:MM or H:MM:SS).
    We locate the time tail via regex, then scan backwards to separate the
    date-time separator from the date part.

    Examples:
        '01.01.2024 0:15'   → ('01.01.2024', ' ', '0:15')
        '01.01.2024:14:30'  → ('01.01.2024', ':', '14:30')
        '2024-01-01T15:30'  → ('2024-01-01', 'T', '15:30')
        '01.01.24 0:15:00'  → ('01.01.24', ' ', '0:15:00')
    """
    s = s.strip()
    m = _TIME_TAIL_RE.search(s)
    if not m:
        return None

    time_part = m.group(1)
    before_time = s[: m.start(1)]

    # Walk backwards over non-digit chars to isolate the separator
    i = len(before_time)
    while i > 0 and not before_time[i - 1].isdigit():
        i -= 1

    if i == 0 or i == len(before_time):
        return None  # no date part or no separator

    return before_time[:i], before_time[i:], time_part


def _heuristic_datetime_format(samples: list[str]) -> str | None:
    """Detect datetime format by splitting on colon-heuristic and detecting parts independently.

    Returns a combined strftime format string or None if detection fails.
    """
    splits: list[tuple[str, str, str]] = []
    for s in samples:
        result = _split_datetime_by_colon(s.strip())
        if result is None:
            return None
        splits.append(result)

    if not splits:
        return None

    # All samples must share the same separator
    separators = {sp[1] for sp in splits}
    if len(separators) != 1:
        return None

    separator = separators.pop()
    date_parts = [sp[0] for sp in splits]
    time_parts = [sp[2] for sp in splits]

    try:
        date_fmt = detect_date_format(date_parts)
    except ValueError:
        return None

    try:
        time_fmt = detect_time_format(time_parts)
    except ValueError:
        return None

    combined_fmt = f"{date_fmt}{separator}{time_fmt}"

    # Validate the full format parses correctly
    try:
        for s in samples[:5]:
            datetime.strptime(s.strip(), combined_fmt)
        return combined_fmt
    except ValueError:
        return None


def detect_datetime_format(samples: list[str]) -> tuple[str, bool]:
    """Detect combined datetime format from sample strings.

    Returns (strftime_format, is_combined).
    is_combined=True means date+time are in a single column.

    Strategy:
    1. Try explicit pattern matching against DATETIME_FORMATS.
    2. Fallback: colon-based heuristic — locate the time tail via ':',
       detect date and time parts independently, combine.
    """
    for fmt, pattern in DATETIME_FORMATS:
        matches = sum(1 for s in samples if re.match(pattern, s.strip()))
        if matches >= len(samples) * 0.8:
            try:
                for s in samples[:5]:
                    datetime.strptime(s.strip(), fmt)
                return fmt, True
            except ValueError:
                continue

    # Fallback: colon-heuristic
    heuristic_fmt = _heuristic_datetime_format(samples)
    if heuristic_fmt is not None:
        return heuristic_fmt, True

    raise ValueError(f"Cannot detect datetime format from samples: {samples[:3]}")
