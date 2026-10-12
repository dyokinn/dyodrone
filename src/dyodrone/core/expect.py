"""What the vehicle should look like after a command, and whether it does yet.

A flight plan must not fire the next command while the vehicle is still flying
the last one. Before each command the runner snapshots telemetry, calls
:func:`expected_after` to compute the expected end state, then keeps checking
fresh telemetry against it until it matches within a margin.

The margin is ``max(margin × commanded amount, floor)``: 10 % by default, with
small absolute floors so a 2 m move does not need better than GPS noise.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Optional

from dyodrone.core.plan import Step
from dyodrone.core.telemetry import Telemetry

#: Metres per degree of latitude; the drivers use the same constant.
METERS_PER_DEGREE = 111_320

#: Comparisons are inclusive; this absorbs float rounding at the exact margin.
_EPS = 1e-6


@dataclass
class Tolerances:
    """How close counts as "arrived". See the module docstring."""

    margin: float = 0.10
    min_distance_m: float = 0.5
    min_altitude_m: float = 0.5
    min_angle_deg: float = 2.0
    landed_m: float = 0.3


class MissingTelemetry(Exception):
    """A value needed to compute the expectation has not been received yet."""


@dataclass
class CheckResult:
    done: bool
    detail: str


@dataclass
class Expectation:
    """The expected end state of one step: a description and a checker."""

    description: str
    check: Callable[[Telemetry], CheckResult]


def _need(value: Optional[float], what: str) -> float:
    if value is None:
        raise MissingTelemetry(what)
    return value


def angle_error_deg(a: float, b: float) -> float:
    """Smallest absolute difference between two headings, in degrees (0–180)."""
    return abs((a - b + 180.0) % 360.0 - 180.0)


def describe_step(step: Step, tol: Tolerances) -> str:
    """Human description of a step's expectation without needing telemetry (dry runs)."""
    v = step.value
    if step.verb == "takeoff":
        return f"armed and at {v:g} m (±{max(tol.margin * v, tol.min_altitude_m):.1f} m)"
    if step.verb == "altitude":
        return f"at {v:g} m (±{max(tol.margin * v, tol.min_altitude_m):.1f} m)"
    if step.verb in ("forward", "back"):
        direction = "ahead" if step.verb == "forward" else "behind"
        return f"{v:g} m {direction} of the start point (±{max(tol.margin * v, tol.min_distance_m):.1f} m)"
    if step.verb in ("left", "right"):
        return f"heading turned {v:g}° {step.verb} (±{max(tol.margin * v, tol.min_angle_deg):.1f}°)"
    if step.verb == "land":
        return f"on the ground (altitude under max({tol.margin:.0%} of start altitude, {tol.landed_m} m))"
    if step.verb == "wait":
        return f"{v:g} s elapsed"
    return step.command


def expected_after(step: Step, before: Telemetry, tol: Tolerances) -> Expectation:
    """Compute the expected state after *step*, given the telemetry *before* it.

    Raises :class:`MissingTelemetry` if *before* lacks a value the step needs.
    """
    verb, value = step.verb, step.value

    if verb in ("takeoff", "altitude"):
        target = float(value)
        band = max(tol.margin * target, tol.min_altitude_m)

        def check_altitude(now: Telemetry) -> CheckResult:
            if now.rel_alt_m is None:
                return CheckResult(False, "waiting for altitude")
            if verb == "takeoff" and not now.armed:
                return CheckResult(False, f"not armed yet, alt {now.rel_alt_m:.1f}/{target:g} m")
            ok = abs(now.rel_alt_m - target) <= band + _EPS
            return CheckResult(ok, f"alt {now.rel_alt_m:.1f}/{target:g} m (±{band:.1f})")

        return Expectation(describe_step(step, tol), check_altitude)

    if verb in ("forward", "back"):
        lat0 = _need(before.lat, "position")
        lon0 = _need(before.lon, "position")
        yaw = math.radians(_need(before.yaw_deg, "heading"))
        distance = float(value)
        sign = 1 if verb == "forward" else -1
        d_north = sign * distance * math.cos(yaw)
        d_east = sign * distance * math.sin(yaw)
        goal_lat = lat0 + d_north / METERS_PER_DEGREE
        goal_lon = lon0 + d_east / (METERS_PER_DEGREE * math.cos(math.radians(lat0)))
        band = max(tol.margin * distance, tol.min_distance_m)

        def check_position(now: Telemetry) -> CheckResult:
            if not now.has_position:
                return CheckResult(False, "waiting for position")
            north = (goal_lat - now.lat) * METERS_PER_DEGREE
            east = (goal_lon - now.lon) * METERS_PER_DEGREE * math.cos(math.radians(lat0))
            remaining = math.hypot(north, east)
            return CheckResult(remaining <= band + _EPS, f"{remaining:.1f} m to go (of {distance:g}, ±{band:.1f})")

        return Expectation(describe_step(step, tol), check_position)

    if verb in ("left", "right"):
        start = _need(before.yaw_deg, "heading")
        angle = float(value)
        goal = (start + (angle if verb == "right" else -angle)) % 360.0
        band = max(tol.margin * angle, tol.min_angle_deg)

        def check_heading(now: Telemetry) -> CheckResult:
            if now.yaw_deg is None:
                return CheckResult(False, "waiting for heading")
            error = angle_error_deg(now.yaw_deg, goal)
            return CheckResult(error <= band + _EPS, f"yaw {now.yaw_deg:.0f}°, target {goal:.0f}° (±{band:.1f}°)")

        return Expectation(describe_step(step, tol), check_heading)

    if verb == "land":
        start_alt = _need(before.rel_alt_m, "altitude")
        band = max(tol.margin * start_alt, tol.landed_m)

        def check_landed(now: Telemetry) -> CheckResult:
            if now.rel_alt_m is None:
                return CheckResult(False, "waiting for altitude")
            return CheckResult(now.rel_alt_m <= band + _EPS, f"alt {now.rel_alt_m:.1f} m, landed below {band:.1f} m")

        return Expectation(describe_step(step, tol), check_landed)

    raise ValueError(f"No expectation for step {step.command!r}")
