using UnityEngine;

public class TreeSwayWhole : MonoBehaviour {
    public WindZone wind;
    public float swayAmount = 3f;      // 傾く角度の最大値
    public float swaySpeed = 1f;
    public float pulseInfluence = 1.5f; // 突風の影響度

    Quaternion baseRotation;
    float phaseOffsetX, phaseOffsetZ;

    void Start() {
        baseRotation = transform.localRotation;
        // 同じPrefabを複数配置しても全部が同期しないようにランダム化
        phaseOffsetX = Random.Range(0f, Mathf.PI * 2f);
        phaseOffsetZ = Random.Range(0f, Mathf.PI * 2f);
    }

    void Update() {
        if (wind == null) return;

        float baseStrength = wind.windMain;
        float pulse = wind.windPulseMagnitude *
                      Mathf.Sin(Time.time * wind.windPulseFrequency) * pulseInfluence;
        float strength = baseStrength + pulse;

        float angleX = Mathf.Sin(Time.time * swaySpeed + phaseOffsetX) * swayAmount * strength;
        float angleZ = Mathf.Sin(Time.time * swaySpeed * 0.8f + phaseOffsetZ) * swayAmount * strength * 0.6f;

        transform.localRotation = baseRotation * Quaternion.Euler(angleX, 0, angleZ);
    }
}