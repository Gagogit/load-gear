"""P4.3 — Asset Fingerprinting (STUB per ADR-005).

Pass-through stub that returns null asset hints.
Future: detect PV midday dip, battery night charge, KWK patterns.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def detect_assets(rows: list[dict]) -> dict:
    """Detect asset patterns in the time series.

    Returns asset_hints dict for analysis_profiles.asset_hints.
    In v0.1, always returns null values (ADR-005).
    """
    logger.debug("Asset fingerprinting stub — returning null hints")
    return {
        "asset_hints": None,
        "pv": None,
        "battery": None,
        "kwk": None,
    }
