import pytest

from suzukaze_gesture_protocol import FrameDecoder, MAX_MESSAGE_BYTES, frame_message


def test_every_split_and_coalesced_frames():
    payloads = [b"a", b"bc", b"x" * MAX_MESSAGE_BYTES]
    wire = b"".join(map(frame_message, payloads))
    assert wire[:4] == b"\x00\x00\x00\x01"
    for split in range(len(wire) + 1):
        decoder = FrameDecoder()
        assert decoder.feed(wire[:split]) + decoder.feed(wire[split:]) == payloads
        decoder.eof()


def test_bytewise_delivery():
    decoder = FrameDecoder()
    frames = []
    for byte in frame_message(b"hello") * 3:
        frames.extend(decoder.feed(bytes([byte])))
    assert frames == [b"hello"] * 3
    assert decoder.feed(b"") == []
    decoder.eof()
    with pytest.raises(ValueError):
        decoder.feed(b"")


@pytest.mark.parametrize("size", [0, MAX_MESSAGE_BYTES + 1, 2**32 - 1])
def test_reject_length_on_header_and_poison(size):
    decoder = FrameDecoder()
    header = size.to_bytes(4, "big")
    assert decoder.feed(header[:3]) == []
    with pytest.raises(ValueError):
        decoder.feed(header[3:])
    with pytest.raises(ValueError):
        decoder.feed(frame_message(b"ok"))


@pytest.mark.parametrize("wire", [b"\x00", b"\x00\x00\x00", b"\x00\x00\x00\x02", b"\x00\x00\x00\x02a"])
def test_partial_eof(wire):
    decoder = FrameDecoder()
    decoder.feed(wire)
    with pytest.raises(ValueError, match="Truncated"):
        decoder.eof()


@pytest.mark.parametrize("payload", [b"", b"x" * (MAX_MESSAGE_BYTES + 1)])
def test_encoder_size(payload):
    with pytest.raises(ValueError):
        frame_message(payload)
