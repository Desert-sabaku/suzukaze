# Unity gesture receiver

Unity **6000.5.8f1**, Windows or 64-bit Linux Editor/standalone, **.NET Standard 2.1** API
compatibility. Connects to the same-PC bridge at `ws://127.0.0.1:5000` by default.
The bridge (`uv run unity-bridge --gesture` in `unity_bridge/`) serves protocol
v1 **binary protobuf**, one `GestureEnvelope` per WebSocket message.
Generated schema/namespace: `Suzukaze.Gesture.Protocol` (`proto/gesture/v1/gesture.proto`).

## 演出から使う共通 API

```text
WebSocket → 配送ポリシー（失効・重複・ACK）→ GestureEvents → 各演出の購読
```

`GestureReceiverBehaviour.GetOrCreate().Events` から全所作を取得します。
受信器は1つ、演出の購読は複数です。所作別の受信器や単一の Sink の設定は不要です。
`IGestureSink` は配送ポリシーと `GestureEvents` の内部接続用です。

| API | 内容 |
|---|---|
| `CurrentState` | 現在の状態。`Gesture` は `None / Fanning / Relaxing / Bow`、`Fresh`、`Tracking`、`PhaseAction`、`Phase` も公開 |
| `StateChanged` | 所作・phase・鮮度・追跡・セッションが変わったときの通知。失効・切断でも解除状態を通知 |
| `Occurred` | `Ramune / Uchimizu` の成立通知。コールバックは採用したときだけ `true` を返す |

すべて Unity メインスレッドで呼ばれます。`CurrentState` は各 Update で更新し、
連番・受信時刻だけの更新では `StateChanged` を再発行しません。購読開始時は
`CurrentState` も読み、既に継続している扇ぎ・夕涼みを反映してください。
現プロトコルの継続状態は代表動作1つで、扇ぎと夕涼みを同時に表しません。

`PhaseAction` と `Phase` は文字列で、認識器の現在の進行状態を公開します。
ラムネや打ち水の準備中は `Gesture == None` でも取得できます。
準備状態は成立イベントではなく、`Occurred` は成立時だけ通知します。

| `PhaseAction` | `Phase` |
|---|---|
| `RAMUNE` | `FORMING / READY / OPENED / WAIT_RELEASE` |
| `UCHIMIZU` | `READY / SWING` |
| `FANNING / RELAXING` | `ACTIVE` |
| `BOW` | `HOLD` |

アイドル・追跡喪失・失効・切断時は両方 `null` です。phaseも代表動作1つを送り、
現在の動作を優先し、動作がない場合はラムネ、打ち水の順に準備状態を選びます。
複数カメラでは現在の動作に対応するphaseを優先し、それ以外は動作の優先順位と
最新の観測時刻で選びます。礼の `BENDING / RETURNING` など、認識器がまだ判定しない
段階は送信しません。

```csharp
bool ramuneReady = gestures.CurrentState.PhaseAction == "RAMUNE"
    && gestures.CurrentState.Phase == "READY";
```

```csharp
using Suzukaze.Gesture.Protocol;
using Suzukaze.Gesture.Receiver;
using UnityEngine;
using GestureEvent = Suzukaze.Gesture.Protocol.Event;

public sealed class GestureExample : MonoBehaviour
{
    private GestureEvents gestures;
    public bool FanningActive { get; private set; }
    public bool RelaxingActive { get; private set; }

    void OnEnable()
    {
        gestures = GestureReceiverBehaviour.GetOrCreate().Events;
        gestures.StateChanged += OnStateChanged;
        gestures.Occurred += OnOccurred;
        OnStateChanged(gestures.CurrentState);
    }

    void OnDisable()
    {
        if (gestures != null)
        {
            gestures.StateChanged -= OnStateChanged;
            gestures.Occurred -= OnOccurred;
            gestures = null;
        }
        OnStateChanged(new StateView());
    }

    void OnStateChanged(StateView state)
    {
        FanningActive = state.Fresh && state.Tracking && state.Gesture == ContinuousGesture.Fanning;
        RelaxingActive = state.Fresh && state.Tracking && state.Gesture == ContinuousGesture.Relaxing;
        // この状態を風・音・映像などに反映する。
    }

    bool OnOccurred(string sessionId, GestureEvent occurrence)
    {
        if (occurrence.Gesture == OccurrenceGesture.Ramune)
            Debug.Log($"ラムネ成立: {sessionId}/{occurrence.EventId}");
        // ログだけでは採用しない。実際に演出を開始できたら true を返す。
        return false;
    }
}
```

`Occurred` は全購読者を呼び、戻り値の OR を ACK の採用結果にします。打ち水を採用する演出と、
ラムネを採用する演出と、記録だけの購読者を併用できます。未購読・全員見送りなら `ignored`。
再送の重複・期限切れは購読者に渡しません。後から購読しても過去の成立イベントは再生しません。
複数の演出が同じイベントを採用した場合、それぞれ実行されます。排他的な演出判断は演出側で行います。
購読者は `OnDisable` で解除し、自分の継続演出も停止してください。

## スタート画面と礼の接続

`Assets/My_script/FOR SCENE/RandomSceneLoader.cs`は、Spaceキーに加え、
`StateChanged`で新たに届いた`Bow`状態でもゲームを開始します。
`Fresh`と`Tracking`が両方trueの場合だけ、Spaceと同じ`TryStartGame()`を呼び、
Inspectorで設定した`sceneNames`からランダムにシーンを選びます。
開始処理はコンポーネントごとに一度だけ実行し、礼の継続・再接続や同時のSpace入力で
二重に開始しません。画面の無効化時に購読を解除します。
購読開始時の保存済み状態は再生せず、画面表示後の状態変更を待ちます。

開始画面`Scene_ch`の`SceneCahnger`オブジェクトに`RandomSceneLoader`を配置済みです。
`sceneNames`にはBuild Settingsで有効な`Forest`、`☆1湖`、`river(中流)`、`river`、`sea`
を設定しています。追加の受信器やイベント設定は不要です。
受信器は開始画面で自動作成し、次のシーンでも再利用します。
起動は`unity_bridge/`で`uv run unity-bridge --gesture`を実行し、Unityで開始画面を再生します。
Spaceによる手動開始は、ブリッジ未接続でも利用できます。

確認時は、開始画面で礼をしてシーンが一度だけ切り替わること、礼を戻してから
開始画面を開き直してSpaceでも切り替わることを確認してください。
probeもWebSocketの受信クライアントなので、Unityで試す前にprobeは終了してください。
ブリッジは同時に1つの受信クライアントだけを許可します。

## 打ち水演出への接続

既存の `Assets/My_script/ParticleOnEnter.cs` が `Occurred` を購読します。
シーン内で有効になると登録し、無効化時に自分の購読だけを解除します。
受信器がない場合は専用ルート GameObject を作成し、シーンをまたいで再利用します。
診断用 Prefab を追加する必要はありません。接続先は既定で `ws://127.0.0.1:5000`。
変更する場合は、あらかじめ設定した受信器をシーンに配置してください。

- `UCHIMIZU` の成立イベントで、Enter と同じ `TryPlay()` を呼びます。
- シーンに設定済みの `particlePrefab` を `neck.position + Vector3.up * heightOffset`
  に、`neck.rotation` で生成します。生成できた場合だけ `accepted` になります。
- ラムネ、無効な演出、Prefab/首位置の未設定はこの購読者が `false` を返します。
  他の購読者も採用しなければ `ignored`。継続状態では水を出しません。
- 期限切れと重複は既存の受信ポリシーが演出前に除外します。
- Enter / テンキー Enter は手動確認用として利用できます。
- `receiveGestures` を無効にしてからコンポーネントを有効化すると、キー入力のみになります。
- 複数の有効な `ParticleOnEnter` はそれぞれ受信します。旧シーンを無効化しても
  新シーンの購読や、別の所作を担当する演出の購読は解除しません。

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

For application integration, subscribe to the receiver's `Events` as above.
`SetSink` / `ClearSink` and the Inspector sink field have been removed.
The diagnostic component is also an ordinary subscriber, so observing events
does not replace a scene's effects. Its opt-in `acceptEvents` is for diagnostics
only; keep it false alongside real effects.
Only one receiver may own the connection, even during disable/re-enable or
replacement: cancellation completes before its successor starts connecting.
Disabling clears pending work and delivers neutral state; destruction cancels
the worker and releases its socket/CTS asynchronously without blocking Unity.
Delivery history (sequence and live accepted/ignored IDs) belongs to the play
session, so destroying and replacing the Behaviour cannot repeat an event whose
ACK was lost. Pending queues and continuous state are cleared on replacement.
Subsystem registration resets history for each new play session, including
when domain reload is disabled, while retaining the old worker's cleanup barrier.

Subscribers must be short, synchronous, and must not wait for networking or
re-enter the receiver. The receiver clones mutable protobuf objects at the
handoff and per-subscriber boundaries. Subscriber exceptions interrupt dispatch
and disconnect without an ACK. An event whose callback threw is retained in
dedup because an effect may have run before the exception; retry returns
`duplicate` rather than repeating it. Already executed effects are not rolled back.

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
* Event expiry is tested at **adoption time**, not receive time. Any true
  subscriber decision ACKs `accepted`; all false/no subscribers ACKs `ignored`. Expired
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

See the [integration guide](../../../../gesture_detection/docs/integration.md)
for setup and the remaining Unity/player checks on Windows and Linux.

## Verification

In Unity Test Runner run **EditMode** and **PlayMode** under `Tests/`. PlayMode
tests cover persistent ownership, destruction/replacement with a lost ACK,
new-play-session isolation, disable/re-enable, and diagnostic opt-in;
ownership tests run on Windows and 64-bit Linux. `NativeClockTests` use the
real host clock. In a test scene manually
exercise session restart, focus loss, scene changes, sink acceptance, and
Windows standalone Mono/IL2CPP builds with a real protobuf bridge
(`unity_bridge/`'s `unity-gesture-probe` is the Python reference receiver).

Fedora 44 x86_64 / Unity 6000.5.8f1: 48 EditMode and 15 PlayMode tests passed.
Tests cover all four gesture kinds, fanout/ACK decisions, stale-state reset,
subscription removal, diagnostic coexistence, and real water-particle creation.
These inject recognition results at the delivery-policy boundary; live-camera
visuals and standalone player builds still need deployment-specific verification.
