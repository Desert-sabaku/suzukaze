import sys
from pathlib import Path

# 生成コードは `from fan.v1 import ...` と絶対 import するため、gen を検索パスに入れる(mcu と同じ)。
_gen_path = str(Path(__file__).parent / "gen")
if _gen_path not in sys.path:
    sys.path.insert(0, _gen_path)
