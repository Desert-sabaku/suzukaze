import argparse

from .client import FanController


def main() -> None:
    parser = argparse.ArgumentParser(description="Send a single fade command to the fan controller firmware.")
    parser.add_argument("--port", required=True, help="Serial port, e.g. /dev/ttyACM0 or COM3")
    parser.add_argument("--pin", type=int, required=True)
    parser.add_argument("--value", type=int, required=True, help="Target PWM value (0-7999)")
    parser.add_argument("--duration", type=float, required=True, help="Fade duration in seconds")
    parser.add_argument("--baudrate", type=int, default=115200)
    args = parser.parse_args()

    with FanController(args.port, baudrate=args.baudrate) as fan:
        fan.fade(pin=args.pin, value=args.value, duration_seconds=args.duration)


if __name__ == "__main__":
    main()
