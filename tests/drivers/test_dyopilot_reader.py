"""MAVLinkReader: the background thread that keeps a pymavlink connection fresh."""

from __future__ import annotations

import pytest
from fakes import wait_for
from marks import needs_pymavlink

pytestmark = [needs_pymavlink, pytest.mark.dyopilot]

from dyodrone.drivers.dyopilot_reader import MAVLinkReader  # noqa: E402


class Msg:
    def __init__(self, kind, buf=b""):
        self._kind, self._buf = kind, buf

    def get_type(self):
        return self._kind

    def get_msgbuf(self):
        return self._buf


class Master:
    def __init__(self, items):
        self.items = list(items)
        self.reads = 0

    def recv_msg(self):
        self.reads += 1
        if not self.items:
            return None
        item = self.items.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def test_frames_are_forwarded_to_the_sink():
    frames = []
    reader = MAVLinkReader(Master([Msg("HEARTBEAT", b"a"), Msg("ATTITUDE", b"b")]), on_frame=frames.append)
    reader.start()
    assert wait_for(lambda: len(frames) == 2)
    reader.stop()
    assert frames == [b"a", b"b"]


def test_corrupt_frames_are_not_forwarded():
    frames = []
    reader = MAVLinkReader(Master([Msg("BAD_DATA", b"junk"), Msg("HEARTBEAT", b"ok")]), on_frame=frames.append)
    reader.start()
    assert wait_for(lambda: frames == [b"ok"])
    reader.stop()


def test_reader_works_without_a_sink():
    master = Master([Msg("HEARTBEAT", b"a")])
    reader = MAVLinkReader(master)
    reader.start()
    assert wait_for(lambda: master.reads >= 2)
    reader.stop()


def test_start_is_idempotent_and_stop_joins():
    reader = MAVLinkReader(Master([]))
    reader.start()
    thread = reader._thread
    reader.start()
    assert reader._thread is thread
    reader.stop()
    assert not thread.is_alive()
    reader.stop()  # safe to call again


def test_recv_exception_ends_the_thread():
    reader = MAVLinkReader(Master([RuntimeError("socket closed")]))
    reader.start()
    thread = reader._thread
    assert wait_for(lambda: not thread.is_alive())
    reader.stop()
