from __future__ import annotations

"""Tests for the Bushnell DrivingRange CSV parser."""

from datetime import date
from decimal import Decimal

import pytest

from app.parsers.bushnell_dr import BushnellDrivingRangeParser

SAMPLE_DR_CSV = """Dates,03-18-2026,Place,,Player,,
Club,Index,Ball Speed,Launch Direction,Launch Angle,Spin Rate,Spin Axis,Back Spin,Side Spin,Apex,Carry,Total,Offline,Landing Angle,Club Path,Face Angle,Attack Angle,Dynamic Loft
7i,1,107.2,L1.2,22.5,5224,R3.1,5220,168,82.1,155.2,167.6,L3.4,42.1,L2.1,L0.8,2.3,24.1
7i,2,109.8,R0.5,21.3,4950,L1.2,4945,105,85.6,162.1,174.7,R1.2,43.5,R0.3,R0.5,1.8,23.2
7i,3,105.1,L2.8,24.1,5580,R5.2,5572,458,78.3,148.9,160.8,L8.1,40.2,L4.2,L2.1,3.1,25.8
Average,,107.37,,22.63,5251.33,,,,81.97,155.40,167.70,,41.93,,,2.40,24.37
Deviation,,2.35,,1.40,315.37,,,,3.67,6.62,6.97,,1.67,,,0.65,1.31
3h,1,128.2,L0.8,16.5,4674,R2.3,4670,188,92.3,185.9,200.8,L2.1,38.2,L1.5,L0.3,1.2,18.1
3h,2,130.8,R1.1,21.0,5224,L0.5,5220,120,98.1,192.4,207.8,R3.2,40.1,R0.8,R1.2,0.5,22.3
Average,,129.50,,18.75,4949.00,,,,95.20,189.15,204.30,,39.15,,,0.85,20.20
"""


class TestBushnellDRParser:
    """Test suite for BushnellDrivingRangeParser."""

    def setup_method(self) -> None:
        self.parser = BushnellDrivingRangeParser()

    def test_detect_valid(self) -> None:
        assert self.parser.detect(SAMPLE_DR_CSV) is True

    def test_detect_invalid(self) -> None:
        assert self.parser.detect("some,other,csv,format") is False
        assert self.parser.detect("Shot Analysis\nfoo,bar") is False

    def test_parse_returns_single_session(self) -> None:
        sessions = self.parser.parse(SAMPLE_DR_CSV, "test.csv")
        assert len(sessions) == 1

    def test_parse_session_metadata(self) -> None:
        sessions = self.parser.parse(SAMPLE_DR_CSV, "test.csv")
        session = sessions[0]
        assert session.source_format == "bushnell_dr"
        assert session.session_date == date(2026, 3, 18)
        assert session.source_file == "test.csv"

    def test_parse_shot_count(self) -> None:
        """Should parse 5 data rows, skipping Average and Deviation rows."""
        sessions = self.parser.parse(SAMPLE_DR_CSV, "test.csv")
        assert len(sessions[0].shots) == 5

    def test_parse_club_normalization(self) -> None:
        sessions = self.parser.parse(SAMPLE_DR_CSV, "test.csv")
        clubs = {s.club_name for s in sessions[0].shots}
        assert "7 Iron" in clubs
        assert "3 Hybrid" in clubs
        # Raw abbreviations should not appear
        assert "7i" not in clubs
        assert "3h" not in clubs

    def test_parse_ball_speed(self) -> None:
        sessions = self.parser.parse(SAMPLE_DR_CSV, "test.csv")
        shot = sessions[0].shots[0]
        assert shot.ball_speed_mph == Decimal("107.2")

    def test_parse_prefix_direction_left(self) -> None:
        """L prefix should produce negative values (left of target)."""
        sessions = self.parser.parse(SAMPLE_DR_CSV, "test.csv")
        shot = sessions[0].shots[0]  # 7i shot 1
        assert shot.launch_direction_deg == Decimal("-1.2")  # L1.2 → -1.2
        assert shot.offline_yards == Decimal("-3.4")  # L3.4 → -3.4

    def test_parse_prefix_direction_right(self) -> None:
        """R prefix should produce positive values (right of target)."""
        sessions = self.parser.parse(SAMPLE_DR_CSV, "test.csv")
        shot = sessions[0].shots[1]  # 7i shot 2
        assert shot.launch_direction_deg == Decimal("0.5")  # R0.5 → 0.5
        assert shot.offline_yards == Decimal("1.2")  # R1.2 → 1.2

    def test_parse_carry_distance(self) -> None:
        sessions = self.parser.parse(SAMPLE_DR_CSV, "test.csv")
        shot = sessions[0].shots[0]
        assert shot.carry_yards == Decimal("155.2")

    def test_parse_spin_rate(self) -> None:
        sessions = self.parser.parse(SAMPLE_DR_CSV, "test.csv")
        shot = sessions[0].shots[0]
        assert shot.spin_rate_rpm == 5224

    def test_parse_empty_content(self) -> None:
        assert self.parser.parse("", "empty.csv") == []

    def test_parse_minimal_content(self) -> None:
        assert self.parser.parse("foo\nbar", "min.csv") == []
