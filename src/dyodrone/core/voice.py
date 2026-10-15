"""Turning spoken words into console commands.

The speech engine only has to produce words; this module slices them into
commands using **exactly the console keywords** (``takeoff``, ``altitude``,
``forward``, ``back``, ``left``, ``right``, ``land``, ``quit``, ``exit``) and
converts spoken numbers to digits::

    "takeoff ten forward twenty five right ninety land"
        -> takeoff 10, forward 25, right 90, land

It is pure Python with no audio or speech dependency.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

#: Keywords that need a number, then the ones that do not.
NUMERIC_KEYWORDS = ("takeoff", "altitude", "forward", "back", "left", "right")
BARE_KEYWORDS = ("land", "quit", "exit")
KEYWORDS = NUMERIC_KEYWORDS + BARE_KEYWORDS

_DIGITS: Dict[str, int] = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4,
    "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
}
_TEENS: Dict[str, int] = {
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
}
_TENS: Dict[str, int] = {
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
    "seventy": 70, "eighty": 80, "ninety": 90,
}
_POINT = "point"
_HUNDRED = "hundred"

#: Every number word the grammar accepts (the speech engine is restricted to these plus the keywords).
NUMBER_WORDS = tuple(list(_DIGITS) + list(_TEENS) + list(_TENS) + [_HUNDRED, _POINT])

#: The complete vocabulary a speech engine should be limited to.
VOCABULARY = KEYWORDS + NUMBER_WORDS


def _parse_int(words: List[str]) -> Optional[int]:
    """Parse a whole number from words (``"two hundred forty five"`` -> 245), or ``None``."""
    if not words:
        return None
    rest = list(words)
    total = 0

    if len(rest) >= 2 and rest[0] in _DIGITS and 1 <= _DIGITS[rest[0]] <= 9 and rest[1] == _HUNDRED:
        total += _DIGITS[rest[0]] * 100
        rest = rest[2:]
    elif rest[0] == _HUNDRED:
        total += 100
        rest = rest[1:]
    elif total == 0 and len(rest) == 1 and rest[0] in _DIGITS:
        return _DIGITS[rest[0]]

    if rest:
        head = rest[0]
        if head in _TENS:
            total += _TENS[head]
            rest = rest[1:]
            if rest and rest[0] in _DIGITS and 1 <= _DIGITS[rest[0]] <= 9:
                total += _DIGITS[rest[0]]
                rest = rest[1:]
        elif head in _TEENS:
            total += _TEENS[head]
            rest = rest[1:]
        elif head in _DIGITS and 1 <= _DIGITS[head] <= 9:
            total += _DIGITS[head]
            rest = rest[1:]
    return total if not rest and (total > 0 or words == ["zero"]) else None


def parse_number(words: List[str]) -> Optional[float]:
    """Convert spoken number words to a float, or ``None`` if they are not a valid number.

    Handles ``zero``–``nineteen``, tens (``twenty five``), ``hundred`` and
    decimals spoken digit by digit (``two point five`` -> 2.5, ``point five`` -> 0.5).
    """
    words = [w for w in words if w]
    if not words:
        return None
    if _POINT in words:
        if words.count(_POINT) != 1:
            return None
        at = words.index(_POINT)
        whole_words, frac_words = words[:at], words[at + 1:]
        if not frac_words or any(w not in _DIGITS for w in frac_words):
            return None
        whole = 0 if not whole_words else _parse_int(whole_words)
        if whole is None:
            return None
        return float(f"{whole}." + "".join(str(_DIGITS[w]) for w in frac_words))
    value = _parse_int(words)
    return None if value is None else float(value)


def _format(value: float) -> str:
    return f"{value:g}"


def slice_commands(text: str) -> Tuple[List[str], List[str]]:
    """Slice a transcript into console commands.

    Returns ``(commands, notes)``: the commands, in spoken order, and short
    notes about anything that was heard but dropped (a keyword without a usable
    number, or a zero value). Words before the first keyword and filler words
    between a keyword and its number are ignored.
    """
    tokens = [t.strip(".,!?;:") for t in (text or "").lower().split()]
    tokens = [t for t in tokens if t]

    commands: List[str] = []
    notes: List[str] = []
    i = 0
    while i < len(tokens):
        word = tokens[i]
        if word not in KEYWORDS:
            i += 1
            continue
        j = i + 1
        while j < len(tokens) and tokens[j] not in KEYWORDS:
            j += 1
        argument = [t for t in tokens[i + 1:j] if t in NUMBER_WORDS]

        if word in BARE_KEYWORDS:
            commands.append(word)
        else:
            value = parse_number(argument) if argument else None
            noun = "a distance" if word in ("forward", "back") else "an angle" if word in ("left", "right") else "an altitude"
            if not argument:
                notes.append(f"heard '{word}' without {noun}")
            elif value is None:
                notes.append(f"could not understand the number in '{word} {' '.join(argument)}'")
            elif value <= 0:
                notes.append(f"'{word} {' '.join(argument)}' must be greater than zero")
            else:
                commands.append(f"{word} {_format(value)}")
        i = j
    return commands, notes
