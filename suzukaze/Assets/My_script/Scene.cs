using UnityEngine;
using UnityEngine.SceneManagement;

public class Scene : MonoBehaviour
{
    public void LoadScene(string Scenename)
    {
        SceneManager.LoadScene(Scenename);
    }
}
