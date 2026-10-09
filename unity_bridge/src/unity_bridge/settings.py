"""設定。suzukaze.local.yaml > suzukaze.yaml の順。既定値はない。

どれにも書かれていないキーや、yaml にある未知のキーは ValidationError になる。
yaml のキーはフィールド名。ピンの一覧は、yaml の配列で書く。
fan_pwm_pins は 6本、diffuser_pins は 2本で、ピンの重複があると ValidationError になる。
"""

from pathlib import Path

from pydantic import model_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

_ROOT = Path(__file__).resolve().parents[3]
# 後ろのファイルが前のファイルを上書きする。local はマシンごとの違い用(コミットしない)。
CONFIG_FILES = (_ROOT / "suzukaze.yaml", _ROOT / "suzukaze.local.yaml")

# ファン(channel 1〜6)とディフューザー(DiffuserChannel の値の数)の本数。
FAN_COUNT = 6
DIFFUSER_COUNT = 2


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="forbid")

    unity_websocket_host: str
    unity_websocket_port: int
    unity_websocket_test_host: str

    microcontroller_serial_port: str
    microcontroller_baudrate: int

    fan_pwm_pins: list[int]
    diffuser_pins: list[int]

    gesture_state_interval: float
    gesture_stale_timeout: float
    gesture_event_ttl: float
    gesture_retry_interval: float
    gesture_max_pending: int
    gesture_debug_port: int

    @model_validator(mode="after")
    def _check_pins(self) -> Settings:
        for name, count in (
            ("fan_pwm_pins", FAN_COUNT),
            ("diffuser_pins", DIFFUSER_COUNT),
        ):
            pins = getattr(self, name)
            if len(pins) != count:
                raise ValueError(f"{name} must have {count} pins, got {len(pins)}")
            if len(set(pins)) != len(pins):
                raise ValueError(f"{name} has duplicate pins: {pins}")
        return self

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # 先のものが優先。CONFIG_FILES は呼び出し時に読む(テストで差し替える)。
        # 環境変数は読まない(env_settings などは捨てる)。
        return (
            init_settings,
            YamlConfigSettingsSource(settings_cls, yaml_file=CONFIG_FILES),
        )


def load_settings() -> Settings:
    return Settings()  # pyright: ignore[reportCallIssue]
