import os
import runpy
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "src" / "gesture_detection" / "config.py"
EXAMPLE_PATH = PROJECT_ROOT / "config.example.toml"


def read_config(contents: str = "", *, root: Path | None = None) -> dict:
    with tempfile.TemporaryDirectory() as directory:
        filename = Path(directory) / "config.toml"
        filename.write_text(contents, encoding="utf-8")
        variables = {"GESTURE_CONFIG_PATH": str(filename)}
        if root is not None:
            variables["GESTURE_PROJECT_ROOT"] = str(root)
        with patch.dict(os.environ, variables, clear=True):
            return runpy.run_path(str(CONFIG_PATH))


def test_defaults_select_camera_without_creating_output() -> None:
    with patch("pathlib.Path.mkdir") as mkdir:
        config = read_config()
    assert config["VIDEO_SOURCE"] is None
    assert config["CAMERA_INDICES"] is None
    assert config["CAMERA_BACKEND"] == 0
    assert config["CAMERA_ROTATION"] == "none"
    assert config["MULTICAM_ROTATION"] == ("none", "none")
    assert config["VIDEO_OUTPUT_PATH"].parent == PROJECT_ROOT / "output"
    assert config["RAMUNE_LEARNED_MODEL_PATH"].name == "ramune_0924.npz"
    mkdir.assert_not_called()


def test_paths_and_device_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    config = read_config(
        f'''
[video]
source = "sample_movies/example.mp4"
[output]
directory = "{tmp_path}"
buffer_frames = 4
record_live = true
[models]
pose = "models/pose.task"
yolo = "{tmp_path / "yolo.pt"}"
[camera]
indices = [2]
backend = 200
fps = 60
'''
    )
    assert config["VIDEO_SOURCE"] == PROJECT_ROOT / "sample_movies/example.mp4"
    assert config["POSE_MODEL_PATH"] == PROJECT_ROOT / "models/pose.task"
    assert config["YOLO_MODEL_PATH"] == tmp_path / "yolo.pt"
    assert config["VIDEO_OUTPUT_PATH"].parent == tmp_path
    assert config["CAMERA_INDICES"] == (2,)
    assert config["CAMERA_BACKEND"] == 200
    assert config["BUFFER_SIZE"] == 60
    assert config["VIDEO_OUTPUT_BUFFER_FRAMES"] == 4
    assert config["RECORD_LIVE_VIDEO"]


def test_empty_source_and_explicit_output() -> None:
    config = read_config('[video]\nsource = ""\n[output]\npath = "custom/out.mp4"\n')
    assert config["VIDEO_SOURCE"] is None
    assert config["VIDEO_OUTPUT_PATH"] == PROJECT_ROOT / "custom/out.mp4"


def test_project_root_controls_relative_assets(tmp_path: Path) -> None:
    config = read_config(root=tmp_path)
    assert config["PROJECT_ROOT"] == tmp_path
    assert config["POSE_MODEL_PATH"] == tmp_path / "pose_landmarker_heavy.task"


@pytest.mark.parametrize("size", ["lite", "full", "heavy"])
def test_model_download_matches_selected_variant(size: str) -> None:
    name = f"pose_landmarker_{size}"
    config = read_config(f'[models]\npose = "models/{name}.task"\n')
    assert config["POSE_MODEL_URL"].endswith(f"/{name}/float16/1/{name}.task")


def test_custom_model_is_never_silently_replaced_with_lite() -> None:
    assert read_config('[models]\npose = "custom.task"\n')["POSE_MODEL_URL"] is None


def test_project_local_config_is_loaded_when_present(tmp_path: Path) -> None:
    (tmp_path / "config.toml").write_text("[camera]\nindices = [3]\n")
    with patch.dict(os.environ, {"GESTURE_PROJECT_ROOT": str(tmp_path)}, clear=True):
        config = runpy.run_path(str(CONFIG_PATH))
    assert config["CONFIG_PATH"] == tmp_path / "config.toml"
    assert config["CAMERA_INDICES"] == (3,)


def test_config_file_can_be_omitted(tmp_path: Path) -> None:
    with patch.dict(os.environ, {"GESTURE_PROJECT_ROOT": str(tmp_path)}, clear=True):
        config = runpy.run_path(str(CONFIG_PATH))
    assert config["CAMERA_INDICES"] is None


def test_explicit_missing_config_fails(tmp_path: Path) -> None:
    with patch.dict(
        os.environ, {"GESTURE_CONFIG_PATH": str(tmp_path / "missing.toml")}, clear=True
    ):
        with pytest.raises(FileNotFoundError, match="missing.toml"):
            runpy.run_path(str(CONFIG_PATH))


def test_example_is_valid_and_matches_defaults() -> None:
    config = read_config(EXAMPLE_PATH.read_text(encoding="utf-8"))
    assert config["CAMERA_INDICES"] is None
    assert config["VIDEO_OUTPUT_PATH"].parent == PROJECT_ROOT / "output"
    assert config["RAMUNE_LEARNED_MODEL_PATH"].name == "ramune_0924.npz"
    assert config["MULTICAM_SELECT_SUBJECT"] == (True, False)
    assert config["ANNOTATION_DEFAULT_PAGE"] == "intervals"
    assert config["ANNOTATION_NINE_POINT_ASSIST"] is False


@pytest.mark.parametrize(
    "value",
    [
        "[camera]\nfps = 0\n",
        "[output]\nbuffer_frames = -1\n",
        '[camera]\nfourcc = "BAD"\n',
        "[camera]\nfps = true\n",
        "[camera]\nindices = [true]\n",
        '[output]\nrecord_live = "true"\n',
        "[camera]\nscan_max_index = 10\n",
        '[pose]\nrunning_mode = "LIVE_STREAM"\n',
        "[events]\nttl_seconds = 0\n",
        "[events]\nttl_seconds = nan\n",
        "[pose.subject]\narea = [0.8, 0, 0.2, 1]\n",
        "[pose.subject]\narea = [0, 0, 1]\n",
        "[pose.subject]\nmin_torso_height = 1.1\n",
        "[multicam]\nenabled = true\n[camera]\nindices = [1, 1]\n",
        "[multicam]\nenabled = true\n[camera]\nindices = [1]\n",
        "[multicam]\nenabled = true\n[camera]\nindices = [-1, 2]\n",
        "[camera]\nindices = [1, 2]\n",
        '[multicam]\nenabled = "maybe"\n',
        "[multicam]\nwidth = 0\n",
        '[multicam.second]\nselect_subject = "invalid"\n',
        '[multicam]\nenabled = true\n[pose]\nrunning_mode = "IMAGE"\n',
        '[multicam]\nenabled = true\n[ramune]\ndetector = "learned"\n',
        '[multicam]\nenabled = true\n[video]\nsource = "single.mp4"\n',
        "[pose]\nselect_subejct = true\n",
        "[unexpected]\nfoo = true\n",
        '[camera]\nindices = "1,2"\n',
        "[pose.subject]\narea = [true, 0, 1, 1]\n",
        "[camera]\nindices = [1, 1]\n",
        '[camera]\nfps = "30"\n',
        '[camera]\nrotation = "sideways"\n',
        '[multicam.first]\nrotation = "left"\n',
    ],
)
def test_invalid_settings(value: str) -> None:
    with pytest.raises(ValueError):
        read_config(value)


@pytest.mark.parametrize("value, expected", [("IMAGE", "IMAGE"), (" video ", "VIDEO")])
def test_pose_running_mode(value: str, expected: str) -> None:
    assert read_config(f'[pose]\nrunning_mode = "{value}"\n')["POSE_RUNNING_MODE"] == expected


def test_subject_area_and_opt_out_are_configurable() -> None:
    config = read_config(
        "[pose]\nselect_subject = false\n[pose.subject]\narea = [0.2, 0.1, 0.8, 0.9]\n"
    )
    assert config["SUBJECT_AREA"] == (0.2, 0.1, 0.8, 0.9)
    assert not config["POSE_SELECT_SUBJECT"]


def test_rotations_are_independent_per_input() -> None:
    config = read_config(
        '[camera]\nrotation = "180"\n'
        '[multicam.first]\nrotation = "clockwise"\n'
        '[multicam.second]\nrotation = "counterclockwise"\n'
    )
    assert config["CAMERA_ROTATION"] == "180"
    assert config["MULTICAM_ROTATION"] == ("clockwise", "counterclockwise")


def test_multicam_is_opt_in_with_independent_subject_selection() -> None:
    assert not read_config()["MULTICAM_ENABLED"]
    config = read_config(
        "[multicam]\nenabled = true\n[camera]\nindices = [0, 2]\n"
        '[multicam.replay]\nsession = "shared/videos/take/session.json"\n'
    )
    assert config["CAMERA_INDICES"] == (0, 2)
    assert config["MULTICAM_SELECT_SUBJECT"] == (True, False)
    assert config["MULTICAM_VIDEO_SESSION"] == PROJECT_ROOT / "shared/videos/take/session.json"
