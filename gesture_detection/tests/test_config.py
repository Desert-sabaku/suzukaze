import os
import runpy
from pathlib import Path
from unittest.mock import patch

import pytest
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "src" / "gesture_detection" / "config.py"


def read_config(values: dict[str, str]) -> dict:
    with patch.dict(os.environ, values, clear=True), patch("dotenv.load_dotenv"):
        return runpy.run_path(str(CONFIG_PATH))


def test_defaults_select_camera_without_creating_output() -> None:
    with patch("pathlib.Path.mkdir") as mkdir:
        config = read_config({})
    assert config["VIDEO_SOURCE"] is None
    assert config["CAMERA_INDEX"] == 0
    assert config["CAMERA_BACKEND"] == 0
    assert config["VIDEO_OUTPUT_PATH"].parent == PROJECT_ROOT / "output"
    mkdir.assert_not_called()


def test_paths_and_device_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    config = read_config(
        {
            "VIDEO_SOURCE": "sample_movies/example.mp4",
            "OUTPUT_DIR": str(tmp_path),
            "POSE_MODEL_PATH": "models/pose.task",
            "YOLO_MODEL_PATH": str(tmp_path / "yolo.pt"),
            "CAMERA_INDEX": "2",
            "CAMERA_BACKEND": "200",
            "FPS": "60",
            "VIDEO_OUTPUT_BUFFER_FRAMES": "4",
        }
    )
    assert config["VIDEO_SOURCE"] == PROJECT_ROOT / "sample_movies/example.mp4"
    assert config["POSE_MODEL_PATH"] == PROJECT_ROOT / "models/pose.task"
    assert config["YOLO_MODEL_PATH"] == tmp_path / "yolo.pt"
    assert config["VIDEO_OUTPUT_PATH"].parent == tmp_path
    assert config["CAMERA_INDEX"] == 2
    assert config["CAMERA_BACKEND"] == 200
    assert config["BUFFER_SIZE"] == 60
    assert config["VIDEO_OUTPUT_BUFFER_FRAMES"] == 4


def test_empty_source_and_explicit_output() -> None:
    config = read_config({"VIDEO_SOURCE": "", "VIDEO_OUTPUT_PATH": "custom/out.mp4"})
    assert config["VIDEO_SOURCE"] is None
    assert config["VIDEO_OUTPUT_PATH"] == PROJECT_ROOT / "custom/out.mp4"


def test_explicit_project_root_controls_dotenv_and_relative_assets(tmp_path: Path) -> None:
    with patch("dotenv.load_dotenv") as loader:
        with patch.dict(os.environ, {"GESTURE_PROJECT_ROOT": str(tmp_path)}, clear=True):
            config = runpy.run_path(str(CONFIG_PATH))
    loader.assert_called_once_with(tmp_path / ".env", override=False)
    assert config["PROJECT_ROOT"] == tmp_path
    assert config["POSE_MODEL_PATH"] == tmp_path / "pose_landmarker_lite.task"


def test_dotenv_loading_preserves_environment(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text('CAMERA_INDEX=3\nVIDEO_SOURCE="sample movies/example.mp4"\n')
    with (
        patch.dict(os.environ, {"CAMERA_INDEX": "7"}, clear=True),
        patch(
            "dotenv.load_dotenv", side_effect=lambda *a, **kw: load_dotenv(env_file, **kw)
        ) as loader,
    ):
        config = runpy.run_path(str(CONFIG_PATH))
    loader.assert_called_once_with(PROJECT_ROOT / ".env", override=False)
    assert config["CAMERA_INDEX"] == 7
    assert config["VIDEO_SOURCE"] == PROJECT_ROOT / "sample movies/example.mp4"


@pytest.mark.parametrize(
    "values", [{"FPS": "0"}, {"VIDEO_OUTPUT_BUFFER_FRAMES": "-1"}, {"CAMERA_FOURCC": "BAD"}]
)
def test_invalid_settings(values: dict[str, str]) -> None:
    with pytest.raises(ValueError):
        read_config(values)


@pytest.mark.parametrize("value, expected", [("IMAGE", "IMAGE"), (" video ", "VIDEO")])
def test_pose_running_mode(value, expected):
    assert read_config({"POSE_RUNNING_MODE": value})["POSE_RUNNING_MODE"] == expected


def test_pose_mode_defaults_to_video():
    assert read_config({})["POSE_RUNNING_MODE"] == "VIDEO"


def test_invalid_pose_mode():
    with pytest.raises(ValueError, match="POSE_RUNNING_MODE"):
        read_config({"POSE_RUNNING_MODE": "LIVE_STREAM"})


@pytest.mark.parametrize(
    "values",
    [
        {"GESTURE_DELIVERY_PORT": "0"},
        {"GESTURE_MAX_PENDING": "0"},
        {"GESTURE_EVENT_TTL": "nan"},
        {"GESTURE_RETRY_INTERVAL": "-1"},
        {"GESTURE_STATE_INTERVAL": "0.5"},
    ],
)
def test_invalid_delivery_settings(values):
    with pytest.raises(ValueError):
        read_config(values)
