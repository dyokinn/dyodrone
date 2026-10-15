"""Expected end state after each command and the 10 % margin."""

from __future__ import annotations

import math

import pytest

from dyodrone.core.expect import (
    METERS_PER_DEGREE,
    MissingTelemetry,
    Tolerances,
    angle_error_deg,
    describe_step,
    expected_after,
)
from dyodrone.core.plan import Step
from dyodrone.core.telemetry import Telemetry

LAT, LON = -35.363261, 149.165230


def at(alt=0.0, yaw=0.0, armed=True, lat=LAT, lon=LON):
    return Telemetry(lat=lat, lon=lon, rel_alt_m=alt, yaw_deg=yaw, armed=armed, mode="GUIDED")


def north(meters, lat=LAT):
    return lat + meters / METERS_PER_DEGREE


TOL = Tolerances()


# -- altitude --------------------------------------------------------------


@pytest.mark.parametrize("alt, done", [(10.0, True), (9.0, True), (11.0, True), (8.9, False), (11.1, False), (0.0, False)])
def test_takeoff_is_done_within_ten_percent_of_the_target(alt, done):
    exp = expected_after(Step(1, "takeoff", 10), at(0, armed=False), TOL)
    assert exp.check(at(alt)).done is done


def test_takeoff_needs_the_motors_armed():
    exp = expected_after(Step(1, "takeoff", 10), at(0, armed=False), TOL)
    result = exp.check(at(10, armed=False))
    assert not result.done and "not armed" in result.detail


def test_altitude_floor_applies_to_small_targets():
    exp = expected_after(Step(1, "altitude", 2), at(10), TOL)  # 10% = 0.2 m, floor 0.5 m
    assert exp.check(at(2.4)).done and not exp.check(at(2.6)).done


def test_altitude_does_not_require_arming_state():
    exp = expected_after(Step(1, "altitude", 20), at(10), TOL)
    assert exp.check(at(20, armed=False)).done


def test_altitude_unknown_is_not_done():
    exp = expected_after(Step(1, "altitude", 20), at(10), TOL)
    assert not exp.check(Telemetry()).done


# -- position --------------------------------------------------------------


@pytest.mark.parametrize("moved, done", [(20.0, True), (18.0, True), (22.0, True), (17.5, False), (23.0, False), (0.0, False)])
def test_forward_north_is_done_within_ten_percent_of_the_distance(moved, done):
    exp = expected_after(Step(1, "forward", 20), at(10, yaw=0), TOL)
    assert exp.check(at(10, lat=north(moved))).done is done


def test_forward_east_moves_longitude():
    exp = expected_after(Step(1, "forward", 20), at(10, yaw=90), TOL)
    lon_20m = LON + 20 / (METERS_PER_DEGREE * math.cos(math.radians(LAT)))
    assert exp.check(at(10, lon=lon_20m)).done
    assert not exp.check(at(10, lat=north(20))).done  # wrong direction


def test_back_goes_the_opposite_way():
    exp = expected_after(Step(1, "back", 20), at(10, yaw=0), TOL)
    assert exp.check(at(10, lat=north(-20))).done
    assert not exp.check(at(10, lat=north(20))).done


def test_small_moves_use_the_distance_floor():
    exp = expected_after(Step(1, "forward", 2), at(10, yaw=0), TOL)  # 10% = 0.2 m, floor 0.5 m
    assert exp.check(at(10, lat=north(1.6))).done and not exp.check(at(10, lat=north(1.4))).done


def test_forward_needs_position_and_heading_before():
    with pytest.raises(MissingTelemetry):
        expected_after(Step(1, "forward", 5), Telemetry(yaw_deg=0), TOL)
    with pytest.raises(MissingTelemetry):
        expected_after(Step(1, "forward", 5), Telemetry(lat=LAT, lon=LON), TOL)


def test_position_unknown_now_is_not_done():
    exp = expected_after(Step(1, "forward", 5), at(10), TOL)
    assert not exp.check(Telemetry(rel_alt_m=10, yaw_deg=0)).done


# -- heading ---------------------------------------------------------------


@pytest.mark.parametrize("yaw, done", [(90, True), (82, True), (98, True), (80, False), (100, False), (0, False)])
def test_right_90_is_done_within_ten_percent(yaw, done):
    exp = expected_after(Step(1, "right", 90), at(10, yaw=0), TOL)
    assert exp.check(at(10, yaw=yaw)).done is done


def test_left_turns_counter_clockwise():
    exp = expected_after(Step(1, "left", 30), at(10, yaw=10), TOL)  # 10 - 30 = 340
    assert exp.check(at(10, yaw=340)).done and not exp.check(at(10, yaw=40)).done


def test_heading_wraps_around_north():
    exp = expected_after(Step(1, "right", 20), at(10, yaw=350), TOL)  # goal 10, band max(2, 2) = 2
    assert exp.check(at(10, yaw=8)).done and exp.check(at(10, yaw=12)).done
    assert not exp.check(at(10, yaw=5)).done


@pytest.mark.parametrize("a, b, err", [(10, 350, 20), (350, 10, 20), (0, 180, 180), (90, 90, 0), (1, 359, 2)])
def test_angle_error_is_the_short_way_round(a, b, err):
    assert angle_error_deg(a, b) == pytest.approx(err)


# -- landing ---------------------------------------------------------------


@pytest.mark.parametrize("alt, done", [(0.0, True), (0.9, True), (1.1, False), (5.0, False)])
def test_land_from_ten_metres_is_done_below_one_metre(alt, done):
    exp = expected_after(Step(1, "land"), at(10), TOL)
    assert exp.check(at(alt)).done is done


def test_land_from_low_altitude_uses_the_landed_floor():
    exp = expected_after(Step(1, "land"), at(2), TOL)  # 10% = 0.2 m, floor 0.3 m
    assert exp.check(at(0.25)).done and not exp.check(at(0.4)).done


def test_land_needs_the_starting_altitude():
    with pytest.raises(MissingTelemetry):
        expected_after(Step(1, "land"), Telemetry(), TOL)


# -- configuration and descriptions ---------------------------------------


def test_margin_is_configurable():
    loose = Tolerances(margin=0.5)
    exp = expected_after(Step(1, "takeoff", 10), at(0, armed=False), loose)
    assert exp.check(at(5.5)).done and not exp.check(at(4.5)).done


def test_wait_has_no_telemetry_expectation():
    with pytest.raises(ValueError):
        expected_after(Step(1, "wait", 3), at(), TOL)


@pytest.mark.parametrize(
    "step, text",
    [
        (Step(1, "takeoff", 10), "armed and at 10 m (±1.0 m)"),
        (Step(1, "forward", 20), "20 m ahead of the start point (±2.0 m)"),
        (Step(1, "back", 5), "5 m behind of the start point (±0.5 m)"),
        (Step(1, "right", 90), "heading turned 90° right (±9.0°)"),
        (Step(1, "wait", 3), "3 s elapsed"),
    ],
)
def test_describe_step_without_telemetry(step, text):
    assert describe_step(step, TOL) == text
