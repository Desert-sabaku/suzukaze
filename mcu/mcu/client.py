import hashlib
import struct
import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING, Self

import serial

from mcu.gen.micon.v1.heartbeat_pb2 import HandshakeReq, VersionInfo
from mcu.gen.micon.v1.micon_pb2 import Packet
from mcu.gen.micon.v1.pwm_pb2 import PwmFade

if TYPE_CHECKING:
    from collections.abc import Callable

    from mcu.gen.micon.v1.heartbeat_pb2 import HandshakeResp
    from mcu.gen.micon.v1.log_pb2 import LogEntry

# firmware/Makefile の SCHEMA_HASH と同じ手順(proto/micon/v1/*.protoの内容をsha256)で
# スキーマの一致を確認するため、リポジトリ内の proto/ を相対パスで参照する。
PROTO_DIR = Path(__file__).resolve().parents[2] / "proto" / "micon" / "v1"


def _local_version() -> VersionInfo:
    proto_bytes = b"".join(p.read_bytes() for p in sorted(PROTO_DIR.glob("*.proto")))
    schema_hash = hashlib.sha256(proto_bytes).hexdigest()[:8]

    commit_hash = subprocess.run(
        ["git", "describe", "--always", "--dirty"],  # noqa: S607
        cwd=PROTO_DIR,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    return VersionInfo(schema_hash=schema_hash, commit_hash=commit_hash)


class SerialTimeoutError(Exception):
    pass


class PacketParseError(Exception):
    pass


class MCUClient:
    MAGIC_HEADER = bytes([ord("S"), ord("Z"), 0xAA, 0x55])

    def __init__(self, url: str, baudrate: int = 115200, timeout: float = 1.0) -> None:
        self.url = url
        self.baudrate = baudrate
        self.timeout = timeout
        self.ser: serial.SerialBase | None = None
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
        self.ser = serial.serial_for_url(self.url, baudrate=self.baudrate, timeout=self.timeout)

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

    def send_packet(self, pkt: Packet) -> None:
        """firmware/cmd/packet.go の SendPacket と同じフレーミングで書き込む."""
        if not self.ser or not self.ser.is_open:
            msg = "Port is not open"
            raise SerialTimeoutError(msg)

        payload = pkt.SerializeToString()
        header = self.MAGIC_HEADER + struct.pack(">H", len(payload))
        self.ser.write(header + payload)

    def handshake(self, timeout: float = 2.0) -> "HandshakeResp":
        """HandshakeReqを送り、HandshakeRespが返るまで待つ."""
        self.send_packet(Packet(handshake_req=HandshakeReq(client_version=_local_version())))

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            pkt = self.read_packet()
            if pkt and pkt.WhichOneof("payload") == "handshake_resp":
                return pkt.handshake_resp

        msg = "Handshake timed out"
        raise SerialTimeoutError(msg)

    def send_fade(self, pin: int, value: int, duration_ms: int) -> None:
        """PwmFadeを送る. valueは0-255(ファームウェア側で内部分解能にスケールする)."""
        self.send_packet(
            Packet(pwm_fade=PwmFade(pin=pin, value=value, duration_ms=duration_ms)),
        )

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
            print("Stopping listening...")  # noqa: T201
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
