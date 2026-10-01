using Suzukaze.Gesture.Protocol;
using Suzukaze.Gesture.Receiver;
using UnityEngine;
using UnityEngine.InputSystem;
using GestureEvent = Suzukaze.Gesture.Protocol.Event;

public class ParticleOnEnter : MonoBehaviour, IGestureSink
{
    public ParticleSystem particlePrefab; // Prefab化したものをアサイン
    public Transform player;              // プレイヤーのTransform(位置基準にする)

    public Transform neck;

    public float heightOffset = 1f;

    [Tooltip("Receive UCHIMIZU from unity_bridge. Enter remains available for manual testing.")]
    public bool receiveGestures = true;
    private GestureReceiverBehaviour receiver;

    void OnEnable()
    {
        if (!receiveGestures) return;
        receiver = GestureReceiverBehaviour.GetOrCreate();
        receiver.SetSink(this);
    }

    void OnDisable()
    {
        if (receiver != null) receiver.ClearSink(this);
        receiver = null;
    }

    public void DeliverState(StateView state) { }

    public bool TryAcceptEvent(string sessionId, GestureEvent occurrence)
    {
        // The receiver checks expiry/dedup before calling this on the main thread.
        return receiveGestures && occurrence != null
            && occurrence.Gesture == OccurrenceGesture.Uchimizu && TryPlay();
    }

    public bool TryPlay()
    {
        // Do not acknowledge an effect that cannot actually be spawned.
        if (!isActiveAndEnabled || particlePrefab == null || neck == null) return false;
        Vector3 spawnPos = neck.position + Vector3.up * heightOffset;
        Instantiate(particlePrefab, spawnPos, neck.rotation);
        return true;
    }

    void Update()
    {
        if (Keyboard.current == null) return;

        if (Keyboard.current.enterKey.wasPressedThisFrame ||
            Keyboard.current.numpadEnterKey.wasPressedThisFrame)
        {
            TryPlay();
        }
    }
}
