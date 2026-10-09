import pytest
from diffuser.v1 import diffuser_pb2

from unity_bridge.diffuser import DiffuserController, pins_from_env


def press(channel, duration_ms=200):
    return diffuser_pb2.DiffuserPress(channel=channel, duration_ms=duration_ms)


def test_press_is_sent_to_the_pin_of_the_channel():
    sent = []
    diffuser = DiffuserController(lambda *args: sent.append(args))
    diffuser.press(press(diffuser_pb2.DIFFUSER_CHANNEL_RAMUNE))
    diffuser.press(press(diffuser_pb2.DIFFUSER_CHANNEL_FOREST, 300))
    assert sent == [(8, 200), (9, 300)]


def test_bad_presses_are_rejected():
    sent = []
    diffuser = DiffuserController(lambda *args: sent.append(args))
    for channel, duration_ms in (
        (diffuser_pb2.DIFFUSER_CHANNEL_UNSPECIFIED, 200),
        (3, 200),
        (diffuser_pb2.DIFFUSER_CHANNEL_RAMUNE, 0),
        (diffuser_pb2.DIFFUSER_CHANNEL_RAMUNE, 5001),
    ):
        with pytest.raises(ValueError, match="Invalid diffuser press"):
            diffuser.press(press(channel, duration_ms))
    assert sent == []


def test_pins_come_from_the_env(monkeypatch):
    monkeypatch.delenv("DIFFUSER_PINS", raising=False)
    assert pins_from_env() == (8, 9)
    monkeypatch.setenv("DIFFUSER_PINS", "4,5")
    assert pins_from_env() == (4, 5)


def test_on_off_is_estimated_from_the_number_of_presses():
    diffuser = DiffuserController(clock=lambda: 100.0)
    assert not diffuser.wired
    for _ in range(3):
        diffuser.press(press(diffuser_pb2.DIFFUSER_CHANNEL_RAMUNE))
    ramune, forest = diffuser.channels()
    assert (ramune["on"], ramune["presses"], ramune["last_press_at"]) == (
        True,
        3,
        100.0,
    )
    assert (forest["on"], forest["presses"], forest["last_press_at"]) == (
        False,
        0,
        None,
    )
