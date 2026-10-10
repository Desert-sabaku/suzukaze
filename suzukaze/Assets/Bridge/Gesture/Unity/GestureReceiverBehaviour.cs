using System;
using System.Threading;
using System.Threading.Tasks;
using Suzukaze.Core;
using Suzukaze.Diffuser;
using Suzukaze.Fan;
using UnityEngine;
using UnityEngine.InputSystem;

namespace Suzukaze.Gesture
{
    [DisallowMultipleComponent]
    public sealed class GestureReceiverBehaviour : MonoBehaviour
    {
        [SerializeField] private string endpoint = "ws://127.0.0.1:5000";

        private static GestureReceiverBehaviour _owner;
        private static Task _retiring = Task.CompletedTask;
        private static DeliveryPolicy _history = new();
        private ReceiverHandoff handoff;
        private KeyboardGestures keyboard;
        private IMonotonicClock clock;
        private Transceiver receiver;
        private CancellationTokenSource stopping;
        private Task worker;
        public bool IsOwner => _owner == this;
        public string LastError => receiver?.LastError;
        public GestureEvents Events { get; } = new GestureEvents();

        // Scene-local effects bind to one persistent transport owner. Reuse a
        // configured scene receiver even if its Awake has not run yet.
        public static GestureReceiverBehaviour GetOrCreate()
        {
            if (_owner) return _owner;
            var configured = FindAnyObjectByType<GestureReceiverBehaviour>();
            if (configured) return configured;
            return new GameObject("GestureReceiver").AddComponent<GestureReceiverBehaviour>();
        }

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
        private static void ResetPlaySession()
        {
            // Also runs when domain reload is disabled. Retire any old worker
            // before releasing ownership, but retain its cleanup barrier.
            if (_owner) _owner.RetireWorker();
            _owner = null;
            _history = new DeliveryPolicy();
        }

        private void Awake()
        {
            if (_owner && _owner != this) { Destroy(gameObject); return; }
            _owner = this;
            DontDestroyOnLoad(gameObject);
            _history.Disconnected();
            handoff = new ReceiverHandoff(_history);
            keyboard = new KeyboardGestures(Events);
        }

        private void OnEnable()
        {
            // With scene/domain reload disabled an existing component can re-enter
            // without a new Awake. Bind it to the new play session's history.
            if (!_owner) Awake();
            if (!IsOwner) return;
            StartWorker();
        }

        private void StartWorker()
        {
            // Re-enable waits in Update until cancellation of the previous worker
            // has completed. There is never a second live connection owner.
            if (worker != null) return;
            try
            {
                clock = HostMonotonicClock.Create();
                var uri = new Uri(endpoint);
                if (!uri.IsLoopback || (uri.Scheme != "ws" && uri.Scheme != "wss"))
                    throw new ArgumentException("Endpoint must be a loopback WebSocket URI");
                // ファンも同じ WebSocket に載せる。FanOutput は差し替わりうるので、都度 Instance を引く。
                receiver = new Transceiver(new GestureConnection(handoff, clock,
                    connected => FanOutput.Instance.Mcu.Connected = DiffuserOutput.Instance.Connected = connected,
                    state => FanOutput.Instance.Mcu.Apply(state),
                    () => FanOutput.Instance.Mcu.TakeOutgoing() ?? DiffuserOutput.Instance.TakeOutgoing()));
                stopping = new CancellationTokenSource();
                handoff.Resume();
                worker = RunAfterRetirement(receiver, uri, stopping.Token);
            }
            catch (Exception error)
            {
                Debug.LogError("Gesture receiver: " + error.Message, this);
                enabled = false;
            }
        }

        private static async Task RunAfterRetirement(Transceiver next, Uri uri, CancellationToken cancellation)
        {
            try { await _retiring.ConfigureAwait(false); }
            catch (Exception) { /* Already observed by the retiring owner. */ }
            cancellation.ThrowIfCancellationRequested();
            await next.RunAsync(uri, cancellation).ConfigureAwait(false);
        }

        private void Update()
        {
            if (!IsOwner) return;
            if (worker is { IsCompleted: true })
            {
                if (worker.IsFaulted) Debug.LogException(worker.Exception, this);
                worker = null;
                stopping.Dispose();
                stopping = null;
            }
            if (worker == null) StartWorker();
            try
            {
                if (clock != null) handoff.Tick(clock, keyboard);
                keyboard.Tick(Time.unscaledTimeAsDouble, ReadKeys());
            }
            catch (Exception error) { Debug.LogException(error, this); }
        }

        // C: 打ち水、V(長押し): ラムネを構える、B: ラムネを開栓(長押しで開栓後の状態を保つ)、X(長押し): 扇ぎ、Z: 一礼
        private static KeyboardGestureInput ReadKeys()
        {
            var keys = Keyboard.current;
            if (keys == null) return default;
            return new KeyboardGestureInput {
                UchimizuPressed = keys.cKey.wasPressedThisFrame,
                RamuneHeld = keys.vKey.isPressed,
                RamuneOpenPressed = keys.bKey.wasPressedThisFrame,
                RamuneOpenHeld = keys.bKey.isPressed,
                FanningHeld = keys.xKey.isPressed,
                BowPressed = keys.zKey.wasPressedThisFrame
            };
        }

        private void OnDisable()
        {
            if (!IsOwner) return;
            stopping?.Cancel();
            // Invalidate all pending callbacks immediately, before async cleanup.
            handoff.Suspend();
            keyboard.Reset();
            if (clock == null) return;
            try { handoff.Tick(clock, keyboard); }
            catch (Exception error) { Debug.LogException(error, this); }
        }

        private void OnDestroy()
        {
            if (!IsOwner) return;
            RetireWorker();
            _owner = null;
        }

        private void RetireWorker()
        {
            handoff?.Suspend();
            _history.Disconnected();
            var cancellation = stopping;
            cancellation?.Cancel();
            // No Unity API in continuation; observe completion and release resources.
            if (worker != null)
            {
                _retiring = worker;
                _ = worker.ContinueWith(task => { _ = task.Exception; cancellation?.Dispose(); },
                    TaskScheduler.Default);
            }
            else cancellation?.Dispose();
            worker = null;
            stopping = null;
            receiver = null;
            clock = null;
        }
    }
}
