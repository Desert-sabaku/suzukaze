using Suzukaze.Gesture.Protocol;
using Suzukaze.Gesture;
using UnityEngine;
using UnityEngine.SceneManagement;

public class RandomSceneLoader : MonoBehaviour
{
    [SerializeField] private string[] sceneNames;
    private GestureReceiverBehaviour receiver;
    private bool starting;

    void OnEnable()
    {
        receiver = GestureReceiverBehaviour.GetOrCreate();
        receiver.Events.StateChanged += OnGestureStateChanged;
    }

    void OnDisable()
    {
        if (receiver != null) receiver.Events.StateChanged -= OnGestureStateChanged;
        receiver = null;
    }

    private void OnGestureStateChanged(StateView state)
    {
        if (state != null && state.Fresh && state.Tracking
            && state.Gesture == ContinuousGesture.Bow)
            TryStartGame();
    }

    void Update()
    {
        if (Input.GetKeyDown(KeyCode.Space)) TryStartGame();
    }

    public bool TryStartGame()
    {
        if (!isActiveAndEnabled || starting || sceneNames == null || sceneNames.Length == 0)
            return false;

        int index = Random.Range(0, sceneNames.Length);
        starting = true;
        SceneManager.LoadScene(sceneNames[index]);
        return true;
    }
}
