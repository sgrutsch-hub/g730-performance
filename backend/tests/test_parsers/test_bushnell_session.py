from __future__ import annotations

"""Tests for the Bushnell Session Export CSV parser."""

from datetime import date
from decimal import Decimal

import pytest

from app.parsers.bushnell_session import BushnellSessionParser

SAMPLE_SESSION_CSV = """user@example.com
7i,
,Date,Time,Ball Speed,Launch Angle,Launch Direction,Side Spin,Back Spin,Spin Rate,Spin Axis,Club Speed,Club Speed Impact,Efficiency,AoA,Club Path,Face to Path,Lie Angle,Dynamic Loft,Closure Rate,Horz Impact,Vert Impact,Face to Target,Carry,Total,Peak Height,Offline,Total Offline,Curve,Descent Angle,Hang Time
1,3/19/26,10:30,107.2,22.5,-1.2,-168,5220,5224,3.1,78.5,78.0,1.37,-2.3,-2.1,1.3,0.5,24.1,150.2,0.3,0.1,-0.8,155.2,167.6,82.1,-3.4,-4.2,0.8,42.1,5.2
2,3/19/26,10:31,109.8,21.3,0.5,105,4945,4950,-1.2,80.1,79.5,1.37,-1.8,0.3,-0.2,0.3,23.2,155.0,0.1,0.2,0.5,162.1,174.7,85.6,1.2,1.8,0.3,43.5,5.4
Average,,,108.50,21.90,-0.35,,,,,,,,,,,,,,,,,,158.65,171.15,83.85,-1.10,-1.20,,42.80,5.30
3h,
,Date,Time,Ball Speed,Launch Angle,Launch Direction,Side Spin,Back Spin,Spin Rate,Spin Axis,Club Speed,Club Speed Impact,Efficiency,AoA,Club Path,Face to Path,Lie Angle,Dynamic Loft,Closure Rate,Horz Impact,Vert Impact,Face to Target,Carry,Total,Peak Height,Offline,Total Offline,Curve,Descent Angle,Hang Time
1,3/19/26,10:45,128.2,16.5,-0.8,-188,4670,4674,2.3,90.5,90.0,1.42,-1.2,-1.5,0.3,0.2,18.1,180.2,0.2,0.1,-0.3,185.9,200.8,92.3,-2.1,-3.0,0.5,38.2,5.8
"""


class TestBushnellSessionParser:
    """Test suite for BushnellSessionParser."""

    def setup_method(self) -> None:
        self.parser = BushnellSessionParser()

    def test_detect_valid(self) -> None:
        assert self.parser.detect(SAMPLE_SESSION_CSV) is True

    def test_detect_invalid(self) -> None:
        assert self.parser.detect("Dates,03-18-2026,Place,,Player,,\nClub,Index,") is False

    def test_parse_returns_one_session(self) -> None:
        """All shots are on 3/19/26, so should produce one session."""
        sessions = self.parser.parse(SAMPLE_SESSION_CSV, "test.csv")
        assert len(sessions) == 1

    def test_parse_date_conversion(self) -> None:
        """3/19/26 should become 2026-03-19."""
        sessions = self.parser.parse(SAMPLE_SESSION_CSV, "test.csv")
        assert sessions[0].session_date == date(2026, 3, 19)

    def test_parse_shot_count(self) -> None:
        """Should get 3 shots (2 for 7i + 1 for 3h), skipping Average rows."""
        sessions = self.parser.parse(SAMPLE_SESSION_CSV, "test.csv")
        assert len(sessions[0].shots) == 3

    def test_parse_club_normalization(self) -> None:
        sessions = self.parser.parse(SAMPLE_SESSION_CSV, "test.csv")
        clubs = {s.club_name for s in sessions[0].shots}
        assert "7 Iron" in clubs
        assert "3 Hybrid" in clubs

    def test_parse_ball_speed(self) -> None:
        sessions = self.parser.parse(SAMPLE_SESSION_CSV, "test.csv")
        shot = sessions[0].shots[0]
        assert shot.ball_speed_mph == Decimal("107.2")

    def test_parse_carry(self) -> None:
        sessions = self.parser.parse(SAMPLE_SESSION_CSV, "test.csv")
        shot = sessions[0].shots[0]
        assert shot.carry_yards == Decimal("155.2")

    def test_parse_directions_are_plain_numbers(self) -> None:
        """Session format uses plain signed numbers, not prefix/suffix notation."""
        sessions = self.parser.parse(SAMPLE_SESSION_CSV, "test.csv")
        shot = sessions[0].shots[0]
        assert shot.launch_direction_deg == Decimal("-1.2")
        assert shot.offline_yards == Decimal("-3.4")

    def test_parse_club_data(self) -> None:
        sessions = self.parser.parse(SAMPLE_SESSION_CSV, "test.csv")
        shot = sessions[0].shots[0]
        assert shot.club_speed_mph == Decimal("78.5")
        assert shot.smash_factor == Decimal("1.37")
        assert shot.attack_angle_deg == Decimal("-2.3")
        assert shot.club_path_deg == Decimal("-2.1")
