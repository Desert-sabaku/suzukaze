"""OpenCV HighGUI environment fixes shared by the camera and annotation apps."""

import os
import subprocess
from pathlib import Path


def configure_qt_fonts() -> None:
    """Restore a system font directory after importing the OpenCV wheel."""
    for directory in (
        Path("/usr/share/fonts/truetype/dejavu"),
        Path("/usr/share/fonts/truetype/noto"),
        Path("/usr/share/fonts/truetype"),
    ):
        if directory.is_dir():
            os.environ["QT_QPA_FONTDIR"] = str(directory)
            return
    try:
        font_file = subprocess.run(
            ["fc-match", "-f", "%{file}"],
            capture_output=True,
            check=True,
            text=True,
            timeout=2,
        ).stdout.strip()
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return
    if font_file and Path(font_file).is_file():
        os.environ["QT_QPA_FONTDIR"] = str(Path(font_file).parent)
