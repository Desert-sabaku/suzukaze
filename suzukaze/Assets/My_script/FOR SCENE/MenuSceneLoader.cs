// MenuSceneLoader
using UnityEngine;
using UnityEngine.InputSystem;
using UnityEngine.EventSystems;

public class MenuSceneLoader : MonoBehaviour
{
    public SceneTransition transition;

    void Update()
    {
        if (Keyboard.current.enterKey.wasPressedThisFrame)
        {
            GameObject selected = EventSystem.current.currentSelectedGameObject;
            if (selected != null && selected.TryGetComponent(out SceneInfo info))
            {
                transition.LoadScene(info.SceneName);
            }
        }
    }
}