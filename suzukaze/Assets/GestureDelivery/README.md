# Unity gesture receiver (PR3)

Unity **6000.5.8f1**, Windows Editor/standalone, **.NET Standard 2.1** API
compatibility. Connects to the same-PC bridge at `ws://127.0.0.1:5000` by default.
The bridge must serve protocol v1 **binary protobuf**, one `GestureEnvelope`
per WebSocket message, without the detector-to-bridge TCP length header.
Generated schema/namespace: `Suzukaze.Gesture.Protocol` (schema commit `de38f1a`).

## Setup

The pinned runtime DLLs (Git LFS), licenses, and Unity metadata are included.
Use a checkout with LFS objects downloaded, or restore the two plugin DLLs
from NuGet. To verify and reproduce them, from the repository root:

```sh
python tools/restore_unity_protobuf.py
```

This stdlib-only script verifies SHA-256 of entire NuGet packages **before**
extracting the chosen `netstandard2.0` DLLs. See `Plugins/DEPENDENCIES.md` for
the framework-supplied transitive dependencies. Do not install another copy of
Google.Protobuf through a different Unity package manager.

In a **Windows** test scene, add `Prefabs/GestureReceiverDiagnostic.prefab` as
a root object. It persists through scene loads; duplicate owners destroy their
own GameObject. The diagnostic sink defaults to `acceptEvents: false` and logs
occurrence decisions. Opt in to acceptance in its Inspector when testing.
Continuous state is available through `GestureDiagnosticSink.LatestState`.
The receiver exposes `LastError` for connection diagnostics.

For application integration, use a dedicated root GameObject with
`GestureReceiverBehaviour` and assign a `MonoBehaviour` implementing
`IGestureSink` to its sink field (or call `SetSink`). The owner is persistent;
scene code should replace the sink when a scene changes. Missing or destroyed
sinks yield `ignored`; there are no inferred scene, fan, or speaker mappings.
Only one receiver may own the connection, even during disable/re-enable or
replacement: cancellation completes before its successor starts connecting.
Disabling clears pending work and delivers neutral state; destruction cancels
the worker and releases its socket/CTS asynchronously without blocking Unity.
Delivery history (sequence and live accepted/ignored IDs) belongs to the play
session, so destroying and replacing the Behaviour cannot repeat an event whose
ACK was lost. Pending queues and continuous state are cleared on replacement.
Subsystem registration resets history for each new play session, including
when domain reload is disabled, while retaining the old worker's cleanup barrier.

```csharp
public void DeliverState(StateView state)
{
    // Called on the main thread each Update, including neutral/stale state.
    // Consume state.Gesture, state.Tracking, state.Fresh as appropriate.
}

public bool TryAcceptEvent(string sessionId, Suzukaze.Gesture.Protocol.Event occurrence)
{
    // Return true only after the scene has adopted this occurrence.
    // Return false if the current scene cannot use it.
    return false;
}
```

Sink methods must be short, synchronous, and must not wait for networking or
re-enter the receiver. The receiver clones mutable protobuf objects at the
handoff/sink boundaries. Sink exceptions disconnect without an ACK. An event
whose sink threw is retained in dedup because the sink may have performed its
effect before throwing; retry returns `duplicate` rather than repeating it.

## Delivery and bounds

* Fragmented binary messages are assembled up to **8192 payload bytes** (one
  extra sentinel byte detects overflow). Empty, text, malformed, unsupported
  version/payload, unknown enum, non-finite time, and invalid ID/expiry inputs
  terminate the connection. Unknown protobuf fields are tolerated.
* The actual final `ReceiveAsync` completion is timestamped, **before parsing
  and Update**. Main-thread policy consumes one latest state and at most **64
  queued events**, plus at most **64 queued ACKs** and one in-flight send.
  State coalescing keeps the highest sequence within a session; older sequence
  numbers remain rejected across reconnects.
* Fresh state requires sender `fresh`, an observed timestamp, and unexpired
  observation, send, and receive times. Future observation/send times are not
  fresh. Tracking/gesture are neutral when freshness is lost, and disconnect
  delivers `NONE`, `tracking=false`, `fresh=false` on the next main-thread tick.
* Event expiry is tested at **adoption time**, not receive time. Only a true
  sink decision ACKs `accepted`; false/missing sink ACKs `ignored`. Expired
  events are never delivered. Future occurrences disconnect (incompatible clock).
* Accepted and ignored event IDs survive reconnects within a producer session;
  retries before expiry ACK `duplicate`. Dedup retains up to **1024 live IDs**.
  Entries can be reclaimed after their original expiry, when normal retries
  ACK `expired`. Publishers must never reuse IDs or change an event's expiry.
  A new session resets dedup and sequence and drops old pending work/ACKs.
  Session IDs must uniquely identify producer lifetimes, not alternate/recur.
* Pending-event, ACK, or live-dedup exhaustion disconnects without fabricating
  an ACK. Already adopted decisions remain deduplicated for a retry. One send
  loop serializes all ACK sends. Connection generations reject stale receives,
  ACK dequeues, and disconnect callbacks from previous sockets.
* Connect timeout: 5 seconds; reconnect backoff: 500 ms. Idle receive/send loops
  honor cancellation; ACK polling is at most 10 ms apart under normal
  scheduling. A disconnect signal also interrupts blocked send/receive tasks
  on main-thread overflow. No background queue grows with a paused Update.

## Clock and platform limits

`WindowsQpcClock` calls `QueryPerformanceCounter` / `QueryPerformanceFrequency`
without subtracting a process start time. This shares the same epoch as
CPython `time.monotonic()` on the **same Windows PC**. Unity `Time.time`, wall
clock, and stopwatch **elapsed** time are unsuitable. Policy/transport accept
an `IMonotonicClock` for deterministic tests; the production component always
selects Windows QPC and reports unsupported platforms rather than guessing.

Remote hosts, WSL/Linux Python paired with Windows Unity, WebGL, and mobile
are unsupported. Loopback endpoints are enforced. Windows Mono and IL2CPP,
native QPC behavior, Unity import/linking, and domain/scene lifecycle still
require testing in Unity on Windows. No global background setting is changed;
the integration owner must arrange background execution if required. If Unity
pauses, bounded queues can disconnect and queued events may expire.

## Verification

Portable Linux/macOS/Windows smoke tests with .NET SDK 8, from repository root:

```sh
dotnet restore tools/GestureDelivery.Smoke/GestureDelivery.Smoke.csproj --locked-mode
dotnet test tools/GestureDelivery.Smoke/GestureDelivery.Smoke.csproj --no-restore
dotnet build tools/GestureDelivery.Compatibility/GestureDelivery.Compatibility.csproj
```

The smoke runner links the actual Unity-independent core, generated schema,
shipped Protobuf DLL, and NUnit EditMode tests. It checks every schema-owned
Python golden fixture (including uint64 max and optional-present zero), exact
C# ACK bytes, fragmentation/bounds, adoption/dedup/state policy, capacity
fail-closed behavior, stale generations, and real loopback ClientWebSocket
reconnection/cancellation. The compatibility build targets .NET Standard 2.1
with C# 8 and warnings as errors; .NET 8 alone would not catch API drift.

In Unity Test Runner run **EditMode** and **PlayMode** under `Tests/`. PlayMode
tests cover persistent ownership, destruction/replacement with a lost ACK,
new-play-session isolation, disable/re-enable, and diagnostic opt-in;
ownership tests skip non-Windows platforms. In a Windows test scene manually
exercise session restart, focus loss, scene changes, sink acceptance, and
Windows standalone Mono/IL2CPP builds with a real protobuf bridge. Portable
tests do not substitute for those Unity/Windows checks.
