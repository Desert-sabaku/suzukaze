// ReturnHomr → ReturnHome にリネーム推奨
using UnityEngine;
using UnityEngine.InputSystem;

public class ReturnHomr : MonoBehaviour
{
    public string sceneName;
    public SceneTransition transition;

    void Update()
    {
        if (Keyboard.current.aKey.wasPressedThisFrame) // isPressedだと押しっぱなしで毎フレーム発火するのでこっちに修正
        {
            transition.LoadScene(sceneName);
        }
    }
}