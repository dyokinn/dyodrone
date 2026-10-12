"""Where a vehicle connection comes from.

A *target* is independent of the driver library: it only knows how to produce a
connection string and how to tear down whatever it started. ``SitlTarget``
launches the bundled ArduCopter simulator; ``ExternalTarget`` uses a string you
supply (a Pixhawk on serial, a TCP/UDP endpoint, an already-running simulator).
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Optional

LOG = logging.getLogger(__name__)

#: Target names accepted by :func:`make_target` and the front ends.
TARGETS = ("sitl", "pixhawk")


class Target(ABC):
    """Supplies a MAVLink connection string and cleans up after it."""

    name: str

    @abstractmethod
    def acquire(self) -> str:
        """Return the connection string, starting anything needed for it."""

    @abstractmethod
    def release(self) -> None:
        """Stop whatever :meth:`acquire` started. Safe to call more than once."""


class SitlTarget(Target):
    """Launches the ArduCopter 3.3 simulator via ``dronekit_sitl``.

    ``dronekit_sitl``'s runtime code never imports ``dronekit``, so this works
    on current Python even though DroneKit itself does not.
    """

    name = "sitl"

    def __init__(self) -> None:
        self._sitl: Optional[Any] = None

    def acquire(self) -> str:
        if self._sitl is None:
            import dronekit_sitl

            LOG.info("Starting SITL simulator...")
            self._sitl = dronekit_sitl.start_default()
        return self._sitl.connection_string()

    def release(self) -> None:
        if self._sitl is not None:
            LOG.info("Stopping SITL simulator.")
            sitl, self._sitl = self._sitl, None
            sitl.stop()


class ExternalTarget(Target):
    """Uses a connection string you provide, e.g. ``/dev/ttyUSB0`` or ``tcp:host:5760``."""

    name = "pixhawk"

    def __init__(self, connection: str) -> None:
        if not connection:
            raise ValueError("A connection string is required for the Pixhawk target.")
        self.connection = connection

    def acquire(self) -> str:
        return self.connection

    def release(self) -> None:
        """Nothing to stop: the vehicle or simulator is not ours."""


def make_target(name: str, connection: Optional[str] = None) -> Target:
    """Build the target called *name* (one of :data:`TARGETS`)."""
    if name == "sitl":
        return SitlTarget()
    if name == "pixhawk":
        return ExternalTarget(connection or "")
    raise ValueError(f"Unknown target: {name!r} (expected one of {', '.join(TARGETS)})")
