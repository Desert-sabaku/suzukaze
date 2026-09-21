import json

import serial


class FanController:
    """Serial client for firmware/'s fade protocol.

    pyserial opens the port in raw mode (no canonical/echo), so unlike a
    plain `cat /dev/ttyACM0`, no `stty raw -echo` dance is needed here.
    """

    def __init__(self, port: str, baudrate: int = 115200, timeout: float = 1.0) -> None:
        self._serial = serial.serial_for_url(port, baudrate=baudrate, timeout=timeout)

    def fade(self, pin: int, value: int, duration_seconds: float) -> None:
        """Fade `pin` to `value` (0-7999) over `duration_seconds`."""
        message = {
            "pin": pin,
            "value": value,
            "duration": int(duration_seconds * 1e9),  # Go time.Duration is nanoseconds
        }
        self._serial.write((json.dumps(message) + "\n").encode("utf-8"))

    def close(self) -> None:
        self._serial.close()

    def __enter__(self) -> "FanController":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
