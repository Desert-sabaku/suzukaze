import pytest

from unity_bridge import core, gesture_probe


def test_gesture_mode_is_loopback_only(monkeypatch):
    monkeypatch.setattr(core, "load_dotenv", lambda: None)
    monkeypatch.setattr("sys.argv", ["unity-bridge", "--gesture"])
    args = core._parse_args()
    assert args.gesture
    assert args.host == "127.0.0.1"
    monkeypatch.setattr("sys.argv", ["unity-bridge", "--gesture", "--host", "10.0.0.1"])
    with pytest.raises(SystemExit):
        core._parse_args()


def test_relay_timing_comes_from_environment(monkeypatch):
    monkeypatch.setenv("GESTURE_STATE_INTERVAL", "0.05")
    monkeypatch.setenv("GESTURE_MAX_PENDING", "8")
    relay = core.bridge_relay_from_env()
    assert relay.state_interval == 0.05
    assert relay.outbox.max_pending == 8
    monkeypatch.setenv("GESTURE_STATE_INTERVAL", "0.5")
    with pytest.raises(ValueError, match="state interval"):
        core.bridge_relay_from_env()


def test_probe_rejects_text_payload():
    with pytest.raises(TypeError):
        gesture_probe.decode_payload("{}")


def test_fan_mode_serves_loopback_without_detection(monkeypatch):
    monkeypatch.setattr(core, "load_dotenv", lambda: None)
    monkeypatch.setattr("sys.argv", ["unity-bridge", "--fan"])
    args = core._parse_args()
    assert args.fan
    assert args.gesture
    assert args.host == "127.0.0.1"
