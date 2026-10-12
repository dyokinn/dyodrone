"""Speech words -> console commands."""

from __future__ import annotations

import pytest

from dyodrone.core.commands import handle_command
from dyodrone.core.voice import KEYWORDS, VOCABULARY, parse_number, slice_commands
from fakes import FakeController


@pytest.mark.parametrize(
    "words, value",
    [
        ("zero", 0), ("one", 1), ("nine", 9), ("ten", 10), ("eleven", 11), ("nineteen", 19),
        ("twenty", 20), ("twenty five", 25), ("ninety nine", 99), ("forty", 40),
        ("hundred", 100), ("one hundred", 100), ("two hundred", 200), ("one hundred five", 105),
        ("one hundred twenty five", 125), ("nine hundred ninety nine", 999), ("two hundred ten", 210),
        ("two point five", 2.5), ("point five", 0.5), ("ten point five", 10.5),
        ("twenty point two five", 20.25), ("zero point five", 0.5),
    ],
)
def test_spoken_numbers(words, value):
    assert parse_number(words.split()) == pytest.approx(value)


@pytest.mark.parametrize(
    "words",
    ["", "twenty twenty", "five five", "ten ten", "hundred hundred", "point", "two point", "two point point five",
     "one point ten", "twenty zero", "banana", "twenty hundred five five"],
)
def test_invalid_numbers_are_rejected(words):
    assert parse_number(words.split()) is None


def test_the_keywords_are_exactly_the_cli_commands():
    assert set(KEYWORDS) == {"takeoff", "altitude", "forward", "back", "left", "right", "land", "quit", "exit"}
    assert set(KEYWORDS) <= set(VOCABULARY)


def test_a_multi_command_utterance_is_sliced():
    commands, notes = slice_commands("takeoff ten forward twenty five right ninety land")
    assert commands == ["takeoff 10", "forward 25", "right 90", "land"]
    assert notes == []


def test_decimals_and_hundreds():
    assert slice_commands("altitude one hundred twenty forward two point five")[0] == ["altitude 120", "forward 2.5"]


def test_case_and_punctuation_do_not_matter():
    assert slice_commands("Takeoff, TEN. Land!")[0] == ["takeoff 10", "land"]


def test_filler_words_and_leading_noise_are_ignored():
    commands, _ = slice_commands("uh okay so takeoff um ten and then forward five please")
    assert commands == ["takeoff 10", "forward 5"]


def test_bare_keywords_ignore_trailing_numbers():
    assert slice_commands("land five")[0] == ["land"]


@pytest.mark.parametrize("word", ["quit", "exit"])
def test_quit_and_exit_are_commands(word):
    assert slice_commands(word)[0] == [word]


@pytest.mark.parametrize(
    "text, note",
    [
        ("forward", "heard 'forward' without a distance"),
        ("right", "heard 'right' without an angle"),
        ("takeoff", "heard 'takeoff' without an altitude"),
        ("forward twenty twenty", "could not understand the number"),
        ("back zero", "must be greater than zero"),
    ],
)
def test_incomplete_commands_are_dropped_with_a_note(text, note):
    commands, notes = slice_commands(text)
    assert commands == [] and note in notes[0]


def test_a_bad_command_does_not_swallow_its_neighbours():
    commands, notes = slice_commands("takeoff ten forward right ninety land")
    assert commands == ["takeoff 10", "right 90", "land"] and len(notes) == 1


@pytest.mark.parametrize("text", ["", "   ", "hello there", "ten twenty"])
def test_no_keywords_means_no_commands(text):
    assert slice_commands(text) == ([], [])


def test_none_is_empty():
    assert slice_commands(None) == ([], [])


def test_near_miss_keywords_are_not_accepted():
    assert slice_commands("take off ten forwards five lands")[0] == []


def test_sliced_commands_are_valid_console_commands():
    ctrl = FakeController()
    for command in slice_commands("takeoff ten forward five back two left ninety right fortyfive altitude fifteen land")[0]:
        assert handle_command(command, ctrl)[1] and "Unknown" not in handle_command(command, ctrl)[1]
