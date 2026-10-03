using UnityEngine;
using UnityEngine.SceneManagement;

public class RandomSceneLoader : MonoBehaviour
{
    [SerializeField] private string[] sceneNames;

    void Update()
    {
        if (Input.GetKeyDown(KeyCode.Space))
        {
            if (sceneNames.Length == 0) return;

            int index = Random.Range(0, sceneNames.Length);
            SceneManager.LoadScene(sceneNames[index]);
        }
    }
}