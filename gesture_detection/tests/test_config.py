import os
import runpy
from pathlib import Path
from unittest.mock import patch

import pytest
from dotenv import load_dotenv

CONFIG_PATH = Path(__file__).resolve().parents[1] / "modules" / "config.py"


def read_config(values: dict[str, str]) -> dict:
    with patch.dict(os.environ, values, clear=True), patch("dotenv.load_dotenv"):
        return runpy.run_path(str(CONFIG_PATH))


def test_defaults_select_camera_without_creating_output() -> None:
    with patch("pathlib.Path.mkdir") as mkdir:
        config = read_config({})
    assert config["VIDEO_SOURCE"] is None
    assert config["CAMERA_INDEX"] == 0
    assert config["CAMERA_BACKEND"] == 0
    assert config["VIDEO_OUTPUT_PATH"].parent == CONFIG_PATH.parents[1] / "output"
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
    assert config["VIDEO_SOURCE"] == CONFIG_PATH.parents[1] / "sample_movies/example.mp4"
    assert config["POSE_MODEL_PATH"] == CONFIG_PATH.parents[1] / "models/pose.task"
    assert config["YOLO_MODEL_PATH"] == tmp_path / "yolo.pt"
    assert config["VIDEO_OUTPUT_PATH"].parent == tmp_path
    assert config["CAMERA_INDEX"] == 2
    assert config["CAMERA_BACKEND"] == 200
    assert config["BUFFER_SIZE"] == 60
    assert config["VIDEO_OUTPUT_BUFFER_FRAMES"] == 4


def test_empty_source_and_explicit_output() -> None:
    config = read_config({"VIDEO_SOURCE": "", "VIDEO_OUTPUT_PATH": "custom/out.mp4"})
    assert config["VIDEO_SOURCE"] is None
    assert config["VIDEO_OUTPUT_PATH"] == CONFIG_PATH.parents[1] / "custom/out.mp4"


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
    loader.assert_called_once_with(CONFIG_PATH.parents[1] / ".env", override=False)
    assert config["CAMERA_INDEX"] == 7
    assert config["VIDEO_SOURCE"] == CONFIG_PATH.parents[1] / "sample movies/example.mp4"


@pytest.mark.parametrize(
    "values", [{"FPS": "0"}, {"VIDEO_OUTPUT_BUFFER_FRAMES": "-1"}, {"CAMERA_FOURCC": "BAD"}]
)
def test_invalid_settings(values: dict[str, str]) -> None:
    with pytest.raises(ValueError):
        read_config(values)
