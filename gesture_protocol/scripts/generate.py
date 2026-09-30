"""Run with uv run --locked python scripts/generate.py from gesture_protocol."""

from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "gesture_protocol/src/suzukaze_gesture_protocol/generated"
CSHARP = ROOT / "suzukaze/Assets/GestureDelivery/Generated"
protoc = shutil.which("protoc")
if protoc is None:
    raise SystemExit("Run uv sync --locked first")
version = subprocess.check_output([protoc, "--version"], text=True).strip()
if version != "libprotoc 30.2":
    raise SystemExit(f"Expected libprotoc 30.2, got {version}")
CSHARP.mkdir(parents=True, exist_ok=True)
subprocess.run([
    protoc, f"--proto_path={ROOT / 'proto'}", f"--python_out={PACKAGE}",
    f"--pyi_out={PACKAGE}", f"--csharp_out={CSHARP}",
    "gesture/v1/gesture.proto",
], check=True)
# protoc assumes its output directory is on sys.path. Qualify its Python
# module identity for our installed package (also makes pickling work).
# The schema descriptor name and serialized descriptor remain untouched.
module = PACKAGE / "gesture/v1/gesture_pb2.py"
text = module.read_text()
old = "'gesture.v1.gesture_pb2'"
assert text.count(old) == 1
module.write_text(text.replace(
    old, "'suzukaze_gesture_protocol.generated.gesture.v1.gesture_pb2'"
))
