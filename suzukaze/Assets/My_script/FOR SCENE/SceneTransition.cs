using UnityEngine;
using UnityEngine.SceneManagement;
using System.Collections;

public class SceneTransition : MonoBehaviour
{
    public CanvasGroup fadeCanvas;
    //public ParticleSystem sparkles;
    public float duration = 1.0f;

    void Awake()
    {
        DontDestroyOnLoad(gameObject);
        //DontDestroyOnLoad(sparkles.gameObject);

        fadeCanvas.alpha = 0;
        fadeCanvas.interactable = false;
        fadeCanvas.blocksRaycasts = false;
    }

    public void LoadScene(string sceneName)
    {
        StartCoroutine(TransitionRoutine(sceneName));
    }

    IEnumerator TransitionRoutine(string sceneName)
    {
        //sparkles.Play();
        yield return StartCoroutine(Fade(0, 1));

        AsyncOperation op = SceneManager.LoadSceneAsync(sceneName);
        op.allowSceneActivation = false;
        while (op.progress < 0.9f) yield return null;
        op.allowSceneActivation = true;
        yield return null;

        yield return StartCoroutine(Fade(1, 0));
        //sparkles.Stop();
    }

    IEnumerator Fade(float from, float to)
    {
        fadeCanvas.blocksRaycasts = true;
        float t = 0;
        while (t < duration)
        {
            t += Time.deltaTime;
            fadeCanvas.alpha = Mathf.Lerp(from, to, t / duration);
            yield return null;
        }
        fadeCanvas.alpha = to;
        fadeCanvas.blocksRaycasts = (to > 0);
    }
}