"""OpenCV HighGUI environment fixes shared by the camera and annotation apps."""

import os
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
            break
