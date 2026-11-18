"""Console helpers so CLI output works the same on Windows, macOS, and Linux."""

from __future__ import annotations

import sys


def utf8_stdio() -> None:
    """Force UTF-8 on stdout/stderr.

    Windows consoles and redirected output often default to cp1252/cp437, which
    cannot encode Vietnamese text and raise UnicodeEncodeError on print().
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="backslashreplace")
        except (ValueError, OSError):
            pass
