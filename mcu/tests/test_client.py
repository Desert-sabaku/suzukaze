import struct

from mcu.client import MCUClient
from micon.v1.heartbeat_pb2 import HandshakeResp, VersionInfo
from micon.v1.micon_pb2 import Packet


def test_send_packet_writes_framed_bytes() -> None:
    with MCUClient("loop://") as client:
        pkt = Packet(handshake_resp=HandshakeResp(uptime_ms=123, matched=True))
        client.send_packet(pkt)

        header = client.read_exact(4)
        (length,) = struct.unpack(">H", client.read_exact(2))
        payload = client.read_exact(length)

        assert header == MCUClient.MAGIC_HEADER
        received = Packet()
        received.ParseFromString(payload)
        assert received == pkt


def test_handshake_returns_matching_response() -> None:
    with MCUClient("loop://") as client:
        resp_pkt = Packet(
            handshake_resp=HandshakeResp(
                controller_version=VersionInfo(schema_hash="a28de0fe", commit_hash="dev"),
                uptime_ms=42,
                matched=True,
            ),
        )
        payload = resp_pkt.SerializeToString()
        assert client.ser is not None
        client.ser.write(MCUClient.MAGIC_HEADER + struct.pack(">H", len(payload)) + payload)

        resp = client.handshake()

        assert resp.matched is True
        assert resp.controller_version.schema_hash == "a28de0fe"
        assert resp.uptime_ms == 42
