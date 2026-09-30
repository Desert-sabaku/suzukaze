using System;
using System.Threading;
using System.Threading.Tasks;
using UnityEngine;

namespace Suzukaze.Gesture.Delivery
{
    [DisallowMultipleComponent]
    public sealed class GestureReceiverBehaviour : MonoBehaviour
    {
        private static GestureReceiverBehaviour owner;
        private static Task retiring = Task.CompletedTask;
        private static DeliveryPolicy history = new DeliveryPolicy();
        [SerializeField] private string endpoint = "ws://127.0.0.1:5000";
        [Tooltip("Must implement IGestureSink. Missing/destroyed sink ignores events.")]
        [SerializeField] private MonoBehaviour sink;
        private ReceiverHandoff handoff;
        private IMonotonicClock clock;
        private WebSocketReceiver receiver;
        private CancellationTokenSource stopping;
        private Task worker;
        public bool IsOwner => owner == this;
        public string LastError => receiver?.LastError;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
        private static void ResetPlaySession()
        {
            // Also runs when domain reload is disabled. Retire any old worker
            // before releasing ownership, but retain its cleanup barrier.
            if (owner != null) owner.RetireWorker();
            owner = null;
            history = new DeliveryPolicy();
        }

        public void SetSink(MonoBehaviour value)
        {
            if (value != null && !(value is IGestureSink))
                throw new ArgumentException("Sink must implement IGestureSink", nameof(value));
            sink = value;
        }

        private void Awake()
        {
            if (owner != null && owner != this) { Destroy(gameObject); return; }
            owner = this;
            DontDestroyOnLoad(gameObject);
            history.Disconnected();
            handoff = new ReceiverHandoff(history);
        }

        private void OnEnable()
        {
            // With scene/domain reload disabled an existing component can re-enter
            // without a new Awake. Bind it to the new play session's history.
            if (owner == null) Awake();
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
                clock = new WindowsQpcClock();
                var uri = new Uri(endpoint);
                if (!uri.IsLoopback || (uri.Scheme != "ws" && uri.Scheme != "wss"))
                    throw new ArgumentException("Endpoint must be a loopback WebSocket URI");
                receiver = new WebSocketReceiver(handoff, clock);
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

        private static async Task RunAfterRetirement(WebSocketReceiver next, Uri uri, CancellationToken cancellation)
        {
            try { await retiring.ConfigureAwait(false); }
            catch (Exception) { /* Already observed by the retiring owner. */ }
            cancellation.ThrowIfCancellationRequested();
            await next.RunAsync(uri, cancellation).ConfigureAwait(false);
        }

        private void Update()
        {
            if (!IsOwner) return;
            if (worker != null && worker.IsCompleted)
            {
                if (worker.IsFaulted) Debug.LogException(worker.Exception, this);
                worker = null;
                stopping.Dispose();
                stopping = null;
            }
            if (worker == null) StartWorker();
            if (clock == null) return;
            try { handoff.Tick(clock, sink != null ? sink as IGestureSink : null); }
            catch (Exception error) { Debug.LogException(error, this); }
        }

        private void OnDisable()
        {
            if (!IsOwner) return;
            stopping?.Cancel();
            // Invalidate all pending callbacks immediately, before async cleanup.
            handoff.Suspend();
            if (clock != null)
            {
                try { handoff.Tick(clock, sink != null ? sink as IGestureSink : null); }
                catch (Exception error) { Debug.LogException(error, this); }
            }
        }

        private void OnDestroy()
        {
            if (!IsOwner) return;
            RetireWorker();
            owner = null;
        }

        private void RetireWorker()
        {
            handoff?.Suspend();
            history.Disconnected();
            var cancellation = stopping;
            cancellation?.Cancel();
            // No Unity API in continuation; observe completion and release resources.
            if (worker != null)
            {
                retiring = worker;
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
