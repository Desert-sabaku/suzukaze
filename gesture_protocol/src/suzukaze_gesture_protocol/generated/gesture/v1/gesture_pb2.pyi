from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class ContinuousGesture(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    CONTINUOUS_GESTURE_UNSPECIFIED: _ClassVar[ContinuousGesture]
    CONTINUOUS_GESTURE_NONE: _ClassVar[ContinuousGesture]
    CONTINUOUS_GESTURE_FANNING: _ClassVar[ContinuousGesture]
    CONTINUOUS_GESTURE_RELAXING: _ClassVar[ContinuousGesture]

class OccurrenceGesture(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    OCCURRENCE_GESTURE_UNSPECIFIED: _ClassVar[OccurrenceGesture]
    OCCURRENCE_GESTURE_RAMUNE: _ClassVar[OccurrenceGesture]
    OCCURRENCE_GESTURE_UCHIMIZU: _ClassVar[OccurrenceGesture]

class AckStatus(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    ACK_STATUS_UNSPECIFIED: _ClassVar[AckStatus]
    ACK_STATUS_ACCEPTED: _ClassVar[AckStatus]
    ACK_STATUS_IGNORED: _ClassVar[AckStatus]
    ACK_STATUS_EXPIRED: _ClassVar[AckStatus]
    ACK_STATUS_DUPLICATE: _ClassVar[AckStatus]
CONTINUOUS_GESTURE_UNSPECIFIED: ContinuousGesture
CONTINUOUS_GESTURE_NONE: ContinuousGesture
CONTINUOUS_GESTURE_FANNING: ContinuousGesture
CONTINUOUS_GESTURE_RELAXING: ContinuousGesture
OCCURRENCE_GESTURE_UNSPECIFIED: OccurrenceGesture
OCCURRENCE_GESTURE_RAMUNE: OccurrenceGesture
OCCURRENCE_GESTURE_UCHIMIZU: OccurrenceGesture
ACK_STATUS_UNSPECIFIED: AckStatus
ACK_STATUS_ACCEPTED: AckStatus
ACK_STATUS_IGNORED: AckStatus
ACK_STATUS_EXPIRED: AckStatus
ACK_STATUS_DUPLICATE: AckStatus

class GestureEnvelope(_message.Message):
    __slots__ = ("version", "session_id", "state", "event", "ack")
    VERSION_FIELD_NUMBER: _ClassVar[int]
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    STATE_FIELD_NUMBER: _ClassVar[int]
    EVENT_FIELD_NUMBER: _ClassVar[int]
    ACK_FIELD_NUMBER: _ClassVar[int]
    version: int
    session_id: str
    state: State
    event: Event
    ack: Ack
    def __init__(self, version: _Optional[int] = ..., session_id: _Optional[str] = ..., state: _Optional[_Union[State, _Mapping]] = ..., event: _Optional[_Union[Event, _Mapping]] = ..., ack: _Optional[_Union[Ack, _Mapping]] = ...) -> None: ...

class State(_message.Message):
    __slots__ = ("sequence", "sent_at", "stale_timeout", "fresh", "gesture", "tracking", "observed_at", "frame_id", "source_timestamp")
    SEQUENCE_FIELD_NUMBER: _ClassVar[int]
    SENT_AT_FIELD_NUMBER: _ClassVar[int]
    STALE_TIMEOUT_FIELD_NUMBER: _ClassVar[int]
    FRESH_FIELD_NUMBER: _ClassVar[int]
    GESTURE_FIELD_NUMBER: _ClassVar[int]
    TRACKING_FIELD_NUMBER: _ClassVar[int]
    OBSERVED_AT_FIELD_NUMBER: _ClassVar[int]
    FRAME_ID_FIELD_NUMBER: _ClassVar[int]
    SOURCE_TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    sequence: int
    sent_at: float
    stale_timeout: float
    fresh: bool
    gesture: ContinuousGesture
    tracking: bool
    observed_at: float
    frame_id: int
    source_timestamp: float
    def __init__(self, sequence: _Optional[int] = ..., sent_at: _Optional[float] = ..., stale_timeout: _Optional[float] = ..., fresh: bool = ..., gesture: _Optional[_Union[ContinuousGesture, str]] = ..., tracking: bool = ..., observed_at: _Optional[float] = ..., frame_id: _Optional[int] = ..., source_timestamp: _Optional[float] = ...) -> None: ...

class Event(_message.Message):
    __slots__ = ("event_id", "gesture", "occurred_at", "expires_at", "frame_id", "source_timestamp")
    EVENT_ID_FIELD_NUMBER: _ClassVar[int]
    GESTURE_FIELD_NUMBER: _ClassVar[int]
    OCCURRED_AT_FIELD_NUMBER: _ClassVar[int]
    EXPIRES_AT_FIELD_NUMBER: _ClassVar[int]
    FRAME_ID_FIELD_NUMBER: _ClassVar[int]
    SOURCE_TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    event_id: int
    gesture: OccurrenceGesture
    occurred_at: float
    expires_at: float
    frame_id: int
    source_timestamp: float
    def __init__(self, event_id: _Optional[int] = ..., gesture: _Optional[_Union[OccurrenceGesture, str]] = ..., occurred_at: _Optional[float] = ..., expires_at: _Optional[float] = ..., frame_id: _Optional[int] = ..., source_timestamp: _Optional[float] = ...) -> None: ...

class Ack(_message.Message):
    __slots__ = ("event_id", "status")
    EVENT_ID_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    event_id: int
    status: AckStatus
    def __init__(self, event_id: _Optional[int] = ..., status: _Optional[_Union[AckStatus, str]] = ...) -> None: ...
