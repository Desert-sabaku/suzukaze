import pytest
import yaml
from pydantic import ValidationError

from unity_bridge import settings
from unity_bridge.settings import Settings, load_settings

BASE = yaml.safe_load(settings.CONFIG_FILES[0].read_text(encoding="utf-8"))


def _use(monkeypatch, tmp_path, base=BASE, local=None):
    files = []
    for name, data in (("base.yaml", base), ("local.yaml", local)):
        path = tmp_path / name
        if data is not None:
            path.write_text(yaml.safe_dump(data), encoding="utf-8")
        files.append(path)
    monkeypatch.setattr(settings, "CONFIG_FILES", tuple(files))


def test_priority_local_then_base(tmp_path, monkeypatch):
    _use(monkeypatch, tmp_path, local={"unity_websocket_port": 6000})

    loaded = load_settings()

    assert loaded.unity_websocket_port == 6000  # local
    assert loaded.microcontroller_baudrate == BASE["microcontroller_baudrate"]  # base


def test_environment_variables_are_ignored(tmp_path, monkeypatch):
    _use(monkeypatch, tmp_path)
    monkeypatch.setenv("GESTURE_DEBUG_PORT", "7000")

    assert load_settings().gesture_debug_port == BASE["gesture_debug_port"]


def test_missing_key_is_an_error_naming_the_key(tmp_path, monkeypatch):
    _use(
        monkeypatch,
        tmp_path,
        base={k: v for k, v in BASE.items() if k != "fan_pwm_pins"},
    )

    with pytest.raises(ValidationError, match="fan_pwm_pins"):
        load_settings()


def test_unknown_key_is_an_error(tmp_path, monkeypatch):
    _use(monkeypatch, tmp_path, local={"fan_pwm_pinz": [1]})

    with pytest.raises(ValidationError, match="fan_pwm_pinz"):
        load_settings()


def test_pins_are_a_list_in_yaml(tmp_path, monkeypatch):
    _use(monkeypatch, tmp_path, local={"fan_pwm_pins": [1, 2, 3, 4, 5, 6]})
    assert load_settings().fan_pwm_pins == [1, 2, 3, 4, 5, 6]


@pytest.mark.parametrize(
    ("key", "pins"),
    [
        ("fan_pwm_pins", []),  # 空でも落ちる(マイコンへ送らない設定はない)
        ("fan_pwm_pins", [2, 3, 4, 5, 6]),
        ("fan_pwm_pins", [2, 3, 4, 5, 6, 7, 8]),
        ("fan_pwm_pins", [2, 3, 4, 5, 6, 6]),
        ("diffuser_pins", [8]),
        ("diffuser_pins", [8, 9, 10]),
        ("diffuser_pins", [8, 8]),
    ],
)
def test_wrong_pin_count_or_duplicate_is_an_error(tmp_path, monkeypatch, key, pins):
    _use(monkeypatch, tmp_path, local={key: pins})

    with pytest.raises(ValidationError, match=key):
        load_settings()


def test_shared_suzukaze_yaml_is_complete():
    # 共有の suzukaze.yaml だけで、全キーが埋まる(= コードが読むキーがすべて書かれている)。
    assert set(BASE) == set(Settings.model_fields)
    load_settings()
