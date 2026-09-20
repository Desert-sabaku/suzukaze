using UnityEngine;

public class FantasySkyboxSwitcher : MonoBehaviour
{
    public Light sun;
    public float dayLengthInSeconds = 120f;
    [Range(0, 24)] public float startHour = 12f;

    [Header("時間順にマテリアルをセット")]
    public Material[] skyboxMaterials; // 例: [夜明け, 昼, 夕方, 夜]
    public float[] hourThresholds;     // 例: [5, 8, 17, 20]

    private float currentHour;
    private int currentIndex = -1;

    void Start()
    {
        currentHour = startHour;
    }

    void Update()
    {
        currentHour += (24f / dayLengthInSeconds) * Time.deltaTime;
        if (currentHour >= 24f) currentHour -= 24f;

        float sunAngle = (currentHour / 24f) * 360f - 90f;
        sun.transform.rotation = Quaternion.Euler(sunAngle, -30f, 0f);

        UpdateSkybox();
    }

    void UpdateSkybox()
    {
        int index = 0;
        for (int i = 0; i < hourThresholds.Length; i++)
        {
            if (currentHour >= hourThresholds[i]) index = i;
        }

        if (index != currentIndex)
        {
            currentIndex = index;
            RenderSettings.skybox = skyboxMaterials[index];
            DynamicGI.UpdateEnvironment();
        }
    }
}