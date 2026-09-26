using UnityEngine;

[ExecuteAlways]
public class WindZoneToShaderGraph : MonoBehaviour
{
    public WindZone wind;

    static readonly int WindStrengthID = Shader.PropertyToID("_WindStrength");

    void Update()
    {
        if (wind == null) return;

        float strength = wind.windMain + wind.windPulseMagnitude *
                          Mathf.Sin(Time.time * wind.windPulseFrequency);

        Shader.SetGlobalFloat(WindStrengthID, strength);
    }
}