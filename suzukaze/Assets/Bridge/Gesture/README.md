# Unity gesture receiver

Unity **6000.5.8f1**, Windows or 64-bit Linux Editor/standalone, **.NET Standard 2.1** API
compatibility. Connects to the same-PC bridge at `ws://127.0.0.1:5000` by default.
The bridge (`uv run unity-bridge --gesture` in `unity_bridge/`) serves protocol
v1 **binary protobuf**, one `GestureEnvelope` per WebSocket message.
Generated schema/namespace: `Suzukaze.Gesture.Protocol` (`proto/gesture/v1/gesture.proto`).

## 打ち水演出への接続

既存の `Assets/My_script/ParticleOnEnter.cs` が `IGestureSink` を実装しています。
シーン内で有効になると、既存の `GestureReceiverBehaviour` に自動登録します。
受信器がない場合は専用ルート GameObject を作成し、シーンをまたいで再利用します。
診断用 Prefab を追加する必要はありません。接続先は既定で `ws://127.0.0.1:5000`。
変更する場合は、あらかじめ設定した受信器をシーンに配置してください。

- `UCHIMIZU` の成立イベントで、Enter と同じ `TryPlay()` を呼びます。
- シーンに設定済みの `particlePrefab` を `neck.position + Vector3.up * heightOffset`
  に、`neck.rotation` で生成します。生成できた場合だけ `accepted` になります。
- ラムネ、無効な演出、Prefab/首位置の未設定は `ignored`。継続状態では水を出しません。
- 期限切れと重複は既存の受信ポリシーが演出前に除外します。
- Enter / テンキー Enter は手動確認用として利用できます。
- `receiveGestures` を無効にしてからコンポーネントを有効化すると、キー入力のみになります。
- 新シーンの有効な `ParticleOnEnter` が受信先になります。旧シーンの終了で新しい受信先を
  解除しません。複数を同時に有効化した場合は最後に登録したものが受信します。

既存の `Forest`、`river`、`sea`、`Sea2`、`☆1湖`、`滝` は変更なしで接続されます。
他のシーンでは `ParticleOnEnter` と `particlePrefab` / `neck` の設定が必要です。
`Scene_ch` や `river(中流)` には、現時点でこの打ち水コンポーネントはありません。

起動は `unity_bridge/` で `uv run unity-bridge --gesture`、Unity で上記シーンを再生します。
認識のみの `gesture-detection` 起動では Unity へ配送しません。確認手順は
[打ち水接続ガイド](../../../../gesture_detection/docs/uchimizu-unity.md)を参照してください。

## Setup

`Google.Protobuf` is installed by NuGetForUnity from `Assets/packages.config`
and restored automatically when the Editor opens. Do not install another copy
through a different package manager.

The generated bindings in `../Generated/` are not committed. After cloning or
changing the schema, run from the repository's `proto/` directory:

```sh
buf generate
```

In a **Windows or Linux** test scene, add `Prefabs/GestureReceiverDiagnostic.prefab` as
a root object. It persists through scene loads; duplicate owners destroy their
own GameObject. The diagnostic sink defaults to `acceptEvents: false` and logs
occurrence decisions. Opt in to acceptance in its Inspector when testing.
Continuous state is available through `GestureDiagnosticSink.LatestState`.
The receiver exposes `LastError` for connection diagnostics.

For application integration, use a dedicated root GameObject with
`GestureReceiverBehaviour` and assign a `MonoBehaviour` implementing
`IGestureSink` to its sink field (or call `SetSink`). The owner is persistent;
scene code should replace the sink when a scene changes. Missing or destroyed
sinks yield `ignored`. The existing `ParticleOnEnter` scenes automatically bind
the Uchimizu effect as described above; other effects require their own sink.
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

`HostMonotonicClock.Create()` selects the native host clock:

- Windows: `WindowsQpcClock`, `QueryPerformanceCounter / QueryPerformanceFrequency`.
- 64-bit Linux (LP64): `LinuxMonotonicClock`, libc `clock_gettime(CLOCK_MONOTONIC)`.

Neither subtracts a process start time. Both share CPython `time.monotonic()`'s
epoch on the **same native OS and PC**. Linux uses MONOTONIC, not BOOTTIME or
MONOTONIC_RAW. Unity `Time.time`, wall clock, and stopwatch **elapsed** time are
unsuitable. Other hosts/32-bit Linux are rejected before native calls.
Policy/transport accept an `IMonotonicClock` for deterministic tests.

Remote hosts, WSL/Linux Python paired with Windows Unity, WebGL, and mobile
are unsupported. Loopback endpoints are enforced. Windows Mono and IL2CPP,
native QPC behavior, Unity import/linking, and domain/scene lifecycle still
require testing in Unity on Windows. Player Settings enables Run In Background
so switching focus to the detector or bridge console does not pause delivery.
Editor pause, breakpoints, or OS suspension can still stop Update; bounded
queues can disconnect and queued events may expire.

See the [Windows operation guide](../../../../gesture_detection/docs/windows-protobuf.md)
for setup and the remaining Unity/player checks, and the
[Fedora guide](../../../../gesture_detection/docs/fedora-protobuf.md) for Linux and batchmode tests.

## Verification

In Unity Test Runner run **EditMode** and **PlayMode** under `Tests/`. PlayMode
tests cover persistent ownership, destruction/replacement with a lost ACK,
new-play-session isolation, disable/re-enable, and diagnostic opt-in;
ownership tests run on Windows and 64-bit Linux. `NativeClockTests` use the
real host clock. In a test scene manually
exercise session restart, focus loss, scene changes, sink acceptance, and
Windows standalone Mono/IL2CPP builds with a real protobuf bridge
(`unity_bridge/`'s `unity-gesture-probe` is the Python reference receiver).

Fedora 44 x86_64 / Unity 6000.5.8f1 was verified with 27 EditMode and 4 PlayMode
tests (including live Python/Unity delivery through the former TCP bridge and the
since-removed Python fixture test). Standalone Linux builds and live
camera-driven visuals still need deployment-specific verification.
