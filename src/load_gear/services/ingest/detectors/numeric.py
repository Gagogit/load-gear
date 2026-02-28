"""Decimal separator and unit detection."""

from __future__ import annotations

import re


def detect_decimal_separator(samples: list[str]) -> str:
    """Detect decimal separator from sample numeric strings.

    Returns ',' or '.'.

    Handles thousands separators:
      German: 1.234,56 → decimal=,  (dots are thousands)
      English: 1,234.56 → decimal=. (commas are thousands)
    """
    comma_count = 0
    dot_count = 0

    for s in samples:
        s = s.strip()
        if not s:
            continue
        # German thousands format: 1.234,56 or 1.234.567,89
        if re.match(r"^-?\d{1,3}(\.\d{3})*,\d{1,3}$", s):
            comma_count += 1
        # Simple comma decimal: 12,5
        elif re.match(r"^-?\d+,\d{1,3}$", s):
            comma_count += 1
        # English thousands format: 1,234.56 or 1,234,567.89
        elif re.match(r"^-?\d{1,3}(,\d{3})*\.\d{1,3}$", s):
            dot_count += 1
        # Simple dot decimal: 12.5
        elif re.match(r"^-?\d+\.\d{1,3}$", s):
            dot_count += 1

    if comma_count > dot_count:
        return ","
    return "."


def detect_unit(header_text: str) -> str:
    """Detect energy unit from header text. Returns kW, kWh, Wh, or MWh.

    Order matters: check longer/more-specific units first to avoid
    kWh matching the kW pattern.
    """
    # Check MWh first (most specific)
    if re.search(r"MWh", header_text, re.IGNORECASE):
        return "MWh"
    # kWh before kW
    if re.search(r"kWh", header_text, re.IGNORECASE):
        return "kWh"
    # kW (not followed by h)
    if re.search(r"kW(?!h)", header_text, re.IGNORECASE):
        return "kW"
    # Wh (not preceded by k or M)
    if re.search(r"(?<![kM])Wh", header_text, re.IGNORECASE):
        return "Wh"
    return "kWh"  # default assumption
