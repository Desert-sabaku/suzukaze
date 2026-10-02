using UnityEngine;

public class FantasySkyboxSwitcher : MonoBehaviour
{
    public Light sun;
    public float dayLengthInSeconds = 120f;
    [Range(0, 24)] public float startHour = 12f;

    [Header("時間順にマテリアルをセット(Skybox/Cubemap形式)")]
    public Material[] skyboxMaterials; // 例: [夜明け, 昼, 夕方, 夜]
    public float[] hourThresholds;     // 例: [5, 8, 17, 20]

    [Header("ブレンド設定")]
    public Material blendMaterial;         // Skybox/CubemapBlend のマテリアル
    public float blendHours = 1.5f;        // しきい値の時刻から、ゲーム内で何時間かけて切り替えるか
    public float envUpdateInterval = 0.5f; // ブレンド中に環境光を更新する間隔(秒)

    private float currentHour;
    private Material sky;
    private Texture[] cubemaps;
    private float envTimer;
    private bool wasBlending;

    void Start()
    {
        currentHour = startHour;

        // 各マテリアルからCubemapを取り出す
        cubemaps = new Texture[skyboxMaterials.Length];
        for (int i = 0; i < skyboxMaterials.Length; i++)
        {
            if (skyboxMaterials[i].HasProperty("_Tex"))
                cubemaps[i] = skyboxMaterials[i].GetTexture("_Tex");
            else
                Debug.LogWarning($"{skyboxMaterials[i].name} は Skybox/Cubemap 形式じゃないかも(_Texが無い)");
        }

        // アセットを書き換えないようにコピーを使う
        sky = new Material(blendMaterial);
        RenderSettings.skybox = sky;

        UpdateSkybox();
        DynamicGI.UpdateEnvironment();
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
        int n = hourThresholds.Length;

        // 今の時間帯を求める(最初のしきい値より前は、最後の時間帯=夜の続き)
        int index = n - 1;
        for (int i = 0; i < n; i++)
        {
            if (currentHour >= hourThresholds[i]) index = i;
        }

        // その時間帯に入ってから何時間経ったか(日をまたぐ場合も考慮)
        float elapsed = currentHour - hourThresholds[index];
        if (elapsed < 0f) elapsed += 24f;

        // 前の時間帯 → 今の時間帯 へ、blendHoursかけてブレンド
        int prev = (index - 1 + n) % n;
        float t = Mathf.SmoothStep(0f, 1f, Mathf.Clamp01(elapsed / blendHours));

        sky.SetTexture("_TexA", cubemaps[prev]);
        sky.SetTexture("_TexB", cubemaps[index]);
        sky.SetFloat("_Blend", t);

        // 環境光はブレンド中だけ、間隔をあけて更新(毎フレームは重いので)
        bool blending = elapsed < blendHours;
        if (blending)
        {
            envTimer += Time.deltaTime;
            if (envTimer >= envUpdateInterval)
            {
                envTimer = 0f;
                DynamicGI.UpdateEnvironment();
            }
        }
        else if (wasBlending)
        {
            DynamicGI.UpdateEnvironment(); // 終わった瞬間に最終状態へ
        }
        wasBlending = blending;
    }
}