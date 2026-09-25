import sys
from pathlib import Path

# mcu/gen ディレクトリをモジュール検索パスに追加
_gen_path = str(Path(__file__).parent / "gen")
if _gen_path not in sys.path:
  sys.path.insert(0, _gen_path)

from .client import MCUClient  # noqa: E402

__all__ = ["MCUClient"]
