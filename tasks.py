"""Invoke tasks for the Suzukaze workspace."""

from invoke.tasks import task


def _run_package(c, directory, command):
    with c.cd(directory):
        c.run(f"uv run {command}")


@task
def proto(c):
    """Generate protobuf sources."""
    with c.cd("proto"):
        c.run("buf generate")


@task
def gesture(c):
    """Run gesture detection."""
    _run_package(c, "", "gesture-detection")


@task
def annotate_landmarks(c):
    """Annotate landmarks in a gesture-detection input."""
    _run_package(c, "", "annotate-landmarks")


@task
def annotate_video(c, video_path: str):
    """Annotate a gesture-detection video."""
    _run_package(c, "", f"annotate-video {video_path}")


@task
def record_cameras(c):
    """Record from the configured cameras."""
    _run_package(c, "", "record-cameras")


@task
def record_three_cameras(c):
    """Record from three cameras."""
    _run_package(c, "", "record-three-cameras")


@task
def unity(c):
    """Start the Unity bridge with gesture detection."""
    _run_package(c, "unity_bridge", "unity-bridge --gesture")


@task
def unity_probe(c):
    """Run the Unity bridge gesture probe."""
    _run_package(c, "unity_bridge", "unity-gesture-probe")


@task
def mcu(c):
    """Run the microcontroller CLI."""
    _run_package(c, "mcu", "mcu")


@task
def gesture_tests(c):
    """Run gesture-detection tests."""
    _run_package(c, "", "python -m pytest")


@task
def unity_tests(c):
    """Run Unity bridge tests."""
    _run_package(c, "unity_bridge", "python -m pytest")


@task
def mcu_tests(c):
    """Run microcontroller library tests."""
    _run_package(c, "mcu", "python -m pytest")


@task
def format(c):
    """Format all Python projects."""
    for package in ("", "unity_bridge", "mcu"):
        with c.cd(package):
            c.run("uv run ruff format")


@task
def lint(c):
    """Lint all Python projects."""
    for package in ("", "unity_bridge", "mcu"):
        with c.cd(package):
            c.run("uv run ruff check")


@task
def typecheck(c):
    """Type-check all Python projects."""
    for package in ("", "unity_bridge", "mcu"):
        with c.cd(package):
            c.run("uv run pyright")
