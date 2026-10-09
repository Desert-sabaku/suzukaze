"""Settings changed from the admin page and sent to Unity.

Unity owns the settings it applies; the bridge keeps the last requested values,
saves them to a JSON file so they survive a restart, and resends them whenever
Unity connects.
"""

import json
import math
import threading
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

from bridge.v1 import bridge_pb2

MAX_TIME_SCALE_MULTIPLIER = 100.0


@dataclass(frozen=True)
class RuntimeSettings:
    diffuser_enabled: bool = True
    # GameSettings.timeScale に掛ける倍率。
    time_scale_multiplier: float = 1.0

    def to_proto(self) -> bridge_pb2.RuntimeSettings:
        return bridge_pb2.RuntimeSettings(
            diffuser_enabled=self.diffuser_enabled,
            time_scale_multiplier=self.time_scale_multiplier,
        )

    def with_fields(self, fields: dict[str, Any]) -> RuntimeSettings:
        """Return a copy with the given fields; raise ValueError if invalid."""
        unknown = set(fields) - set(asdict(self))
        if unknown:
            raise ValueError(f"Unknown settings: {', '.join(sorted(unknown))}")
        changed = replace(self, **fields)
        if type(changed.diffuser_enabled) is not bool:
            raise ValueError("diffuser_enabled must be bool")
        multiplier = changed.time_scale_multiplier
        if (
            not isinstance(multiplier, int | float)
            or isinstance(multiplier, bool)
            or not math.isfinite(multiplier)
            or not 0 <= multiplier <= MAX_TIME_SCALE_MULTIPLIER
        ):
            raise ValueError(
                f"time_scale_multiplier must be in [0, {MAX_TIME_SCALE_MULTIPLIER:g}]"
            )
        return replace(changed, time_scale_multiplier=float(multiplier))


class SettingsStore:
    """The latest settings and a version that increases on every change."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._settings = self._load()
        self._version = 1

    @property
    def current(self) -> RuntimeSettings:
        with self._lock:
            return self._settings

    @property
    def version(self) -> int:
        with self._lock:
            return self._version

    def update(self, fields: dict[str, Any]) -> RuntimeSettings:
        """Apply and save the given fields; raise ValueError if invalid."""
        with self._lock:
            self._settings = self._settings.with_fields(fields)
            self._version += 1
            settings = self._settings
        self._save(settings)
        return settings

    def _load(self) -> RuntimeSettings:
        if self._path is None or not self._path.exists():
            return RuntimeSettings()
        try:
            return RuntimeSettings().with_fields(json.loads(self._path.read_text()))
        except (OSError, ValueError, TypeError) as error:
            print(f"Ignoring saved settings {self._path}: {error}", flush=True)
            return RuntimeSettings()

    def _save(self, settings: RuntimeSettings) -> None:
        if self._path is None:
            return
        try:
            self._path.write_text(json.dumps(asdict(settings), indent=2) + "\n")
        except OSError as error:
            print(f"Could not save settings to {self._path}: {error}", flush=True)
