"""Encoding detection using chardet."""

from __future__ import annotations

import chardet


def detect_encoding(raw_bytes: bytes) -> str:
    """Detect file encoding from raw bytes. Returns lowercase encoding name."""
    # Try BOM detection first
    if raw_bytes.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    if raw_bytes.startswith(b"\xff\xfe"):
        return "utf-16-le"
    if raw_bytes.startswith(b"\xfe\xff"):
        return "utf-16-be"

    result = chardet.detect(raw_bytes)
    encoding = (result.get("encoding") or "utf-8").lower()

    # Normalize common aliases
    encoding_map = {
        "ascii": "utf-8",
        "iso-8859-1": "iso-8859-1",
        "latin-1": "iso-8859-1",
        "latin1": "iso-8859-1",
        "windows-1252": "windows-1252",
        "cp1252": "windows-1252",
    }
    return encoding_map.get(encoding, encoding)
