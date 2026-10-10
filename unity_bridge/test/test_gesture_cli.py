import pytest

from unity_bridge import core, gesture_probe


def test_gesture_mode_is_loopback_only(monkeypatch):
    monkeypatch.setattr("sys.argv", ["unity-bridge", "--gesture"])
    args = core._parse_args(core.load_settings())
    assert args.gesture
    assert args.host == "127.0.0.1"
    monkeypatch.setattr("sys.argv", ["unity-bridge", "--gesture", "--host", "10.0.0.1"])
    with pytest.raises(SystemExit):
        core._parse_args(core.load_settings())


def _settings(**changes):
    return core.load_settings().model_copy(update=changes)


def test_relay_timing_comes_from_the_settings():
    relay = core.bridge_relay_from_settings(
        _settings(gesture_state_interval=0.05, gesture_max_pending=8)
    )
    assert relay.state_interval == 0.05
    assert relay.outbox.max_pending == 8
    with pytest.raises(ValueError, match="state interval"):
        core.bridge_relay_from_settings(_settings(gesture_state_interval=0.5))


def test_probe_rejects_text_payload():
    with pytest.raises(TypeError):
        gesture_probe.decode_payload("{}")


def test_fan_mode_serves_loopback_without_detection(monkeypatch):
    monkeypatch.setattr("sys.argv", ["unity-bridge", "--fan"])
    args = core._parse_args(core.load_settings())
    assert args.fan
    assert args.gesture
    assert args.host == "127.0.0.1"
