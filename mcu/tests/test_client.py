import json

from mcu import FanController


def test_fade_writes_one_json_line():
    with FanController("loop://") as controller:
        controller.fade(pin=25, value=4000, duration_seconds=1.0)

        line = controller._serial.readline()
        message = json.loads(line)

    assert message == {"pin": 25, "value": 4000, "duration": 1_000_000_000}
