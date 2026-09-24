import os
from pathlib import Path
from subprocess import CompletedProcess

from gesture_detection.qt_setup import configure_qt_fonts


def test_fontconfig_fallback_uses_installed_font_directory(monkeypatch, tmp_path):
    font = tmp_path / "Example.ttf"
    font.touch()
    original_is_dir = Path.is_dir
    monkeypatch.setattr(Path, "is_dir", lambda path: path == tmp_path and original_is_dir(path))
    monkeypatch.setattr(
        "gesture_detection.qt_setup.subprocess.run",
        lambda *args, **kwargs: CompletedProcess(args[0], 0, str(font)),
    )
    monkeypatch.delenv("QT_QPA_FONTDIR", raising=False)

    configure_qt_fonts()

    assert os.environ["QT_QPA_FONTDIR"] == str(tmp_path)
