"""Flight-plan text format: one CLI command per line.

::

    # comments start with '#', blank lines are ignored
    takeoff 10
    forward 20
    right 90          # trailing comments are fine too
    wait 5            # optional pause, in seconds
    land

Steps are the same commands the console accepts (``takeoff``, ``altitude``,
``forward``, ``back``, ``left``, ``right``, ``land``) plus ``wait``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional, Tuple

#: Verbs that need one positive number, with the unit used in error messages.
NUMERIC_VERBS = {
    "takeoff": "altitude in meters",
    "altitude": "altitude in meters",
    "forward": "distance in meters",
    "back": "distance in meters",
    "left": "angle in degrees",
    "right": "angle in degrees",
    "wait": "seconds",
}

#: Verbs that take no argument.
BARE_VERBS = {"land"}

PLAN_VERBS = tuple(sorted(set(NUMERIC_VERBS) | BARE_VERBS))

#: Verbs the console records into a plan (everything but ``wait``).
RECORDABLE_VERBS = frozenset(set(NUMERIC_VERBS) - {"wait"} | BARE_VERBS)


@dataclass(frozen=True)
class Step:
    """One validated plan step."""

    line: int  # 1-based line number in the source text (0 if not from text)
    verb: str
    value: Optional[float] = None

    @property
    def command(self) -> str:
        """The console command for this step, e.g. ``"forward 5"``."""
        return self.verb if self.value is None else f"{self.verb} {self.value:g}"


class PlanError(ValueError):
    """The plan text is invalid; ``errors`` lists every problem as ``(line, message)``."""

    def __init__(self, errors: List[Tuple[int, str]]) -> None:
        self.errors = errors
        super().__init__("; ".join(f"line {n}: {m}" if n else m for n, m in errors))


def parse_plan(text: str) -> List[Step]:
    """Parse plan *text* into steps, or raise :class:`PlanError` listing every problem."""
    steps: List[Step] = []
    errors: List[Tuple[int, str]] = []

    for number, raw in enumerate((text or "").splitlines(), start=1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        verb = parts[0].lower()

        if verb in BARE_VERBS:
            if len(parts) != 1:
                errors.append((number, f"'{verb}' takes no argument"))
                continue
            steps.append(Step(number, verb))
        elif verb in NUMERIC_VERBS:
            unit = NUMERIC_VERBS[verb]
            if len(parts) != 2:
                errors.append((number, f"'{verb}' needs one value ({unit})"))
                continue
            try:
                value = float(parts[1])
            except ValueError:
                errors.append((number, f"'{parts[1]}' is not a number ({verb}: {unit})"))
                continue
            if not value > 0 or value != value or value == float("inf"):
                errors.append((number, f"'{verb}' needs a value greater than 0 ({unit})"))
                continue
            steps.append(Step(number, verb, value))
        else:
            errors.append((number, f"unknown command '{parts[0]}' (expected one of: {', '.join(PLAN_VERBS)})"))

    if not errors and not steps:
        errors.append((0, "the plan has no steps"))
    if errors:
        raise PlanError(errors)
    return steps


def format_plan(commands: Iterable[str], header: Optional[str] = None) -> str:
    """Render command lines as plan text (used when recording a session)."""
    lines = [f"# {header}"] if header else []
    lines.extend(c.strip() for c in commands if c.strip())
    return "\n".join(lines) + "\n"
