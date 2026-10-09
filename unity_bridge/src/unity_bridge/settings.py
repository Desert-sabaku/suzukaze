"""設定。環境変数 > suzukaze.local.yaml > suzukaze.yaml の順。既定値はない。

どれにも書かれていないキーや、yaml にある未知のキーは ValidationError になる。
yaml のキーはフィールド名、環境変数名はその大文字(例: fan_pwm_pins / FAN_PWM_PINS)。
ピンの一覧は、yaml では配列、環境変数ではカンマ区切りで書く(空なら空の一覧)。
"""

from pathlib import Path
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import (
    BaseSettings,
    NoDecode,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

_ROOT = Path(__file__).resolve().parents[3]
# 後ろのファイルが前のファイルを上書きする。local はマシンごとの違い用(コミットしない)。
CONFIG_FILES = (_ROOT / "suzukaze.yaml", _ROOT / "suzukaze.local.yaml")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="forbid")

    unity_websocket_host: str
    unity_websocket_port: int
    unity_websocket_test_host: str

    microcontroller_serial_port: str
    microcontroller_baudrate: int

    fan_pwm_pins: Annotated[list[int], NoDecode]
    diffuser_pins: Annotated[list[int], NoDecode]

    gesture_state_interval: float
    gesture_stale_timeout: float
    gesture_event_ttl: float
    gesture_retry_interval: float
    gesture_max_pending: int
    gesture_debug_port: int

    @field_validator("fan_pwm_pins", "diffuser_pins", mode="before")
    @classmethod
    def _split_pins(cls, value: object) -> object:
        if isinstance(value, str):
            return [int(pin) for pin in value.split(",") if pin.strip()]
        return value

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
        return (
            init_settings,
            env_settings,
            YamlConfigSettingsSource(settings_cls, yaml_file=CONFIG_FILES),
        )


def load_settings() -> Settings:
    return Settings()  # pyright: ignore[reportCallIssue]
