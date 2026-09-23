import csv
import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from gesture_detection.video_annotation import (
    AnnotationApp,
    TimelineEditor,
    active_intervals,
    default_output_path,
    import_legacy_landmarks,
    load_label_config,
    load_timeline,
    new_timeline,
    save_timeline,
)


def make_video(path: Path, frames: int = 12) -> None:
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter.fourcc(*"MJPG"), 10, (64, 48))
    assert writer.isOpened()
    for index in range(frames):
        writer.write(np.full((48, 64, 3), index * 10, dtype=np.uint8))
    writer.release()


@pytest.fixture
def timeline(tmp_path):
    video = tmp_path / "group" / "clip.avi"
    video.parent.mkdir()
    make_video(video)
    output = tmp_path / "timeline.json"
    data = new_timeline(video, load_label_config())
    save_timeline(output, data)
    return video, output, TimelineEditor(data, output)


def test_default_path_and_video_validation(tmp_path):
    video = Path("shared/videos/group/clip.mp4")
    assert default_output_path(video, tmp_path) == (
        tmp_path / "shared/annotations/group/clip/timeline.json"
    )

    first = tmp_path / "first.avi"
    second = tmp_path / "second.avi"
    make_video(first)
    make_video(second, 8)
    output = tmp_path / "timeline.json"
    save_timeline(output, new_timeline(first, load_label_config()))
    assert load_timeline(output, first)["source"]["total_frames"] == 12
    with pytest.raises(ValueError, match="different video"):
        load_timeline(output, second)


def test_intervals_events_landmarks_and_history(timeline):
    _, output, editor = timeline
    interval_id = editor.add_interval("action", "FANNING", 7, 3)
    assert active_intervals(editor.data, 5)[0]["id"] == interval_id
    assert editor.data["intervals"][0]["start_frame"] == 3

    with pytest.raises(ValueError, match="Overlapping"):
        editor.add_interval("action", "RAMUNE", 6, 9)
    assert len(editor.data["intervals"]) == 1
    editor.add_interval("ramune_phase", "READY", 4, 6)

    event_id = editor.add_event("FANNING_REVERSAL", 5)
    editor.set_landmark(5, "left_wrist", "marked", (12, 18))
    editor.set_landmark(5, "right_wrist", "uncertain")
    assert editor.data["landmarks"][0]["points"]["left_wrist"]["x_px"] == 12
    editor.set_absent(8)
    assert set(point["status"] for point in editor.data["landmarks"][1]["points"].values()) == {
        "absent"
    }

    editor.update_interval_edge(interval_id, "start", 2)
    editor.delete(event_id)
    assert not editor.data["events"]
    assert editor.undo()
    assert editor.data["events"][0]["id"] == event_id
    assert editor.redo()
    assert not editor.data["events"]
    assert load_timeline(output)["intervals"][0]["start_frame"] == 2


def test_import_legacy_landmarks(timeline, tmp_path):
    video, _, editor = timeline
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    (legacy / "source.json").write_text(
        json.dumps({"sha256": editor.data["source"]["sha256"]}), encoding="utf-8"
    )
    fields = ("video", "frame_id", "timestamp", "landmark", "x_px", "y_px", "status")
    with (legacy / "annotations.csv").open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=fields)
        writer.writeheader()
        writer.writerow(
            {
                "video": video.name,
                "frame_id": "2",
                "timestamp": "0.2",
                "landmark": "left_wrist",
                "x_px": "10",
                "y_px": "20",
                "status": "marked",
            }
        )
        writer.writerow(
            {
                "video": video.name,
                "frame_id": "3",
                "timestamp": "0.3",
                "landmark": "right_wrist",
                "x_px": "",
                "y_px": "",
                "status": "pending",
            }
        )
    assert import_legacy_landmarks(editor, legacy) == 1
    assert editor.data["landmarks"][0]["points"]["left_wrist"] == {
        "status": "marked",
        "x_px": 10,
        "y_px": 20,
    }


def test_ui_render_and_actions_without_window(timeline):
    video, _, editor = timeline
    app = AnnotationApp(video, editor, 64, 48)
    try:
        canvas = app.render()
        assert canvas.shape[1] == 64 + 470
        app.handle("label", ("action", "UCHIMIZU"))
        app.handle("start")
        app.handle("step", 3)
        app.handle("end")
        assert editor.data["intervals"][0]["end_frame"] == 3

        app.handle("event", "UCHIMIZU_RELEASE")
        app.handle("landmark", "left_wrist")
        app.click(cv2.EVENT_LBUTTONDOWN, 10, 20, 0, None)
        assert editor.data["events"][0]["frame_id"] == 3
        assert editor.data["landmarks"][0]["points"]["left_wrist"]["status"] == "marked"
    finally:
        app.reader.close()


def test_phase_must_belong_to_and_stay_inside_action(timeline):
    _, _, editor = timeline
    action_id = editor.add_interval("action", "UCHIMIZU", 2, 9)
    phase_id = editor.add_interval("uchimizu_phase", "READY", 3, 5, action_id)
    phase = next(item for item in editor.data["intervals"] if item["id"] == phase_id)
    assert phase["parent_action_id"] == action_id

    with pytest.raises(ValueError, match="inside its parent action"):
        editor.add_interval("uchimizu_phase", "SWING", 1, 2, action_id)

    editor.add_event("UCHIMIZU_PEAK", 4, action_id)
    editor.delete(action_id)
    assert not editor.data["intervals"]
    assert not editor.data["events"]
