import argparse

from mcu.gen.comms.v1.log_pb2 import LogEntry

from .client import MCUClient, _local_version


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True, help="Serial port, e.g. /dev/ttyACM0 or COM3")
    parser.add_argument("--baudrate", type=int, default=115200)
    args = parser.parse_args()

    with MCUClient(args.port, baudrate=args.baudrate) as client:
        resp = client.handshake()
        if resp.matched:
            print(f"handshake ok (schema={resp.controller_version.schema_hash})")  # noqa: T201
        else:
            print(  # noqa: T201
                f"schema mismatch: controller={resp.controller_version.schema_hash} "
                f"client={_local_version().schema_hash}",
            )

        def on_log(log_entry: LogEntry) -> None:
            print(log_entry)  # noqa: T201

        client.on_log = on_log

        client.start_listening()

if __name__ == "__main__":
    main()
