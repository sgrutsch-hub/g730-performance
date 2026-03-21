from __future__ import annotations

"""
Bushnell Launch Pro — Session Export CSV parser.

Format characteristics:
  - Email address on line 1
  - Club sections: club name alone on a line (e.g., "7i, ")
  - Header row: ",Date,Time,Ball Speed,Launch Angle,..."
  - Direction values are plain numbers (negative = left)
  - Date format: M/D/YY (e.g., "3/19/26")
  - Many more columns than other formats (~30+)

Column mapping (0-indexed):
  0: Index, 1: Date, 2: Time, 3: Ball Speed, 4: Launch Angle
  5: Launch Direction, 6: Side Spin, 7: Back Spin, 8: Spin Rate
  9: Spin Axis, 10: Club Speed, 11: Club Speed Impact, 12: Efficiency/Smash
  13: AoA, 14: Club Path, 15: Face to Path, 16: Lie Angle
  17: Dynamic Loft, 18: Closure Rate, 19: Horz Impact, 20: Vert Impact
  21: Face to Target, 22: Carry, 23: Total, 24: Peak Height
  25: Offline, 26: Total Offline, 27: Curve, 28: Descent Angle, 29: Hang Time
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


def _to_int(val: Decimal | None) -> int | None:
    if val is None:
        return None
    return int(val)


class BushnellSessionParser(BaseParser):
    """Parser for Bushnell Launch Pro Session Export CSV."""

    def detect(self, content: str, filename: str = "") -> bool:
        """
        Detect by looking for the specific header pattern:
        ",Date,Time,Ball Speed,Launch Angle,"
        This is distinct from Shot Analysis which has a different column order.
        """
        return ",Date,Time,Ball Speed,Launch Angle," in content

    def parse(self, content: str, filename: str = "") -> list[ParsedSession]:
        """Parse Session Export CSV into sessions (grouped by date)."""
        lines = content.split("\n")
        shots_by_date: dict[str, list[ParsedShot]] = {}
        current_club: str | None = None
        header_found = False

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            # Club name line: "7i, " or "3h, " or "Driver, "
            if (
                re.match(r"^[A-Za-z0-9\s]+,\s*$", stripped)
                and not stripped.startswith(",")
                and len(stripped.split(",")) <= 3
            ):
                current_club = _normalize_club(re.sub(r",\s*$", "", stripped).strip())
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
            if len(cols) < 25:
                continue

            # First column should be a shot index number
            try:
                int(cols[0])
            except ValueError:
                continue

            # Parse date: "3/19/26" → date(2026, 3, 19)
            raw_date = (cols[1] or "").strip()
            parsed_date = self._parse_short_date(raw_date)
            if not parsed_date:
                continue

            date_key = parsed_date.strftime("%m-%d-%Y")

            carry = _num(cols[22])
            if carry is not None and carry <= 0:
                continue

            shot = ParsedShot(
                club_name=current_club,
                ball_speed_mph=_num(cols[3]),
                launch_angle_deg=_num(cols[4]),
                launch_direction_deg=_num(cols[5]),
                side_spin_rpm=_to_int(_num(cols[6])),
                back_spin_rpm=_to_int(_num(cols[7])),
                spin_rate_rpm=_to_int(_num(cols[8])),
                spin_axis_deg=_num(cols[9]),
                club_speed_mph=_num(cols[10]),
                smash_factor=_num(cols[12]),
                attack_angle_deg=_num(cols[13]),
                club_path_deg=_num(cols[14]),
                face_to_path_deg=_num(cols[15]) if len(cols) > 15 else None,
                dynamic_loft_deg=_num(cols[17]) if len(cols) > 17 else None,
                closure_rate_dps=_num(cols[18]) if len(cols) > 18 else None,
                carry_yards=carry,
                total_yards=_num(cols[23]) if len(cols) > 23 else None,
                apex_feet=_num(cols[24]) if len(cols) > 24 else None,
                offline_yards=_num(cols[25]) if len(cols) > 25 else None,
                curve_yards=_num(cols[27]) if len(cols) > 27 else None,
                landing_angle_deg=_num(cols[28]) if len(cols) > 28 else None,
                hang_time_sec=_num(cols[29]) if len(cols) > 29 else None,
            )

            shots_by_date.setdefault(date_key, []).append(shot)

        # Create sessions grouped by date
        sessions: list[ParsedSession] = []
        for date_key, shots in sorted(shots_by_date.items()):
            parts = date_key.split("-")
            session_date = date(int(parts[2]), int(parts[0]), int(parts[1]))
            sessions.append(
                ParsedSession(
                    source_file=f"{filename}_{date_key}",
                    source_format="bushnell_session",
                    session_date=session_date,
                    shots=shots,
                )
            )

        return sessions

    @staticmethod
    def _parse_short_date(raw: str) -> date | None:
        """
        Parse M/D/YY format to date object.

        Examples: "3/19/26" → date(2026, 3, 19)
        Two-digit years: 00-50 → 2000s, 51-99 → 1900s
        """
        parts = raw.split("/")
        if len(parts) != 3:
            return None
        try:
            month = int(parts[0])
            day = int(parts[1])
            year = int(parts[2])
            if year < 100:
                year = 1900 + year if year > 50 else 2000 + year
            return date(year, month, day)
        except (ValueError, IndexError):
            return None
