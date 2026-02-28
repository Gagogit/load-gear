"""CSV delimiter detection via frequency analysis, csv.Sniffer, and clevercsv."""

from __future__ import annotations

import csv
import io


CANDIDATE_DELIMITERS = [";", ",", "\t", "|"]


def detect_delimiter(text: str) -> str:
    """Detect CSV delimiter from decoded text content.

    Uses csv.Sniffer first, then clevercsv, then frequency analysis.
    """
    # Take first ~20 lines for analysis
    lines = text.strip().split("\n")[:20]
    sample = "\n".join(lines)

    # Try csv.Sniffer
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters="".join(CANDIDATE_DELIMITERS))
        return dialect.delimiter
    except csv.Error:
        pass

    # Try clevercsv as second attempt
    try:
        import clevercsv
        dialect = clevercsv.Sniffer().sniff(sample, verbose=False)
        if dialect and dialect.delimiter in CANDIDATE_DELIMITERS:
            return dialect.delimiter
    except Exception:
        pass

    # Fallback: frequency analysis — pick delimiter with most consistent count across lines
    best_delimiter = ","
    best_score = -1

    for delim in CANDIDATE_DELIMITERS:
        counts = [line.count(delim) for line in lines if line.strip()]
        if not counts or counts[0] == 0:
            continue
        # Score = consistency (all lines same count) * count
        if len(set(counts)) == 1:
            score = counts[0] * 10  # bonus for perfect consistency
        else:
            score = min(counts)
        if score > best_score:
            best_score = score
            best_delimiter = delim

    return best_delimiter
