"""設定。suzukaze.local.yaml > suzukaze.yaml の順。既定値はない。

どれにも書かれていないキーや、yaml にある未知のキーは ValidationError になる。
yaml のキーはフィールド名。ピンは、機器の名前(left_back など)をキーにして書く。
ピンのキーが足りないときと、ピンが重複するときも ValidationError になる。
"""

from pathlib import Path

from pydantic import BaseModel, ConfigDict, model_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

_ROOT = Path(__file__).resolve().parents[3]
# 後ろのファイルが前のファイルを上書きする。local はマシンごとの違い用(コミットしない)。
CONFIG_FILES = (_ROOT / "suzukaze.yaml", _ROOT / "suzukaze.local.yaml")


class _Pins(BaseModel):
    model_config = ConfigDict(extra="forbid")

    def ordered(self) -> tuple[int, ...]:
        """フィールドの宣言順(= channel の1から順)のピン番号。"""
        return tuple(self.model_dump().values())

    @model_validator(mode="after")
    def _check_unique(self) -> _Pins:
        pins = self.ordered()
        if len(set(pins)) != len(pins):
            raise ValueError(f"duplicate pins: {pins}")
        return self


class FanPins(_Pins):
    # FanChannel の1〜6の順。
    left_back: int
    left_side: int
    left_front: int
    right_back: int
    right_side: int
    right_front: int


class DiffuserPins(_Pins):
    # DiffuserChannel の1〜2の順。
    ramune: int
    forest: int


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="forbid")

    unity_websocket_host: str
    unity_websocket_port: int
    unity_websocket_test_host: str

    microcontroller_serial_port: str
    microcontroller_baudrate: int

    fan_pwm_pins: FanPins
    diffuser_pins: DiffuserPins

    gesture_state_interval: float
    gesture_stale_timeout: float
    gesture_event_ttl: float
    gesture_retry_interval: float
    gesture_max_pending: int
    gesture_debug_port: int

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
