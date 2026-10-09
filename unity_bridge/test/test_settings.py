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


def test_pins_are_named_and_ordered_by_channel(tmp_path, monkeypatch):
    fan = {**BASE["fan_pwm_pins"], "left_back": 20}
    _use(monkeypatch, tmp_path, local={"fan_pwm_pins": fan})

    loaded = load_settings()

    assert loaded.fan_pwm_pins.ordered() == (20, 3, 4, 5, 6, 7)
    assert loaded.diffuser_pins.ordered() == (8, 9)


@pytest.mark.parametrize(
    ("key", "name", "pin"),
    [
        ("fan_pwm_pins", "left_back", 3),  # left_side と重複
        ("fan_pwm_pins", "left_back", 7),  # right_front と重複
        ("diffuser_pins", "ramune", 9),  # forest と重複
    ],
)
def test_duplicate_pin_is_an_error(tmp_path, monkeypatch, key, name, pin):
    _use(monkeypatch, tmp_path, local={key: {**BASE[key], name: pin}})

    with pytest.raises(ValidationError, match="duplicate pins"):
        load_settings()


@pytest.mark.parametrize(
    ("key", "name"), [("fan_pwm_pins", "left_back"), ("diffuser_pins", "forest")]
)
def test_missing_pin_name_is_an_error(tmp_path, monkeypatch, key, name):
    pins = {k: v for k, v in BASE[key].items() if k != name}
    _use(monkeypatch, tmp_path, local={key: pins})

    with pytest.raises(ValidationError, match=f"{key}.{name}"):
        load_settings()


@pytest.mark.parametrize("key", ["fan_pwm_pins", "diffuser_pins"])
def test_unknown_pin_name_is_an_error(tmp_path, monkeypatch, key):
    _use(monkeypatch, tmp_path, local={key: {**BASE[key], "center": 1}})

    with pytest.raises(ValidationError, match=f"{key}.center"):
        load_settings()


def test_shared_suzukaze_yaml_is_complete():
    # 共有の suzukaze.yaml だけで、全キーが埋まる(= コードが読むキーがすべて書かれている)。
    assert set(BASE) == set(Settings.model_fields)
    load_settings()
