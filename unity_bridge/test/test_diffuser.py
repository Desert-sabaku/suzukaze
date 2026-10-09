import pytest
from diffuser.v1 import diffuser_pb2

from unity_bridge.diffuser import DiffuserController
from unity_bridge.settings import load_settings


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


def test_pins_come_from_the_settings():
    assert load_settings().diffuser_pins.ordered() == (8, 9)
