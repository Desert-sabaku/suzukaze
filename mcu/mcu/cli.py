import argparse
import os
import threading

import questionary
from prompt_toolkit.patch_stdout import patch_stdout

from mcu.gen.comms.v1.log_pb2 import LogEntry

from .client import MCUClient, _local_version


def _listen(client: MCUClient) -> None:
    try:
        client.start_listening()
    except Exception as e:  # noqa: BLE001 ログスレッドが死んだらプロンプトだけ残るゾンビ状態を避ける
        print(f"log listener died: {e}")  # noqa: T201
        os._exit(1)


def _is_uint(v: str, max_value: int | None = None) -> bool:
    return v.isdigit() and (max_value is None or int(v) <= max_value)


def _fade_prompt(client: MCUClient) -> None:
    pin = questionary.text("pin", validate=_is_uint).ask()
    if pin is None:
        return

    value = questionary.text("value (0-255)", validate=lambda v: _is_uint(v, 255)).ask()
    if value is None:
        return

    duration_ms = questionary.text("duration_ms", validate=_is_uint).ask()
    if duration_ms is None:
        return

    client.send_fade(int(pin), int(value), int(duration_ms))


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
        threading.Thread(target=_listen, args=(client,), daemon=True).start()

        with patch_stdout():
            while True:
                command = questionary.select("command", choices=["fade", "quit"]).ask()
                if command is None or command == "quit":
                    break

                _fade_prompt(client)

if __name__ == "__main__":
    main()
