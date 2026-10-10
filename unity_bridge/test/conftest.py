import pytest

from unity_bridge import settings


@pytest.fixture(autouse=True)
def _shared_settings_only(monkeypatch):
    # 開発者の suzukaze.local.yaml に左右されないよう、共有の suzukaze.yaml だけを読む。
    monkeypatch.setattr(settings, "CONFIG_FILES", settings.CONFIG_FILES[:1])
