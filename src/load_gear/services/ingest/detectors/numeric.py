"""Decimal separator and unit detection."""

from __future__ import annotations

import re


def detect_decimal_separator(samples: list[str]) -> str:
    """Detect decimal separator from sample numeric strings.

    Returns ',' or '.'.
    """
    comma_count = 0
    dot_count = 0

    for s in samples:
        s = s.strip()
        # Count occurrences in numeric context (not thousands separator)
        # A decimal separator appears once, followed by 1-3 digits at end
        if re.match(r"^-?\d+,\d{1,3}$", s):
            comma_count += 1
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
