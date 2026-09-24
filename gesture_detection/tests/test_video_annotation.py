import csv
import json
from pathlib import Path

import cv2
import numpy as np
import pytest
from scripts.video_annotation import (
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


def test_exclusive_track_adjusts_nearby_boundaries(timeline):
    _, _, editor = timeline
    editor.add_interval("action", "FANNING", 3, 7)
    assert editor.nearest_available_frame("action", 6, 10) == 8
    assert editor.adjusted_interval("action", 0, 4, 10) == (0, 2)
    assert editor.adjusted_interval("action", 6, 10, 10) == (8, 10)

    editor.add_interval("action", "RAMUNE", 0, 2)
    editor.add_interval("action", "UCHIMIZU", 8, 11)
    with pytest.raises(ValueError, match="No unannotated frame"):
        editor.nearest_available_frame("action", 5, 10)


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


def test_existing_six_point_timeline_gains_new_landmark_choices(timeline):
    _, output, editor = timeline
    editor.data["label_config"]["landmarks"] = [
        "left_shoulder",
        "right_shoulder",
        "left_wrist",
        "right_wrist",
        "left_hip",
        "right_hip",
    ]
    editor.set_landmark(2, "left_wrist", "marked", (10, 15))
    editor.set_absent(3)

    loaded = load_timeline(output)

    assert len(loaded["label_config"]["landmarks"]) == 33
    assert loaded["landmarks"][0]["points"]["left_wrist"]["x_px"] == 10
    assert len(loaded["landmarks"][1]["points"]) == 33
    assert all(point["status"] == "absent" for point in loaded["landmarks"][1]["points"].values())


def test_landmark_page_advances_within_frame_and_supports_arrows(app):
    app.seek(3)
    app.handle("page", "landmarks")
    assert app.selected_landmark == "nose"
    app.render()
    assert any(action == "landmark" for _, action, _ in app.buttons)
    assert not any(action == "start" for _, action, _ in app.buttons)

    app.click(cv2.EVENT_LBUTTONDOWN, 10, 20, 0, None)
    assert app.frame_id == 3
    assert app.selected_landmark == "left_eye_inner"
    assert app._point_data()["nose"]["status"] == "marked"
    app.key(65363)  # X11/Qt right arrow
    assert app.selected_landmark == "left_eye"
    app.key(2424832)  # Windows left arrow
    assert app.selected_landmark == "left_eye_inner"
    app.handle("uncertain")
    assert app._point_data()["left_eye_inner"]["status"] == "uncertain"
    assert app.selected_landmark == "left_eye"
    app.handle("clear_landmark")
    assert "left_eye" not in app._point_data()
    app.handle("absent")
    assert len(app._point_data()) == 33
    app.handle("reset_landmarks")
    assert app._point_data() == {}
    assert app.selected_landmark == "nose"


def test_last_landmark_stays_on_selected_frame(app):
    app.seek(5)
    app.handle("page", "landmarks")
    last = app.data["label_config"]["landmarks"][-1]
    app.handle("landmark", last)
    app.click(cv2.EVENT_LBUTTONDOWN, 10, 20, 0, None)

    assert app.frame_id == 5
    assert app.selected_landmark == last
    assert app._point_data()[last]["status"] == "marked"


def test_landmark_groups_and_page_navigation(app, monkeypatch):
    app.handle("page", "landmarks")
    pages = app._landmark_pages()
    assert [(title, len(names)) for title, names in pages] == [
        ("FACE & HEAD", 11),
        ("UPPER BODY & HANDS", 12),
        ("HIPS & LEGS", 10),
    ]
    drawn = []
    original = cv2.putText

    def capture_text(image, text, position, *args):
        drawn.append(text)
        return original(image, text, position, *args)

    monkeypatch.setattr(cv2, "putText", capture_text)
    app.render()
    assert "PAGE 1/3 - FACE & HEAD" in drawn
    assert {payload for _, action, payload in app.buttons if action == "landmark"} == set(
        pages[0][1]
    )

    app.handle("landmark_page", 1)
    assert app.selected_landmark == "left_shoulder"
    app.render()
    assert "PAGE 2/3 - UPPER BODY & HANDS" in drawn
    app.key(65366)  # X11 Page Down
    assert app.selected_landmark == "left_hip"
    app.key(2162688)  # Windows Page Up
    assert app.selected_landmark == "left_shoulder"
    app.key(65361)  # Individual arrow still crosses group boundary.
    assert app.selected_landmark == "mouth_right"
    assert app._landmark_page_index() == 0


def test_custom_landmarks_appear_in_other_group(app):
    app.data["label_config"]["landmarks"].append("custom_point")
    app.handle("page", "landmarks")
    assert app._landmark_pages()[-1] == ("OTHER", ["custom_point"])


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
        assert app.selected_action_id == editor.data["intervals"][0]["id"]
        assert app.selected_label is None
        app.render()
        phase_payloads = {
            payload
            for _, action, payload in app.buttons
            if action == "label" and payload[0] != "action"
        }
        assert phase_payloads == {
            ("uchimizu_phase", "READY"),
            ("uchimizu_phase", "SWING"),
        }

        app.handle("event", "UCHIMIZU_RELEASE")
        app.handle("landmark", "left_wrist")
        app.click(cv2.EVENT_LBUTTONDOWN, 10, 20, 0, None)
        assert editor.data["events"][0]["frame_id"] == 3
        assert editor.data["landmarks"][0]["points"]["left_wrist"]["status"] == "marked"
    finally:
        app.reader.close()


@pytest.fixture
def app(timeline):
    video, _, editor = timeline
    instance = AnnotationApp(video, editor, 64, 48)
    yield instance
    instance.reader.close()


def test_pending_start_and_bottom_controls(app):
    app.handle("label", ("action", "FANNING"))
    app.seek(2)
    app.handle("start")
    app.seek(6)
    canvas = app.render()
    x = app._frame_x(2)
    assert tuple(canvas[720, x]) == (0, 230, 255)
    # Timeline seeking preserves the uncommitted start.
    app.click(cv2.EVENT_LBUTTONDOWN, app._frame_x(7), 725, 0, None)
    assert app.interval_start == 2
    controls = [rect for rect, action, _ in app.buttons if action in {"start", "end", "delete"}]
    others = [rect for rect, action, _ in app.buttons if action not in {"start", "end", "delete"}]
    assert len(controls) == 3
    assert min(rect[1] for rect in controls) > max(rect[3] for rect in others)
    app.handle("end")
    assert app.editor.data["intervals"][0]["start_frame"] == 2
    assert app.editor.data["intervals"][0]["end_frame"] == 7


def test_pending_start_can_be_canceled_without_saving(app):
    app.handle("label", ("action", "FANNING"))
    app.seek(2)
    app.handle("start")
    app.render()
    assert any(action == "delete" for _, action, _ in app.buttons)
    app.handle("delete")
    assert app.interval_start is None
    assert app.selected_label == ("action", "FANNING")
    assert app.editor.data["intervals"] == []
    app.seek(4)
    app.handle("start")
    app.key(8)
    assert app.interval_start is None
    assert app.editor.data["intervals"] == []


def test_timeline_shows_each_tracks_current_label(app, monkeypatch):
    action_id = app.editor.add_interval("action", "FANNING", 0, 11)
    app.editor.add_interval("fanning_phase", "ACTIVE", 2, 9, action_id)
    app.seek(4)
    drawn = []
    original = cv2.putText

    def capture_text(image, text, position, *args):
        drawn.append((text, position))
        return original(image, text, position, *args)

    monkeypatch.setattr(cv2, "putText", capture_text)
    app.render()
    assert any(text == "FANNING" and x == 5 for text, (x, _) in drawn)
    assert any(text == "ACTIVE" and x == 5 for text, (x, _) in drawn)
    assert app._x_frame(app._frame_x(4)) == 4


@pytest.mark.parametrize("track,label", [("action", "FANNING"), ("fanning_phase", "ACTIVE")])
def test_buttons_resize_just_saved_interval(app, track, label):
    if track != "action":
        app.selected_action_id = app.editor.add_interval("action", "FANNING", 0, 11)
    app.handle("label", (track, label))
    app.seek(3)
    app.handle("start")
    app.seek(6)
    app.handle("end")
    identifier = app.selected_annotation
    for edge, target in [("end", 9), ("end", 5), ("start", 1), ("start", 4)]:
        app.seek(target)
        app.handle(edge)
        interval = next(item for item in app.editor.data["intervals"] if item["id"] == identifier)
        assert interval[f"{edge}_frame"] == target
    assert app.editor.data["intervals"][-1]["start_frame"] == 4
    assert app.editor.data["intervals"][-1]["end_frame"] == 5


def test_repeated_action_uses_occurrence_at_current_frame(app):
    first = app.editor.add_interval("action", "FANNING", 1, 3)
    second = app.editor.add_interval("action", "FANNING", 7, 9)

    for start, end, parent in ((2, 3, first), (8, 9, second)):
        app.seek(start)
        assert app.selected_action_id == parent
        app.handle("label", ("fanning_phase", "ACTIVE"))
        app.handle("start")
        assert app.interval_start == start
        app.seek(end)
        app.handle("end")
        phase = app.editor.data["intervals"][-1]
        assert phase["parent_action_id"] == parent
        assert (phase["start_frame"], phase["end_frame"]) == (start, end)
        app.handle("event", "FANNING_REVERSAL")
        assert app.editor.data["events"][-1]["parent_action_id"] == parent

    app.seek(5)
    assert app.selected_action_id is None
    app.handle("label", ("fanning_phase", "POSITION"))
    assert app.selected_label is None


def test_new_action_mode_survives_timeline_seeking_near_existing_interval(app):
    first = app.editor.add_interval("action", "FANNING", 1, 4)
    app.render()
    app.seek(4)
    app._select_interval(app.data["intervals"][0])
    assert app.selected_annotation == first
    app.handle("label", ("action", "FANNING"))
    app.click(cv2.EVENT_LBUTTONDOWN, app._frame_x(4) + 5, 725, 0, None)
    assert app.selected_label == ("action", "FANNING")
    assert app.selected_annotation is None

    app.click(cv2.EVENT_LBUTTONDOWN, app._frame_x(7), 725, 0, None)
    app.handle("start")
    app.click(cv2.EVENT_LBUTTONDOWN, app._frame_x(9), 725, 0, None)
    app.handle("end")

    actions = [item for item in app.data["intervals"] if item["track"] == "action"]
    assert [(item["label"], item["start_frame"], item["end_frame"]) for item in actions] == [
        ("FANNING", 1, 4),
        ("FANNING", 7, 9),
    ]


def test_phase_cannot_end_in_another_action_occurrence(app):
    first = app.editor.add_interval("action", "FANNING", 1, 3)
    app.editor.add_interval("action", "FANNING", 7, 9)
    app.seek(2)
    app.handle("label", ("fanning_phase", "ACTIVE"))
    app.handle("start")
    assert app.interval_parent_action_id == first
    app.seek(8)
    app.handle("end")

    assert "same action" in app.message
    assert len(app.editor.data["intervals"]) == 2
    assert app.interval_start == 2


def test_phase_label_cannot_follow_cursor_into_different_action(app):
    app.editor.add_interval("action", "FANNING", 1, 3)
    app.editor.add_interval("action", "RAMUNE", 7, 9)
    app.seek(2)
    app.handle("label", ("fanning_phase", "ACTIVE"))
    app.seek(8)
    app.handle("start")

    assert app.interval_start is None
    assert "matching action" in app.message


@pytest.mark.parametrize(
    "edge,initial,target", [("start", 3, 1), ("start", 3, 5), ("end", 7, 10), ("end", 7, 5)]
)
def test_drag_resizes_once_and_supports_undo(app, edge, initial, target):
    identifier = app.editor.add_interval("action", "FANNING", 3, 7)
    app.render()
    app.click(cv2.EVENT_LBUTTONDOWN, app._frame_x(initial), 725, 0, None)
    assert app.drag_edge == (identifier, edge)
    app.click(cv2.EVENT_MOUSEMOVE, app._frame_x(target), 725, cv2.EVENT_FLAG_LBUTTON, None)
    assert app.editor.data["intervals"][0][f"{edge}_frame"] == initial
    app.render()  # Preview does not save or add an undo step.
    assert len(app.editor.undo_stack) == 1
    app.click(cv2.EVENT_LBUTTONUP, app._frame_x(target), 725, 0, None)
    assert app.editor.data["intervals"][0][f"{edge}_frame"] == target
    assert len(app.editor.undo_stack) == 2
    app.key(ord("z"))
    assert app.data["intervals"][0][f"{edge}_frame"] == initial
    app.key(ord("y"))
    assert app.data["intervals"][0][f"{edge}_frame"] == target


def test_rejected_drag_restores_interval_and_saved_file(app):
    app.editor.add_interval("action", "FANNING", 1, 4)
    app.editor.add_interval("action", "RAMUNE", 7, 10)
    app.click(cv2.EVENT_LBUTTONDOWN, app._frame_x(4), 725, 0, None)
    app.click(cv2.EVENT_LBUTTONUP, app._frame_x(8), 725, 0, None)
    assert "Overlapping" in app.message
    assert app.data["intervals"][0]["end_frame"] == 4
    assert load_timeline(app.editor.output)["intervals"][0]["end_frame"] == 4
    assert len(app.editor.undo_stack) == 2


def test_resize_preserves_children_and_rejects_crossing(app):
    identifier = app.editor.add_interval("action", "FANNING", 1, 10)
    app.editor.add_interval("fanning_phase", "ACTIVE", 3, 8, identifier)
    app._select_interval(app.data["intervals"][0])
    app.seek(6)
    app.handle("end")
    assert "inside its parent action" in app.message
    assert app.data["intervals"][0]["end_frame"] == 10
    app.seek(11)
    app.handle("start")
    assert "Invalid interval frames" in app.message
    assert app.data["intervals"][0]["start_frame"] == 1


def test_run_does_not_create_native_seek_bar(app, monkeypatch):
    from unittest.mock import Mock

    for name in ("namedWindow", "setMouseCallback", "imshow", "destroyAllWindows"):
        monkeypatch.setattr(cv2, name, Mock())
    trackbar = Mock()
    monkeypatch.setattr(cv2, "createTrackbar", trackbar)
    monkeypatch.setattr(cv2, "waitKeyEx", lambda _: ord("q"))
    app.run()
    trackbar.assert_not_called()


def test_run_keeps_processing_events_without_repainting_unchanged_frame(app, monkeypatch):
    from unittest.mock import Mock

    for name in ("namedWindow", "setMouseCallback", "destroyAllWindows"):
        monkeypatch.setattr(cv2, name, Mock())
    show = Mock()
    monkeypatch.setattr(cv2, "imshow", show)
    keys = iter([-1, -1, -1, ord("q")])
    monkeypatch.setattr(cv2, "waitKeyEx", lambda _: next(keys))
    monkeypatch.setattr(cv2, "getWindowProperty", lambda *args: 1)

    app.run()

    assert show.call_count == 1


def test_playback_caps_painting_but_continues_processing_events(app, monkeypatch):
    from unittest.mock import Mock

    for name in ("namedWindow", "setMouseCallback", "destroyAllWindows"):
        monkeypatch.setattr(cv2, name, Mock())
    show = Mock()
    monkeypatch.setattr(cv2, "imshow", show)
    keys = iter([-1] * 10 + [ord("q")])
    wait = Mock(side_effect=lambda _: next(keys))
    monkeypatch.setattr(cv2, "waitKeyEx", wait)
    monkeypatch.setattr(cv2, "getWindowProperty", lambda *args: 1)
    clock = iter(index * 0.005 for index in range(100))
    monkeypatch.setattr("scripts.video_annotation.time.monotonic", lambda: next(clock))
    app.playing = True
    app._last_tick = -1

    app.run()

    assert wait.call_count == 11
    assert 1 < show.call_count < wait.call_count


def test_playback_end_repaints_play_button(app, monkeypatch):
    from unittest.mock import Mock

    app.seek(app.total - 1)
    app.playing = True
    app._last_tick = -1
    app._needs_redraw = False
    for name in ("namedWindow", "setMouseCallback", "destroyAllWindows"):
        monkeypatch.setattr(cv2, name, Mock())
    show = Mock()
    monkeypatch.setattr(cv2, "imshow", show)
    monkeypatch.setattr(cv2, "waitKeyEx", Mock(side_effect=[-1, ord("q")]))
    monkeypatch.setattr(cv2, "getWindowProperty", lambda *args: 1)
    labels = []
    original = cv2.putText

    def capture_text(image, label, position, *args):
        labels.append(label)
        return original(image, label, position, *args)

    monkeypatch.setattr(cv2, "putText", capture_text)
    app.run()

    assert not app.playing
    assert show.call_count == 1
    assert "PLAY" in labels
