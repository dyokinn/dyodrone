"""GCSProxy: UDP forwarding of raw MAVLink frames to a ground station."""

from __future__ import annotations

import socket
from types import SimpleNamespace

import pytest

from dyodrone.core.proxy import GCSProxy


@pytest.fixture
def receiver():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    sock.settimeout(1.0)
    yield sock
    sock.close()


def test_forward_sends_the_exact_bytes(receiver):
    proxy = GCSProxy(receiver.getsockname()[1], "127.0.0.1")
    frame = b"\xfe\x09\x00\x01\x01\x00\x00\x00\x00\x00\x02\x03\x51\x03\x03\xaa\xbb"
    proxy.forward(frame)
    assert receiver.recv(512) == frame
    proxy.stop()


def test_empty_frame_is_not_sent(receiver):
    proxy = GCSProxy(receiver.getsockname()[1], "127.0.0.1")
    receiver.settimeout(0.2)
    proxy.forward(b"")
    with pytest.raises(socket.timeout):
        receiver.recv(512)
    proxy.stop()


def test_send_errors_are_swallowed(receiver):
    proxy = GCSProxy(receiver.getsockname()[1], "127.0.0.1")

    def fail(*_args, **_kwargs):
        raise OSError("network down")

    proxy._gcs_sock.close()
    proxy._gcs_sock = SimpleNamespace(sendto=fail, close=lambda: None)
    proxy.forward(b"abc")  # must not raise
    proxy.stop()


@pytest.mark.parametrize("host", ["255.255.255.255", "<broadcast>"])
def test_broadcast_hosts_enable_so_broadcast(host):
    proxy = GCSProxy(14550, host)
    assert proxy._gcs_sock.getsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST) != 0
    proxy.stop()


def test_unicast_host_leaves_broadcast_off():
    proxy = GCSProxy(14550, "127.0.0.1")
    assert proxy._gcs_sock.getsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST) == 0
    proxy.stop()


def test_properties_expose_target():
    proxy = GCSProxy(5600, "192.168.1.50")
    assert (proxy.gcs_port, proxy.gcs_host) == (5600, "192.168.1.50")
    proxy.stop()


class _FakeVehicle:
    def __init__(self):
        self.listeners = []

    def add_message_listener(self, name, fn):
        self.listeners.append((name, fn))

    def remove_message_listener(self, name, fn):
        self.listeners.remove((name, fn))


def test_start_registers_wildcard_listener_that_forwards(receiver):
    vehicle = _FakeVehicle()
    proxy = GCSProxy(receiver.getsockname()[1], "127.0.0.1")
    proxy.start(vehicle)
    assert [n for n, _ in vehicle.listeners] == ["*"]

    listener = vehicle.listeners[0][1]
    listener(vehicle, "HEARTBEAT", SimpleNamespace(get_msgbuf=lambda: b"frame"))
    assert receiver.recv(512) == b"frame"
    listener(vehicle, "X", SimpleNamespace(get_msgbuf=lambda: b""))  # empty buffers are skipped

    proxy.stop()
    assert vehicle.listeners == []


def test_stop_is_safe_without_start():
    GCSProxy(14550, "127.0.0.1").stop()
