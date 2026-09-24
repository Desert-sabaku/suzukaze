import os

from gesture_detection.native_logging import suppress_native_stderr


def test_suppress_native_stderr_hides_file_descriptor_writes(capfd):
    with suppress_native_stderr():
        os.write(2, b"hidden native warning\n")

    os.write(2, b"visible error\n")
    assert capfd.readouterr().err == "visible error\n"


def test_suppress_native_stderr_can_be_disabled(capfd):
    with suppress_native_stderr(enabled=False):
        os.write(2, b"visible diagnostic\n")

    assert capfd.readouterr().err == "visible diagnostic\n"
