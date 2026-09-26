"""Optional 0924 Ramune detector. Camera-independent, bounded, causal inference."""

import json
import math
from collections import deque
from pathlib import Path

import numpy as np

DEFAULT_MODEL = Path(__file__).with_name("models") / "ramune_0924.npz"


def current_features(points: np.ndarray, aspect: float) -> tuple[np.ndarray, np.ndarray]:
    selected = points[[11, 12, 13, 14, 15, 16, 23, 24]].copy()
    xy, visibility = selected[:, :2], selected[:, 2]
    xy[:, 0] *= aspect
    center, hips = xy[:2].mean(axis=0), xy[6:].mean(axis=0)
    scale = max(float(np.linalg.norm(center - hips)), 0.03)
    xy = np.clip((xy - center) / scale, -5, 5)
    xy[visibility < 0.5] = 0
    base = np.concatenate([xy.reshape(-1), visibility])
    p = points[[11, 12, 15, 16]].copy()
    valid = (p[:, 2] > 0.5) & np.isfinite(p).all(axis=1)
    p[:, 0] *= aspect
    center = p[:2, :2].mean(axis=0)
    width = float(np.linalg.norm(p[0, :2] - p[1, :2]))
    shoulders = bool(valid[:2].all() and width > 1e-6)
    wrists = (p[2:, :2] - center) / (width if shoulders else 1.0)
    delta = wrists[0] - wrists[1]
    left, right = shoulders and valid[2], shoulders and valid[3]
    flags = np.array([left and right] * 3 + [left] * 2 + [right] * 2)
    values = np.r_[abs(delta[0]), abs(delta[1]), np.linalg.norm(delta), wrists.reshape(-1)]
    geometry = np.r_[np.where(flags, values, 0.0), flags.astype(float)]
    return base, geometry


class LearnedRamuneAnalyzer:
    """Action is used only for setup/release, not as a new public gesture policy."""

    def __init__(self, model_path: Path = DEFAULT_MODEL, *, fps: float = 30.0) -> None:
        if not math.isfinite(fps) or fps <= 0:
            raise ValueError("Learned Ramune FPS must be positive and finite")
        with np.load(model_path, allow_pickle=False) as data:
            self.metadata = json.loads(str(data["metadata"]))
            self.weights = {key: data[key].copy() for key in data.files if key != "metadata"}
        if (
            self.metadata.get("format_version") != 1
            or self.metadata.get("feature_schema") != "0924-relative-position-v1"
        ):
            raise ValueError("Unsupported learned Ramune model")
        for target in ("action", "phase"):
            history = self.metadata[target]["history"]
            if not math.isfinite(history) or not 0 < history <= 2:
                raise ValueError("Invalid model history")
        if self.metadata.get("central_mask") != [0.35, 0.75]:
            raise ValueError("Unsupported learned Ramune input mask")
        for key in ("hold_seconds", "release_seconds", "setup_seconds"):
            if not math.isfinite(self.metadata[key]) or self.metadata[key] <= 0:
                raise ValueError("Invalid temporal settings")
        self.windows = {
            target: max(1, round(self.metadata[target]["history"] * fps))
            for target in ("action", "phase")
        }
        for target, dimensions in (("action", 96), ("phase", 110)):
            if self.metadata[target]["classifier"] not in ("linear", "rbf"):
                raise ValueError("Unsupported model classifier")
            expected = dimensions + 1 + (128 if self.metadata[target]["classifier"] == "rbf" else 0)
            shapes = {
                "mean": (dimensions,),
                "scale": (dimensions,),
                "counts": (5,),
                "beta": (expected, 5),
                "projection": (dimensions, 64),
            }
            for key, shape in shapes.items():
                value = self.weights[target + "_" + key]
                if value.shape != shape or not np.isfinite(value).all():
                    raise ValueError(f"Invalid model weights: {target}_{key}")
            if (self.weights[target + "_scale"] <= 0).any():
                raise ValueError("Invalid model scale")
        self.history: deque[np.ndarray] = deque(maxlen=max(self.windows.values()) + 1)
        self.reset()

    def reset(self) -> None:
        self.history.clear()
        self.gate = "WAIT_SETUP"
        self.state = "IDLE"
        self.last_time: float | None = None
        self.last_frame: int | None = None
        self.last_open = -math.inf
        self.setup_since: float | None = None
        self.release_since: float | None = None
        self.just_opened = False
        self.action = self.phase = 0

    def features(self, base: np.ndarray, geometry: np.ndarray, target: str) -> np.ndarray:
        values = np.asarray(self.history)
        window = self.windows[target]
        segment = values[-window:]
        previous = values[max(0, len(values) - window - 1)]
        result = np.r_[base, segment.mean(axis=0), segment.std(axis=0), base - previous]
        return np.r_[result, geometry] if target == "phase" else result

    def predict(self, feature: np.ndarray, target: str) -> int:
        value = np.clip(
            (feature - self.weights[target + "_mean"]) / self.weights[target + "_scale"], -10, 10
        )
        if self.metadata[target]["classifier"] == "rbf":
            angles = value @ self.weights[target + "_projection"]
            value = np.r_[value, np.sin(angles), np.cos(angles)]
        scores = np.r_[value, 1.0] @ self.weights[target + "_beta"]
        scores[self.weights[target + "_counts"] == 0] = -np.inf
        return int(scores.argmax())

    def advance(self, phase: int, action: int, observed: bool, now: float) -> bool:
        self.just_opened = False
        if self.gate == "ARMED" and phase == 3:
            self.gate = "OPENED"
            self.last_open = now
            self.just_opened = True
        if self.gate == "OPENED":
            if phase == 3:
                self.last_open = now
            if phase == 3 or now - self.last_open <= self.metadata["hold_seconds"] + 1e-9:
                self.state = "OPENED"
                return True
            self.gate = "LOCKED"
            self.setup_since = self.release_since = None
        if self.gate == "LOCKED":
            if observed and action != 1:
                self.release_since = now if self.release_since is None else self.release_since
                if now - self.release_since + 1e-9 >= self.metadata["release_seconds"]:
                    self.gate = "WAIT_SETUP"
            else:
                self.release_since = None
        elif self.gate == "WAIT_SETUP":
            if observed and action == 1 and phase in (1, 2):
                self.setup_since = now if self.setup_since is None else self.setup_since
                if now - self.setup_since + 1e-9 >= self.metadata["setup_seconds"]:
                    self.gate = "ARMED"
            else:
                self.setup_since = None
        self.state = (
            "WAIT_RELEASE"
            if self.gate == "LOCKED"
            else {1: "FORMING", 2: "READY"}.get(phase, "IDLE")
            if action == 1
            else "IDLE"
        )
        return False

    def update(
        self, landmarks, now: float, *, aspect_ratio: float = 1.0, frame_id: int | None = None
    ) -> bool:
        if not math.isfinite(now) or (self.last_time is not None and now <= self.last_time):
            raise ValueError("Learned Ramune timestamps must strictly increase")
        if not math.isfinite(aspect_ratio) or aspect_ratio <= 0:
            raise ValueError("Invalid aspect ratio")
        index = (
            frame_id
            if frame_id is not None
            else (0 if self.last_frame is None else self.last_frame + 1)
        )
        if self.last_frame is not None and index <= self.last_frame:
            raise ValueError("Learned Ramune frame IDs must strictly increase")
        skipped = 0 if self.last_frame is None else index - self.last_frame - 1
        if self.last_time is not None and (skipped or now - self.last_time > 0.5):
            # Missing time is not observed release or sustained setup.
            self.release_since = self.setup_since = None
            if self.gate == "ARMED":
                self.gate = "WAIT_SETUP"
            if self.gate == "OPENED" and now - self.last_open > self.metadata["hold_seconds"]:
                self.gate = "LOCKED"
            if now - self.last_time > 0.5:
                self.history.clear()
            for _ in range(min(skipped, max(self.windows.values()) + 1)):
                self.history.append(np.zeros(24))
        points = np.zeros((33, 3))
        if landmarks:
            if len(landmarks) != 33:
                raise ValueError("Expected 33 pose landmarks")
            points = np.array([(p.x, p.y, p.visibility) for p in landmarks], dtype=float)
            points[~np.isfinite(points).all(axis=1)] = 0
        base, geometry = current_features(points, aspect_ratio)
        self.history.append(base)
        observed = bool((points[:, 2] > 0.5).any())
        self.action = (
            self.predict(self.features(base, geometry, "action"), "action") if observed else 0
        )
        self.phase = (
            self.predict(self.features(base, geometry, "phase"), "phase") if observed else 0
        )
        self.last_time, self.last_frame = now, index
        return self.advance(self.phase, self.action, observed, now)
