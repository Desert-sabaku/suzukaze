using UnityEngine;

public class DayNightCycle : MonoBehaviour
{
    [Header("参照")]
    public Light sun;
    public Material skyboxMaterial; // Procedural Skyboxマテリアル

    [Header("時間設定")]
    public float dayLengthInSeconds = 120f;
    [Range(0, 24)] public float startHour = 12f;

    [Header("太陽の色・強度")]
    public Gradient sunColor;
    public AnimationCurve sunIntensity;

    [Header("環境光")]
    public Gradient ambientColor;
    public AnimationCurve ambientIntensity; // SkyboxのExposure Multiplierに使う

    [Header("スカイボックスの色味")]
    public Gradient skyboxTint; // 空全体の色調

    private float currentHour;

    void Start()
    {
        currentHour = startHour;

        if (skyboxMaterial == null)
            skyboxMaterial = RenderSettings.skybox;
    }

    void Update()
    {
        currentHour += (24f / dayLengthInSeconds) * Time.deltaTime;
        if (currentHour >= 24f) currentHour -= 24f;

        float t = currentHour / 24f;

        UpdateSun(t);
        UpdateAmbient(t);
        UpdateSkybox(t);
    }

    void UpdateSun(float t)
    {
        float sunAngle = t * 360f - 90f;
        sun.transform.rotation = Quaternion.Euler(sunAngle, -30f, 0f);

        sun.color = sunColor.Evaluate(t);
        sun.intensity = sunIntensity.Evaluate(t);
    }

    void UpdateAmbient(float t)
    {
        // Lighting > Environment > Ambient Sourceが"Color"の場合はこれが効く
        RenderSettings.ambientLight = ambientColor.Evaluate(t);

        // Ambient Sourceが"Skybox"の場合はExposureで明るさを制御
        if (skyboxMaterial != null && skyboxMaterial.HasProperty("_Exposure"))
        {
            skyboxMaterial.SetFloat("_Exposure", ambientIntensity.Evaluate(t));
        }

        // 反射も更新(重い処理なので数フレームに1回でもOK)
        DynamicGI.UpdateEnvironment();
    }

    void UpdateSkybox(float t)
    {
        if (skyboxMaterial != null && skyboxMaterial.HasProperty("_SkyTint"))
        {
            skyboxMaterial.SetColor("_SkyTint", skyboxTint.Evaluate(t));
        }
    }
}