#if UNITY_EDITOR
using UnityEditor;
using UnityEngine;

[InitializeOnLoad]
public class Startup
{
    static Startup()    
    {
        EditorPrefs.SetInt("ShowNumber_TreePacks", EditorPrefs.GetInt("ShowNumber_TreePacks") + 1);

        if (EditorPrefs.GetInt("ShowNumber_TreePacks") == 1)       
        {
                Application.OpenURL("https://assetstore.unity.com/publishers/141530");
        }
    }     
}
#endif
