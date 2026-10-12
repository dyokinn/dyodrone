"""Flight-plan text format."""

from __future__ import annotations

import pytest

from dyodrone.core.plan import PLAN_VERBS, PlanError, Step, format_plan, parse_plan


def test_parses_the_documented_example():
    steps = parse_plan("# square\ntakeoff 10\nforward 20\nright 90\nwait 5\nland\n")
    assert [s.command for s in steps] == ["takeoff 10", "forward 20", "right 90", "wait 5", "land"]
    assert [s.line for s in steps] == [2, 3, 4, 5, 6]


def test_comments_blank_lines_and_trailing_comments_are_ignored():
    steps = parse_plan("\n   \n# only a comment\ntakeoff 5   # up\n\n   land\t# down\n")
    assert [s.command for s in steps] == ["takeoff 5", "land"]


def test_verbs_are_case_insensitive_and_values_normalised():
    steps = parse_plan("TAKEOFF 12.50\nForward 5.0\nLAND")
    assert [s.command for s in steps] == ["takeoff 12.5", "forward 5", "land"]
    assert steps[0] == Step(1, "takeoff", 12.5)


def test_decimal_values_and_windows_line_endings():
    steps = parse_plan("takeoff 2.5\r\nright 22.5\r\n")
    assert [s.value for s in steps] == [2.5, 22.5]


@pytest.mark.parametrize(
    "text, message",
    [
        ("takeoff", "needs one value"),
        ("takeoff 1 2", "needs one value"),
        ("takeoff abc", "is not a number"),
        ("forward -3", "greater than 0"),
        ("forward 0", "greater than 0"),
        ("forward nan", "greater than 0"),
        ("forward inf", "greater than 0"),
        ("land now", "takes no argument"),
        ("flip 3", "unknown command 'flip'"),
        ("quit", "unknown command 'quit'"),
        ("info", "unknown command 'info'"),
    ],
)
def test_invalid_lines_are_reported_with_their_line_number(text, message):
    with pytest.raises(PlanError) as info:
        parse_plan("takeoff 5\n" + text)
    assert info.value.errors[0][0] == 2
    assert message in info.value.errors[0][1]


def test_all_errors_are_collected_not_just_the_first():
    with pytest.raises(PlanError) as info:
        parse_plan("takeoff\nflip\nforward x\nland")
    assert [line for line, _ in info.value.errors] == [1, 2, 3]
    assert "line 1" in str(info.value) and "line 3" in str(info.value)


@pytest.mark.parametrize("text", ["", "   \n\n", "# nothing here\n"])
def test_a_plan_needs_at_least_one_step(text):
    with pytest.raises(PlanError, match="no steps"):
        parse_plan(text)


def test_none_is_treated_as_empty():
    with pytest.raises(PlanError):
        parse_plan(None)


def test_plan_verbs_match_the_console_plus_wait():
    assert set(PLAN_VERBS) == {"takeoff", "altitude", "forward", "back", "left", "right", "land", "wait"}


def test_format_plan_round_trips():
    commands = ["takeoff 10", "forward 5", "land"]
    text = format_plan(commands, header="recorded")
    assert text.startswith("# recorded\n")
    assert [s.command for s in parse_plan(text)] == commands


def test_format_plan_skips_blank_commands():
    assert format_plan(["land", "  ", ""]) == "land\n"
