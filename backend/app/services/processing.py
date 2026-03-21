from __future__ import annotations

"""
Shot processing pipeline — trimming, theoretical carry, and computed fields.

This runs after CSV parsing and shot insertion. It applies the bottom-N%
carry trim and computes theoretical carry distances using physics simulation.
"""

import math
from collections import defaultdict
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.session import Session
from app.models.shot import Shot


async def process_session_shots(
    db: AsyncSession,
    session: Session,
    trim_pct: float = 0.20,
    elevation_ft: int = 0,
) -> None:
    """
    Process all shots in a session:
      1. Compute theoretical carry for each shot
      2. Apply bottom-N% trim by carry distance

    This modifies shots in-place within the current transaction.
    Caller is responsible for committing.

    Args:
        db: Active database session
        session: The session whose shots need processing
        trim_pct: Bottom percentage to trim (default 20%)
        elevation_ft: Elevation for air density adjustment in physics sim
    """
    result = await db.execute(
        select(Shot)
        .where(Shot.session_id == session.id)
        .order_by(Shot.shot_index)
    )
    shots = list(result.scalars().all())
    if not shots:
        return

    # Step 1: Compute theoretical carry for each shot
    for shot in shots:
        shot.theoretical_carry = _theoretical_carry(
            ball_speed_mph=shot.ball_speed_mph,
            launch_angle_deg=shot.launch_angle_deg,
            spin_rate_rpm=shot.spin_rate_rpm,
            elevation_ft=elevation_ft,
        )

    # Step 2: Apply bottom-N% trim, grouped by club
    clubs: dict[str, list[Shot]] = defaultdict(list)
    for shot in shots:
        clubs[shot.club_name].append(shot)

    for club_shots in clubs.values():
        _apply_trim(club_shots, trim_pct)

    # Update processed timestamp
    from sqlalchemy import func
    session.processed_at = func.now()


def _apply_trim(shots: list[Shot], trim_pct: float) -> None:
    """
    Mark the bottom N% of shots (by carry distance) as filtered out.

    Shots with valid carry are sorted; those below the cutoff percentile
    get is_filtered = False. Shots with no carry data are also marked False.
    """
    # Separate shots with valid carry from those without
    with_carry = [
        s for s in shots
        if s.carry_yards is not None and s.carry_yards > 0
    ]

    if not with_carry:
        for s in shots:
            s.is_filtered = False
        return

    # Sort by carry ascending
    with_carry.sort(key=lambda s: s.carry_yards)  # type: ignore[arg-type]

    # Find the cutoff value at the trim percentile
    cutoff_idx = int(len(with_carry) * trim_pct)
    cutoff_value = with_carry[cutoff_idx].carry_yards if cutoff_idx < len(with_carry) else Decimal("0")

    # Mark each shot
    for shot in shots:
        if shot.carry_yards is None or shot.carry_yards <= 0:
            shot.is_filtered = False
        else:
            shot.is_filtered = shot.carry_yards >= cutoff_value


def _theoretical_carry(
    ball_speed_mph: Decimal | None,
    launch_angle_deg: Decimal | None,
    spin_rate_rpm: int | None,
    elevation_ft: int = 0,
) -> Decimal | None:
    """
    Physics-based carry distance estimation.

    Uses a simplified trajectory simulation accounting for:
    - Drag force (quadratic)
    - Lift force (from backspin via Magnus effect)
    - Air density adjusted for elevation
    - Gravity

    This matches the PWA's theoreticalCarry() function exactly.

    Args:
        ball_speed_mph: Initial ball speed in mph
        launch_angle_deg: Launch angle in degrees
        spin_rate_rpm: Total spin rate in RPM
        elevation_ft: Course/range elevation in feet

    Returns:
        Estimated carry distance in yards, or None if inputs are invalid
    """
    if not ball_speed_mph or ball_speed_mph <= 0:
        return None
    if not launch_angle_deg or launch_angle_deg <= 0:
        return None
    if not spin_rate_rpm or spin_rate_rpm <= 0:
        return None

    bs = float(ball_speed_mph)
    la = float(launch_angle_deg)
    sr = float(spin_rate_rpm)

    # Air density adjustment for elevation
    rho = 1.225 * math.exp(-elevation_ft * 0.3048 / 8500)
    dr = rho / 1.225

    # Convert to SI units
    v = bs * 0.44704  # mph to m/s
    theta = math.radians(la)

    vx = v * math.cos(theta)
    vy = v * math.sin(theta)

    # Golf ball physical constants
    mass = 0.04593  # kg
    radius = 0.02135  # m
    area = math.pi * radius * radius

    # Aerodynamic coefficients (adjusted for air density)
    cd = 0.225 * dr  # Drag coefficient
    cl = 0.00015 * sr / 1000 * dr  # Lift coefficient (spin-dependent)

    # Trajectory simulation (Euler method)
    x = 0.0
    y = 0.0
    dt = 0.01

    t = 0.0
    while t < 15.0:
        speed = math.sqrt(vx * vx + vy * vy)
        if speed == 0:
            break

        drag = 0.5 * rho * area * cd * speed
        lift = 0.5 * rho * area * cl * speed

        vx += (-drag * vx / mass) * dt
        vy += (-9.81 - drag * vy / mass + lift * speed / mass) * dt

        x += vx * dt
        y += vy * dt

        if y < 0 and t > 0.1:
            break

        t += dt

    # Convert meters to yards
    carry_yards = x / 0.9144
    return Decimal(str(round(carry_yards, 1)))
