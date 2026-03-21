from __future__ import annotations

"""
Base parser interface and canonical data structures.

Every parser normalizes its source format into ParsedShot and ParsedSession.
This is the single source of truth for what "a shot" looks like in the system,
regardless of which launch monitor produced it.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal


@dataclass
class ParsedShot:
    """
    A single parsed shot — the canonical intermediate representation.

    All values are optional because different monitors measure different metrics.
    Sign conventions are standardized:
      - Negative = LEFT (offline, face angle, club path, launch direction, spin axis)
      - Positive = RIGHT

    Each parser is responsible for converting its source format to these conventions.
    """

    club_name: str

    # Ball data
    ball_speed_mph: Decimal | None = None
    launch_angle_deg: Decimal | None = None
    launch_direction_deg: Decimal | None = None
    spin_rate_rpm: int | None = None
    spin_axis_deg: Decimal | None = None
    back_spin_rpm: int | None = None
    side_spin_rpm: int | None = None

    # Club data
    club_speed_mph: Decimal | None = None
    smash_factor: Decimal | None = None
    attack_angle_deg: Decimal | None = None
    club_path_deg: Decimal | None = None
    face_angle_deg: Decimal | None = None
    face_to_path_deg: Decimal | None = None
    dynamic_loft_deg: Decimal | None = None
    closure_rate_dps: Decimal | None = None

    # Result data
    carry_yards: Decimal | None = None
    total_yards: Decimal | None = None
    offline_yards: Decimal | None = None
    apex_feet: Decimal | None = None
    landing_angle_deg: Decimal | None = None
    hang_time_sec: Decimal | None = None
    curve_yards: Decimal | None = None


@dataclass
class ParsedSession:
    """
    A parsed session — a collection of shots from a single practice session.

    One CSV file may produce multiple ParsedSessions (e.g., Bushnell
    DrivingRange format groups shots by date within a single file).
    """

    source_file: str
    source_format: str
    session_date: date
    shots: list[ParsedShot] = field(default_factory=list)
    ball_type: str | None = None


class BaseParser(ABC):
    """
    Abstract base for all CSV parsers.

    Subclasses must implement:
      - detect(content, filename) → bool
      - parse(content, filename) → list[ParsedSession]
    """

    @abstractmethod
    def detect(self, content: str, filename: str = "") -> bool:
        """
        Does this content match this parser's expected format?

        Should be fast and non-destructive — examine only the first
        few lines or known header patterns. Return True if confident.
        """

    @abstractmethod
    def parse(self, content: str, filename: str = "") -> list[ParsedSession]:
        """
        Parse the content into sessions and shots.

        Assumes detect() already returned True. Should handle edge cases
        gracefully (missing columns, empty rows, malformed numbers) and
        skip unparseable rows rather than crashing.
        """
