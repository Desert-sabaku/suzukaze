import struct
from typing import TYPE_CHECKING, Self

import serial

from mcu.gen.comms.v1.comms_pb2 import Packet

if TYPE_CHECKING:
    from collections.abc import Callable

    from mcu.gen.comms.v1.log_pb2 import LogEntry


class SerialTimeoutError(Exception):
    pass


class PacketParseError(Exception):
    pass


class MCUClient:
    MAGIC_HEADER = bytes([ord("S"), ord("Z"), 0xAA, 0x55])

    def __init__(self, port: str, baudrate: int = 115200, timeout: float = 1.0) -> None:
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.ser: serial.Serial | None = None
        self.on_log: Callable[[LogEntry], None] | None = None

    def read_exact(self, size: int) -> bytes:
        if not self.ser or not self.ser.is_open:
            msg = "Port is not open"
            raise SerialTimeoutError(msg)

        buf = self.ser.read(size)
        if len(buf) < size:
            msg = f"Expected {size} bytes, got {len(buf)} bytes"
            raise SerialTimeoutError(msg)

        return buf

    def connect(self) -> None:
        """シリアルポートを開く."""
        self.ser = serial.Serial(self.port, self.baudrate, timeout=self.timeout)

    def sync_header(self) -> bytes:
        buf = bytearray()
        header_len = len(self.MAGIC_HEADER)

        while True:
            byte = self.read_exact(1)
            buf.append(byte[0])

            # ヘッダーの長さを超えたぶんを捨てる
            if len(buf) > header_len:
                buf.pop(0)

            # ヘッダーと一致するか確認
            if buf == self.MAGIC_HEADER:
                break

        return bytes(buf)

    def read_packet(self) -> Packet | None:
        try:
            self.sync_header()
        except SerialTimeoutError:
            return None

        try:
            len_buf = self.read_exact(2)
            (length,) = struct.unpack(">H", len_buf)

            payload = self.read_exact(length)

            pkt = Packet()
        except SerialTimeoutError as e:
            msg = "Failed to read packet"
            raise PacketParseError(msg) from e

        try:
            pkt.ParseFromString(payload)
        except Exception as e:
            msg = "Failed to parse packet"
            raise PacketParseError(msg) from e
        else:
            return pkt

    def start_listening(self) -> None:
        try:
            while True:
                pkt = self.read_packet()
                if not pkt:
                    continue

                payload_type = pkt.WhichOneof("payload")

                match payload_type:
                    case "log_entry":
                        if self.on_log:
                            self.on_log(pkt.log_entry)

                continue
        except KeyboardInterrupt:
            print("Stopping listening...")
        finally:
            self.close()

    def close(self) -> None:
        if self.ser and self.ser.is_open:
            self.ser.close()

    def __enter__(self) -> Self:
        self.connect()

        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
