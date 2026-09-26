using UnityEngine;
using UnityEngine.InputSystem;
using UnityEngine.EventSystems;

public class SceneLoadOnKey : MonoBehaviour
{
    [Header("キー設定")]
    public Key key = Key.Enter;

    [Header("シーン指定(空欄なら選択中のメニュー項目のSceneInfoから取得)")]
    public string sceneName;

    public SceneTransition transition;

    void Update()
    {
        if (Keyboard.current == null || !Keyboard.current[key].wasPressedThisFrame) return;

        string target = sceneName;

        if (string.IsNullOrEmpty(target))
        {
            GameObject selected = EventSystem.current.currentSelectedGameObject;
            if (selected != null && selected.TryGetComponent(out SceneInfo info))
                target = info.SceneName;
        }

        if (!string.IsNullOrEmpty(target))
            transition.LoadScene(target);
    }
}