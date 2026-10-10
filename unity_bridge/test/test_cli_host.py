import sys

import pytest

from unity_bridge import core


def parse(monkeypatch, *argv):
    monkeypatch.setattr(sys, "argv", ["unity-bridge", *argv])
    return core._parse_args()


def test_serial_mode_uses_the_host_in_yaml(monkeypatch):
    assert parse(monkeypatch).host == "0.0.0.0"


def test_gesture_mode_defaults_to_loopback(monkeypatch):
    assert parse(monkeypatch, "--gesture").host == "127.0.0.1"


def test_gesture_mode_rejects_an_explicit_non_loopback_host(monkeypatch):
    with pytest.raises(SystemExit):
        parse(monkeypatch, "--gesture", "--host", "192.168.0.2")
