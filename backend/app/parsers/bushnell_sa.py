from __future__ import annotations

"""
Bushnell Launch Pro — Shot Analysis CSV parser.

Format characteristics:
  - First line contains "Shot Analysis"
  - Club sections: club name alone on a line (e.g., "7i,")
  - Header row: ",Date,Time,..."
  - Direction values use SUFFIX notation: "5.2 L", "3.1 R", "2.0 DN", "1.5 UP"
  - Multiple clubs per file, each with their own header
  - "Average," rows at end of each section

Column mapping (0-indexed):
  0: Index, 1: Date, 2: Time, 3: Carry, 4: ?, 5: Apex
  6: Offline, 7: ?, 8: Landing Angle, 9: ?, 10: Ball Speed
  11: Launch Angle, 12: Launch Direction, 13: Side Spin, 14: Back Spin
  15: Spin Rate, 16: Spin Axis/Club Speed, 17: ?, 18: Smash Factor
  19: Attack Angle, 20: Club Path, ...27: Face Angle
"""

import re
from datetime import date
from decimal import Decimal, InvalidOperation

from app.parsers.base import BaseParser, ParsedSession, ParsedShot

CLUB_MAP: dict[str, str] = {
    "3h": "3 Hybrid", "4h": "4 Hybrid", "5h": "5 Hybrid",
    "3i": "3 Iron", "4i": "4 Iron", "5i": "5 Iron", "6i": "6 Iron",
    "7i": "7 Iron", "8i": "8 Iron", "9i": "9 Iron",
    "pw": "PW", "sw": "SW", "gw": "GW", "lw": "LW",
    "dr": "Driver", "3w": "3 Wood", "5w": "5 Wood",
}


def _normalize_club(raw: str) -> str:
    cleaned = raw.strip()
    return CLUB_MAP.get(cleaned.lower(), cleaned)


def _num(val: str | None) -> Decimal | None:
    if val is None:
        return None
    val = val.strip()
    if not val:
        return None
    try:
        return Decimal(val)
    except InvalidOperation:
        return None


def _parse_suffix_dir(val: str | None, left_negative: bool = True) -> Decimal | None:
    """
    Parse Bushnell Shot Analysis suffix direction notation.

    Examples: "5.2 L" → -5.2, "3.1 R" → 3.1, "2.0 DN" → -2.0, "1.5 UP" → 1.5
    Also handles: "O-I" (out-to-in = negative), "I-O" (in-to-out = positive)
    """
    if val is None:
        return None
    val = val.strip()
    if not val:
        return None

    parts = val.split()
    if len(parts) < 2:
        # No direction suffix — treat as plain number
        try:
            return Decimal(val)
        except InvalidOperation:
            return None

    try:
        number = Decimal(parts[0])
    except InvalidOperation:
        return None

    direction = parts[1].upper()
    left_dirs = {"L", "DN", "O-I"}
    right_dirs = {"R", "UP", "I-O"}

    if direction in left_dirs:
        return -number if left_negative else number
    if direction in right_dirs:
        return number if left_negative else -number
    return number


def _to_int(val: Decimal | None) -> int | None:
    if val is None:
        return None
    return int(val)


class BushnellShotAnalysisParser(BaseParser):
    """Parser for Bushnell Launch Pro Shot Analysis CSV exports."""

    def detect(self, content: str, filename: str = "") -> bool:
        """Detect by looking for 'Shot Analysis' in the first line."""
        first_line = content.split("\n", 1)[0].strip()
        return "Shot Analysis" in first_line

    def parse(self, content: str, filename: str = "") -> list[ParsedSession]:
        """Parse Shot Analysis CSV into sessions (grouped by date)."""
        lines = content.split("\n")
        shots_by_date: dict[str, list[ParsedShot]] = {}
        current_club: str | None = None
        header_found = False

        for line in lines:
            stripped = line.strip()
            if not stripped or "Shot Analysis" in stripped:
                continue

            # Club name line: "7i," or "Driver,"
            if (
                re.match(r"^[A-Za-z0-9\s]+,$", stripped)
                and not stripped.startswith(",")
                and len(stripped.split(",")) <= 2
            ):
                current_club = _normalize_club(stripped.rstrip(",").strip())
                header_found = False
                continue

            # Header line
            if stripped.startswith(",Date,Time,"):
                header_found = True
                continue

            # Average line
            if stripped.startswith("Average,"):
                continue

            if not header_found or not current_club:
                continue

            cols = stripped.split(",")
            if len(cols) < 20:
                continue

            # First column should be a shot index number
            try:
                int(cols[0])
            except ValueError:
                continue

            # Extract date
            raw_date = (cols[1] or "").strip().replace("/", "-")

            # Parse shot data
            carry = _num(cols[3])
            if carry is not None and carry <= 0:
                continue

            shot = ParsedShot(
                club_name=current_club,
                ball_speed_mph=_num(cols[10]),
                launch_angle_deg=_num(cols[11]),
                launch_direction_deg=_parse_suffix_dir(cols[12]) if len(cols) > 12 else None,
                side_spin_rpm=_to_int(_parse_suffix_dir(cols[13])) if len(cols) > 13 else None,
                back_spin_rpm=_to_int(_parse_suffix_dir(cols[14])) if len(cols) > 14 else None,
                spin_rate_rpm=(
                    _to_int(_num(cols[15])) or _to_int(_num(cols[14]))
                    if len(cols) > 15
                    else None
                ),
                spin_axis_deg=(
                    _parse_suffix_dir(cols[16], left_negative=False)
                    if len(cols) > 16
                    else None
                ),
                apex_feet=_num(cols[5]),
                carry_yards=carry,
                offline_yards=_parse_suffix_dir(cols[6]) if len(cols) > 6 else None,
                landing_angle_deg=_num(cols[8]) if len(cols) > 8 else None,
                club_path_deg=_parse_suffix_dir(cols[20]) if len(cols) > 20 else None,
                face_angle_deg=_parse_suffix_dir(cols[27]) if len(cols) > 27 else None,
                attack_angle_deg=(
                    _parse_suffix_dir(cols[19], left_negative=False)
                    if len(cols) > 19
                    else None
                ),
                smash_factor=_num(cols[18]) if len(cols) > 18 else None,
                club_speed_mph=_num(cols[16]) if len(cols) > 16 else None,
            )

            shots_by_date.setdefault(raw_date, []).append(shot)

        # Create sessions grouped by date
        sessions: list[ParsedSession] = []
        for date_str, shots in sorted(shots_by_date.items()):
            session_date = self._parse_date(date_str)
            if not session_date:
                continue
            sessions.append(
                ParsedSession(
                    source_file=f"{filename}_{date_str}",
                    source_format="bushnell_sa",
                    session_date=session_date,
                    shots=shots,
                )
            )

        return sessions

    @staticmethod
    def _parse_date(date_str: str) -> date | None:
        """Parse MM-DD-YYYY to date."""
        parts = date_str.split("-")
        if len(parts) != 3:
            return None
        try:
            return date(int(parts[2]), int(parts[0]), int(parts[1]))
        except (ValueError, IndexError):
            return None
