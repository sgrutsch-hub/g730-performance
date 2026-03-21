from __future__ import annotations

"""
CSV parser registry with auto-detection.

Each parser implements the BaseParser interface and registers itself.
The detect_and_parse() function tries each parser's detect() method
in priority order and delegates to the first match.

Adding a new launch monitor parser:
  1. Create a new file in this package (e.g., garmin_r10.py)
  2. Subclass BaseParser
  3. Implement detect() and parse()
  4. Add it to the PARSERS list below

The parser should normalize ALL directional values to:
  - Negative = LEFT (offline, face angle, club path, spin axis)
  - Positive = RIGHT
This is critical for cross-monitor consistency.
"""

from app.parsers.base import BaseParser, ParsedSession, ParsedShot
from app.parsers.bushnell_dr import BushnellDrivingRangeParser
from app.parsers.bushnell_sa import BushnellShotAnalysisParser
from app.parsers.bushnell_session import BushnellSessionParser

# Parser registry — order matters for detection priority.
# More specific formats should come first to avoid false positives.
PARSERS: list[BaseParser] = [
    BushnellSessionParser(),
    BushnellShotAnalysisParser(),
    BushnellDrivingRangeParser(),
    # Future parsers:
    # GarminR10Parser(),
    # SkyTrakParser(),
    # FlightScopeParser(),
    # TrackManParser(),
]


def detect_and_parse(content: str, filename: str = "") -> list[ParsedSession]:
    """
    Auto-detect the CSV format and parse it.

    Tries each registered parser's detect() method in order.
    Returns a list of ParsedSession objects (one file may contain
    multiple sessions, e.g., Bushnell DrivingRange format).

    Raises:
        UnsupportedFormatError: No parser recognized the file
    """
    from app.core.exceptions import UnsupportedFormatError

    for parser in PARSERS:
        if parser.detect(content, filename):
            return parser.parse(content, filename)

    raise UnsupportedFormatError(
        f"Could not identify the file format for '{filename}'. "
        "Supported formats: Bushnell Launch Pro (DrivingRange, Shot Analysis, Session Export). "
        "More formats coming soon."
    )


__all__ = [
    "BaseParser",
    "ParsedSession",
    "ParsedShot",
    "detect_and_parse",
]
