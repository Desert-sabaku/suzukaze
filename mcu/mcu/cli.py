import argparse

from mcu.gen.comms.v1.log_pb2 import LogEntry

from .client import MCUClient


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True, help="Serial port, e.g. /dev/ttyACM0 or COM3")
    parser.add_argument("--baudrate", type=int, default=115200)
    args = parser.parse_args()

    with MCUClient(args.port, baudrate=args.baudrate) as client:
        def on_log(log_entry: LogEntry) -> None:
            print(log_entry)

        client.on_log = on_log

        client.start_listening()

if __name__ == "__main__":
    main()
