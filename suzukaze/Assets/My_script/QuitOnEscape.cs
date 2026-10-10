using UnityEngine;
using UnityEngine.InputSystem;

public class QuitOnEscape : MonoBehaviour
{
    void Update()
    {
        if (Keyboard.current != null && Keyboard.current.escapeKey.wasPressedThisFrame)
        {
            // ゲーム中は GameSceneTransition がリザルトへの遷移を担当する。
            // 遷移開始後にコンポーネントが無効になっていても、アプリは終了しない。
            if (FindAnyObjectByType<Features.SceneTransition.GameSceneTransition>() != null) return;
            Quit();
        }
    }

    void Quit()
    {
#if UNITY_EDITOR
        UnityEditor.EditorApplication.isPlaying = false;
#else
        Application.Quit();
#endif
    }
}
