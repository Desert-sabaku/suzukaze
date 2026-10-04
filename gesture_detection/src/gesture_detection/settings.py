"""Read the optional, project-local TOML settings with strict key and type checks."""

import math
import tomllib
from pathlib import Path
from typing import Any


class Settings:
    def __init__(self, root: Path, filename: Path, *, required: bool = False) -> None:
        self.root = root
        self.filename = filename
        if required and not filename.is_file():
            raise FileNotFoundError(f"Settings file does not exist: {filename}")
        self.data = (
            tomllib.loads(filename.read_text(encoding="utf-8")) if filename.is_file() else {}
        )
        self.used: set[tuple[str, ...]] = set()

    def get(self, section: str, key: str, default: Any) -> Any:
        parts = (*section.split("."), key)
        table: Any = self.data
        for part in parts[:-1]:
            table = table.get(part, {})
            if not isinstance(table, dict):
                raise ValueError(f"{'.'.join(parts[:-1])} must be a TOML table")
        self.used.add(parts)
        return table.get(key, default)

    def boolean(self, section: str, key: str, default: bool) -> bool:
        value = self.get(section, key, default)
        if type(value) is not bool:
            raise ValueError(f"{section}.{key} must be a boolean")
        return value

    def integer(self, section: str, key: str, default: int) -> int:
        value = self.get(section, key, default)
        if type(value) is not int:
            raise ValueError(f"{section}.{key} must be an integer")
        return value

    def number(self, section: str, key: str, default: float) -> float:
        value = self.get(section, key, default)
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError(f"{section}.{key} must be a finite number")
        return float(value)

    def text(self, section: str, key: str, default: str) -> str:
        value = self.get(section, key, default)
        if not isinstance(value, str):
            raise ValueError(f"{section}.{key} must be a string")
        return value

    def path(self, section: str, key: str, default: str) -> Path:
        value = Path(self.text(section, key, default)).expanduser()
        return value if value.is_absolute() else self.root / value

    def optional_path(self, section: str, key: str) -> Path | None:
        value = self.text(section, key, "")
        if not value:
            return None
        path = Path(value).expanduser()
        return path if path.is_absolute() else self.root / path

    def finish(self) -> None:
        def check(table: dict[str, Any], prefix: tuple[str, ...] = ()) -> None:
            for key, value in table.items():
                path = (*prefix, key)
                if isinstance(value, dict):
                    if not any(used[: len(path)] == path for used in self.used):
                        raise ValueError(f"Unknown setting: {'.'.join(path)}")
                    check(value, path)
                elif path not in self.used:
                    raise ValueError(f"Unknown setting: {'.'.join(path)}")

        check(self.data)
