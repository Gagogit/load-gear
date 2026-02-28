"""Date and time format detection from sample values."""

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
    ("%H:%M", r"\d{1,2}:\d{2}"),                 # 24h: HH:MM or H:MM
    ("%H:%M:%S", r"\d{1,2}:\d{2}:\d{2}"),        # 24h with seconds
    ("%I:%M %p", r"\d{1,2}:\d{2}\s*[AaPp][Mm]"), # 12h AM/PM
]

# Combined datetime patterns (single column)
DATETIME_FORMATS = [
    ("%Y-%m-%d %H:%M", r"\d{4}-\d{2}-\d{2}\s+\d{1,2}:\d{2}"),
    ("%Y-%m-%dT%H:%M", r"\d{4}-\d{2}-\d{2}T\d{1,2}:\d{2}"),
    ("%d.%m.%Y %H:%M", r"\d{2}\.\d{2}\.\d{4}\s+\d{1,2}:\d{2}"),
    ("%d.%m.%Y:%H:%M", r"\d{2}\.\d{2}\.\d{4}:\d{1,2}:\d{2}"),          # colon separator
    ("%d.%m.%Y:%H:%M:%S", r"\d{2}\.\d{2}\.\d{4}:\d{1,2}:\d{2}:\d{2}"), # colon with seconds
    ("%d.%m.%y %H:%M", r"\d{2}\.\d{2}\.\d{2}\s+\d{1,2}:\d{2}"),        # 2-digit year + time
    ("%d.%m.%y:%H:%M", r"\d{2}\.\d{2}\.\d{2}:\d{1,2}:\d{2}"),          # 2-digit year + colon
]


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


def detect_datetime_format(samples: list[str]) -> tuple[str, bool]:
    """Detect combined datetime format from sample strings.

    Returns (strftime_format, is_combined).
    is_combined=True means date+time are in a single column.
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
    raise ValueError(f"Cannot detect datetime format from samples: {samples[:3]}")
