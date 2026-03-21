from __future__ import annotations

"""
Bushnell Launch Pro — DrivingRange CSV parser.

Format characteristics:
  - Line 0: "Dates,MM-DD-YYYY,Place,Location..."
  - Header row: "Club,Index,Ball Speed,..."
  - Direction values use PREFIX notation: "L5.2", "R3.1"
  - Each file = one session (one date)
  - "Average" and "Deviation" rows at the end of each club section

Example first lines:
    Dates,03-18-2026,Place,,Player,,
    Club,Index,Ball Speed,Launch Direction,Launch Angle,Spin Rate,...
"""

import re
from datetime import date
from decimal import Decimal, InvalidOperation

from app.parsers.base import BaseParser, ParsedSession, ParsedShot

# Club abbreviation normalization map
CLUB_MAP: dict[str, str] = {
    "3h": "3 Hybrid", "4h": "4 Hybrid", "5h": "5 Hybrid",
    "3i": "3 Iron", "4i": "4 Iron", "5i": "5 Iron", "6i": "6 Iron",
    "7i": "7 Iron", "8i": "8 Iron", "9i": "9 Iron",
    "pw": "PW", "sw": "SW", "gw": "GW", "lw": "LW",
    "dr": "Driver", "3w": "3 Wood", "5w": "5 Wood",
}


def _normalize_club(raw: str) -> str:
    """Normalize club abbreviations to standard names."""
    cleaned = raw.strip()
    return CLUB_MAP.get(cleaned.lower(), cleaned)


def _num(val: str | None) -> Decimal | None:
    """Parse a numeric string to Decimal, returning None on failure."""
    if val is None:
        return None
    val = val.strip()
    if not val:
        return None
    try:
        return Decimal(val)
    except InvalidOperation:
        return None


def _parse_prefix_dir(val: str | None, left_negative: bool = True) -> Decimal | None:
    """
    Parse Bushnell DrivingRange prefix direction notation.

    Examples: "L5.2" → -5.2 (left), "R3.1" → 3.1 (right)
    Convention: L = negative, R = positive (when left_negative=True)
    """
    if val is None:
        return None
    val = val.strip()
    if not val:
        return None

    multiplier = Decimal("1")
    if val.startswith("L"):
        multiplier = Decimal("-1") if left_negative else Decimal("1")
        val = val[1:]
    elif val.startswith("R"):
        multiplier = Decimal("1") if left_negative else Decimal("-1")
        val = val[1:]

    try:
        return multiplier * Decimal(val)
    except InvalidOperation:
        return None


class BushnellDrivingRangeParser(BaseParser):
    """Parser for Bushnell Launch Pro DrivingRange CSV exports."""

    def detect(self, content: str, filename: str = "") -> bool:
        """
        Detect by looking for the signature first line pattern:
        "Dates,MM-DD-YYYY,Place,..."
        """
        first_line = content.split("\n", 1)[0].strip()
        # Must start with "Dates," or have "Club,Index," in first few lines
        if first_line.startswith("Dates,"):
            return True
        # Also check for the header row in first 5 lines
        for line in content.split("\n", 5)[:5]:
            if line.strip().startswith("Club,Index,"):
                return True
        return False

    def parse(self, content: str, filename: str = "") -> list[ParsedSession]:
        """Parse DrivingRange CSV into sessions."""
        lines = [line.strip() for line in content.split("\n") if line.strip()]
        if len(lines) < 3:
            return []

        # Extract date from metadata line
        meta = lines[0].split(",")
        file_date_str = meta[1].strip() if len(meta) > 1 else ""
        session_date = self._parse_date(file_date_str)
        if not session_date:
            return []

        # Find header row
        header_idx = -1
        for i in range(min(5, len(lines))):
            if lines[i].startswith("Club,Index,"):
                header_idx = i
                break

        if header_idx < 0:
            return []

        # Parse shots
        shots: list[ParsedShot] = []
        for i in range(header_idx + 1, len(lines)):
            cols = lines[i].split(",")
            if len(cols) < 16:
                continue

            club_raw = cols[0].strip()
            if not club_raw or club_raw in ("Average", "Deviation"):
                continue

            club = _normalize_club(club_raw)
            carry = _num(cols[10]) if len(cols) > 10 else None
            if carry is not None and carry <= 0:
                continue  # Skip zero/negative carry shots

            shot = ParsedShot(
                club_name=club,
                ball_speed_mph=_num(cols[2]) if len(cols) > 2 else None,
                launch_direction_deg=_parse_prefix_dir(cols[3]) if len(cols) > 3 else None,
                launch_angle_deg=_num(cols[4]) if len(cols) > 4 else None,
                spin_rate_rpm=self._to_int(_num(cols[5])) if len(cols) > 5 else None,
                spin_axis_deg=(
                    _parse_prefix_dir(cols[6], left_negative=False) if len(cols) > 6 else None
                ),
                back_spin_rpm=self._to_int(_num(cols[7])) if len(cols) > 7 else None,
                side_spin_rpm=(
                    self._to_int(_parse_prefix_dir(cols[8])) if len(cols) > 8 else None
                ),
                apex_feet=_num(cols[9]) if len(cols) > 9 else None,
                carry_yards=carry,
                offline_yards=_parse_prefix_dir(cols[12]) if len(cols) > 12 else None,
                landing_angle_deg=_num(cols[13]) if len(cols) > 13 else None,
                club_path_deg=_parse_prefix_dir(cols[14]) if len(cols) > 14 else None,
                face_angle_deg=_parse_prefix_dir(cols[15]) if len(cols) > 15 else None,
                attack_angle_deg=_num(cols[16]) if len(cols) > 16 else None,
                dynamic_loft_deg=_num(cols[17]) if len(cols) > 17 else None,
            )
            shots.append(shot)

        if not shots:
            return []

        return [
            ParsedSession(
                source_file=filename,
                source_format="bushnell_dr",
                session_date=session_date,
                shots=shots,
            )
        ]

    @staticmethod
    def _parse_date(date_str: str) -> date | None:
        """Parse MM-DD-YYYY to a date object."""
        parts = date_str.split("-")
        if len(parts) != 3:
            return None
        try:
            return date(int(parts[2]), int(parts[0]), int(parts[1]))
        except (ValueError, IndexError):
            return None

    @staticmethod
    def _to_int(val: Decimal | None) -> int | None:
        """Convert Decimal to int (for RPM values)."""
        if val is None:
            return None
        return int(val)
