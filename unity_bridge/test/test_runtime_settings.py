import json

import pytest

from unity_bridge.runtime_settings import RuntimeSettings, SettingsStore


def test_update_bumps_the_version_and_survives_a_restart(tmp_path):
    path = tmp_path / "settings.json"
    store = SettingsStore(path)
    assert store.current == RuntimeSettings()
    version = store.version
    store.update({"diffuser_enabled": False, "time_scale_multiplier": 2})
    assert store.version == version + 1
    assert store.current == RuntimeSettings(False, 2.0)
    assert SettingsStore(path).current == RuntimeSettings(False, 2.0)


@pytest.mark.parametrize(
    "fields",
    [
        {"diffuser_enabled": 1},
        {"time_scale_multiplier": -1},
        {"time_scale_multiplier": 101},
        {"time_scale_multiplier": float("nan")},
        {"time_scale_multiplier": True},
        {"time_scale_multiplier": "2"},
        {"volume": 1},
    ],
)
def test_invalid_fields_are_rejected_and_nothing_changes(tmp_path, fields):
    store = SettingsStore(tmp_path / "settings.json")
    version = store.version
    with pytest.raises(ValueError):
        store.update(fields)
    assert store.current == RuntimeSettings()
    assert store.version == version
    assert not (tmp_path / "settings.json").exists()


def test_a_broken_settings_file_falls_back_to_defaults(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"time_scale_multiplier": -5}))
    assert SettingsStore(path).current == RuntimeSettings()
    path.write_text("{")
    assert SettingsStore(path).current == RuntimeSettings()
