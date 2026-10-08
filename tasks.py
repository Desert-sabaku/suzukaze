"""Invoke tasks for the Suzukaze workspace."""

import os
import subprocess
import sys
import time
from pathlib import Path

from invoke.context import Context
from invoke.exceptions import Exit
from invoke.tasks import task

UNITY_PROJECT = Path(__file__).resolve().parent / "suzukaze"
UNITY_BUILD_METHOD = "Suzukaze.Build.Editor.PlayerBuilder.BuildFromCommandLine"
# invoke-side name -> Unity's -buildTarget value
UNITY_BUILD_TARGETS = {
    "win64": "Win64",
    "linux64": "Linux64",
    "osx": "OSXUniversal",
}


def _run_package(c: Context, directory: str, command: str):
    with c.cd(directory):
        c.run(f"uv run {command}")


@task
def proto(c: Context):
    """Generate protobuf sources."""
    with c.cd("proto"):
        c.run("buf generate")


@task
def gesture(c: Context):
    """Run gesture detection."""
    _run_package(c, "", "gesture-detection")


@task
def annotate_landmarks(c: Context):
    """Annotate landmarks in a gesture-detection input."""
    _run_package(c, "", "annotate-landmarks")


@task
def annotate(c: Context, video_path: str):
    """Annotate a gesture-detection video."""
    _run_package(c, "", f"annotate-video {video_path}")


@task
def record_cameras(c: Context):
    """Record from the configured cameras."""
    _run_package(c, "", "record-cameras")


@task
def record_three_cameras(c: Context):
    """Record from three cameras."""
    _run_package(c, "", "record-three-cameras")


@task
def unity(c: Context):
    """Start the Unity bridge with gesture detection."""
    _run_package(c, "unity_bridge", "unity-bridge --gesture")


@task
def unity_debug(c: Context):
    """Start the Unity bridge with the browser gesture debug GUI."""
    _run_package(c, "unity_bridge", "unity-bridge --debug-gui")


def _unity_editor_version() -> str:
    version_file = UNITY_PROJECT / "ProjectSettings" / "ProjectVersion.txt"
    for line in version_file.read_text(encoding="utf-8").splitlines():
        if line.startswith("m_EditorVersion:"):
            return line.split(":", 1)[1].strip()
    raise Exit(f"m_EditorVersion not found in {version_file}")


def _find_unity_editor(version: str) -> Path:
    """Return the Unity Hub install of `version`, or `UNITY_EDITOR` if set."""
    if override := os.environ.get("UNITY_EDITOR"):
        return Path(override)
    if sys.platform == "win32":
        hub = (
            Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Unity" / "Hub"
        )
        candidate = hub / "Editor" / version / "Editor" / "Unity.exe"
    elif sys.platform == "darwin":
        candidate = Path(
            f"/Applications/Unity/Hub/Editor/{version}/Unity.app/Contents/MacOS/Unity"
        )
    else:
        candidate = (
            Path.home() / "Unity" / "Hub" / "Editor" / version / "Editor" / "Unity"
        )
    if not candidate.exists():
        raise Exit(
            f"Unity {version} not found at {candidate}. "
            "Install it with Unity Hub or set UNITY_EDITOR to the editor executable."
        )
    return candidate


def _default_unity_build_target() -> str:
    if sys.platform == "win32":
        return "win64"
    if sys.platform == "darwin":
        return "osx"
    return "linux64"


@task(
    help={
        "target": f"Build target: {', '.join(UNITY_BUILD_TARGETS)} (default: host OS).",
        "output": "Player path (default: suzukaze/Builds/<BuildTarget>/<productName>).",
        "development": "Make a development build.",
        "log": "Unity log file, also echoed to the terminal (default: suzukaze/Logs/build.log).",
    }
)
def unity_build(
    c: Context,
    target: str = "",
    output: str = "",
    development: bool = False,
    log: str = "",
):
    """Build the Unity player in batch mode. Close the project in the Editor first."""
    target = target or _default_unity_build_target()
    if target not in UNITY_BUILD_TARGETS:
        raise Exit(
            f"Unknown target {target!r}; choose from {', '.join(UNITY_BUILD_TARGETS)}."
        )

    generated = UNITY_PROJECT / "Assets" / "Bridge" / "Generated"
    if not any(generated.glob("*.cs")):
        raise Exit("Protobuf bindings are missing; run `invoke proto` first.")
    _ensure_unity_project_closed()

    log_path = Path(log).resolve() if log else UNITY_PROJECT / "Logs" / "build.log"

    args = [
        str(_find_unity_editor(_unity_editor_version())),
        "-batchmode",
        "-nographics",
        "-projectPath",
        str(UNITY_PROJECT),
        "-buildTarget",
        UNITY_BUILD_TARGETS[target],
        "-executeMethod",
        UNITY_BUILD_METHOD,
        "-logFile",
        str(log_path),
    ]
    if output:
        args += ["-suzukazeOutput", str(Path(output).resolve())]
    if development:
        args.append("-suzukazeDevelopment")

    print("Running:", subprocess.list2cmdline(args), flush=True)
    returncode = _run_and_follow_log(args, log_path)
    if returncode != 0:
        raise Exit(
            f"Unity build failed (exit code {returncode}). See {log_path}.", returncode
        )
    print(f"Unity build succeeded. Log: {log_path}")


def _ensure_unity_project_closed() -> None:
    """Fail early when the Editor holds the project lock (detectable on Windows)."""
    lockfile = UNITY_PROJECT / "Temp" / "UnityLockfile"
    if sys.platform != "win32" or not lockfile.exists():
        return
    try:
        with lockfile.open("a"):
            pass
    except PermissionError:
        raise Exit(
            "The Unity project is open in the Editor. Close it and try again."
        ) from None


def _run_and_follow_log(args: list[str], log_path: Path) -> int:
    """Run Unity and echo its log file, since Unity.exe on Windows has no console."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.unlink(missing_ok=True)
    process = subprocess.Popen(args)
    position = 0
    while True:
        returncode = process.poll()
        if log_path.exists():
            with log_path.open(encoding="utf-8", errors="replace") as log:
                log.seek(position)
                sys.stdout.write(log.read())
                sys.stdout.flush()
                position = log.tell()
        if returncode is not None:
            return returncode
        time.sleep(0.5)


@task
def unity_probe(c: Context):
    """Run the Unity bridge gesture probe."""
    _run_package(c, "unity_bridge", "unity-gesture-probe")


@task
def mcu(c: Context):
    """Run the microcontroller CLI."""
    _run_package(c, "mcu", "mcu")


@task
def gesture_tests(c: Context):
    """Run gesture-detection tests."""
    _run_package(c, "", "python -m pytest")


@task
def unity_tests(c: Context):
    """Run Unity bridge tests."""
    _run_package(c, "unity_bridge", "python -m pytest")


@task
def mcu_tests(c: Context):
    """Run microcontroller library tests."""
    _run_package(c, "mcu", "python -m pytest")


@task
def format(c: Context):
    """Format all Python projects."""
    for package in ("", "unity_bridge", "mcu"):
        with c.cd(package):
            c.run("uv run ruff format")


@task
def lint(c: Context):
    """Lint all Python projects."""
    for package in ("", "unity_bridge", "mcu"):
        with c.cd(package):
            c.run("uv run ruff check")


@task
def typecheck(c: Context):
    """Type-check all Python projects."""
    for package in ("", "unity_bridge", "mcu"):
        with c.cd(package):
            c.run("uv run pyright")
