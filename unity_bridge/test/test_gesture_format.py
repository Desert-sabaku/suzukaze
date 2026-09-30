from unittest.mock import AsyncMock

import pytest

from unity_bridge import core, gesture_probe


@pytest.mark.parametrize(
    "env, cli, expected",
    [
        (None, [], "json"),
        ("protobuf", [], "protobuf"),
        ("protobuf", ["json"], "json"),
    ],
)
def test_selectors(monkeypatch, env, cli, expected):
    monkeypatch.delenv("GESTURE_DELIVERY_FORMAT", raising=False)
    if env:
        monkeypatch.setenv("GESTURE_DELIVERY_FORMAT", env)
    monkeypatch.setattr(core, "load_dotenv", lambda: None)
    monkeypatch.setattr(
        "sys.argv",
        ["unity-bridge", "--gesture-port", "5001"]
        + (["--gesture-format", *cli] if cli else []),
    )
    assert core._parse_args().gesture_format == expected
    run = AsyncMock()
    monkeypatch.setattr(gesture_probe, "run", run)
    monkeypatch.setattr(
        "sys.argv", ["unity-gesture-probe"] + (["--format", *cli] if cli else [])
    )
    gesture_probe.main()
    run.assert_awaited_once_with("ws://127.0.0.1:5000", False, expected)


@pytest.mark.parametrize("main", [core._parse_args, gesture_probe.main])
def test_invalid_environment_format(main, monkeypatch):
    monkeypatch.setattr(core, "load_dotenv", lambda: None)
    monkeypatch.setenv("GESTURE_DELIVERY_FORMAT", "auto")
    monkeypatch.setattr("sys.argv", ["command"])
    with pytest.raises(SystemExit):
        main()


@pytest.mark.parametrize("raw, fmt", [("{}", "protobuf"), (b"{}", "json")])
def test_probe_rejects_wrong_websocket_type(raw, fmt):
    with pytest.raises(ValueError):
        gesture_probe.decode_payload(raw, fmt)
