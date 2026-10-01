# Suzukaze gesture protocol

Standalone Python >=3.12 distribution `suzukaze-gesture-protocol` (0.1.0).
Runtime dependency: `protobuf==6.33.5`. Wire protocol version: **1**.
No application, camera, socket, or MCU dependencies.

```python
from suzukaze_gesture_protocol import (
    encode_message, decode_message, frame_message, FrameDecoder,
    MAX_MESSAGE_BYTES,
)

message = dict(version=1, type="ack", session_id="example",
               event_id=1, status="accepted")
payload = encode_message(message)
decoder = FrameDecoder()
assert decode_message(decoder.feed(frame_message(payload))[0]) == message
decoder.eof()
```

## Dictionary and wire contract

The schema is `../proto/gesture/v1/gesture.proto`. `GestureEnvelope` contains
`version`, a nonempty `session_id`, and exactly one `state`, `event`, or `ack`.
The Python API uses **flat** dictionaries with `type` selecting that payload:

* state: `sequence`, `sent_at`, `stale_timeout`, `fresh`, `gesture`, `tracking`,
  `observed_at`, `frame_id`, `source_timestamp`.
* event: `event_id`, `gesture`, `occurred_at`, `expires_at`, `frame_id`,
  `source_timestamp`.
* ack: `event_id`, `status`.

Continuous gesture strings: `NONE`, `FANNING`, `RELAXING`. Occurrences:
`RAMUNE`, `UCHIMIZU`. Ack status strings: `accepted`, `ignored`, `expired`,
`duplicate` (lowercase, matching existing application dictionaries).
Schema enum zero/unknown values are invalid. Sequence/event IDs are positive
uint64; frame IDs are uint64 including zero. Booleans must be actual bools.
Times must be finite; stale timeout is positive and expiry follows occurrence.
No wall-clock freshness or cross-message/session ordering is enforced here.

Optional metadata can be omitted or `None`; decoding always returns its keys
with `None` when absent. Explicit zero remains present on the wire. Required
dictionary keys cannot be omitted. Unknown dictionary keys are rejected;
unknown protobuf fields are tolerated. Proto3 scalar defaults cannot be
distinguished from explicit zero/false on decode. Invalid messages raise
`ValueError`; non-bytes transport inputs raise `TypeError`.

`encode_message(dict) -> bytes` and `decode_message(bytes) -> dict` enforce
`MAX_MESSAGE_BYTES = 8192` (payload only). `frame_message(bytes) -> bytes`
adds a four-byte big-endian length. `FrameDecoder.feed(bytes) -> list[bytes]`
handles arbitrary splits/coalescing, rejecting zero or oversized lengths as
soon as the header is complete, buffering at most one bounded frame.
`eof()` closes the decoder and raises on partial headers/payloads. A decoder
cannot be reused after EOF or an invalid length; discard the connection.
Framing validates lengths only, so pass each returned payload to the codec.

## Reproduce, test, build

From `gesture_protocol/`:

```sh
uv sync --locked
uv run --locked pytest
uv run --locked python -m compileall src
uv build --wheel
```

The Python bindings under `generated/` are checked in and no longer
regenerated here; this package is scheduled for removal. Do not add the
`generated/` directory to sys.path or copy/register a second generated module.

C# bindings are generated with buf from `../proto`
(`buf generate --template buf.gen.gesture.yaml`) into
`../suzukaze/Assets/GestureDelivery/Generated/Gesture.cs`, namespace
`Suzukaze.Gesture.Protocol`, assembly `Suzukaze.Gesture.Protocol`.
`Google.Protobuf` **3.36.2** is installed in Unity via NuGetForUnity.

`tests/fixtures/messages.json` contains flat dictionaries and deterministic
protobuf hex (without frame headers), usable by Python and C# tests. Hex
equality assumes deterministic serialization; protobuf wire order is otherwise
not semantically significant. Fixtures include absent/present-zero optionals,
all enum values, and uint64 values beyond JavaScript's exact integer range;
fixture consumers must preserve integers as uint64 rather than doubles.
