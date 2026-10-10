import pytest

from unity_bridge import core, gesture_probe


def test_gesture_mode_is_loopback_only(monkeypatch):
    monkeypatch.setattr("sys.argv", ["unity-bridge", "--gesture"])
    args = core._parse_args()
    assert args.gesture
    assert args.host == "127.0.0.1"
    monkeypatch.setattr("sys.argv", ["unity-bridge", "--gesture", "--host", "10.0.0.1"])
    with pytest.raises(SystemExit):
        core._parse_args()


def _use_settings(monkeypatch, **changes):
    settings = core.load_settings().model_copy(update=changes)
    monkeypatch.setattr(core, "load_settings", lambda: settings)


def test_relay_timing_comes_from_the_settings(monkeypatch):
    _use_settings(monkeypatch, gesture_state_interval=0.05, gesture_max_pending=8)
    relay = core.bridge_relay_from_env()
    assert relay.state_interval == 0.05
    assert relay.outbox.max_pending == 8
    _use_settings(monkeypatch, gesture_state_interval=0.5)
    with pytest.raises(ValueError, match="state interval"):
        core.bridge_relay_from_env()


def test_probe_rejects_text_payload():
    with pytest.raises(TypeError):
        gesture_probe.decode_payload("{}")


def test_fan_mode_serves_loopback_without_detection(monkeypatch):
    monkeypatch.setattr("sys.argv", ["unity-bridge", "--fan"])
    args = core._parse_args()
    assert args.fan
    assert args.gesture
    assert args.host == "127.0.0.1"
