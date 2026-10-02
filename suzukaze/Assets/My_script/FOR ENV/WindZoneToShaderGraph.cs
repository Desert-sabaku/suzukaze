using UnityEngine;

[ExecuteAlways]
public class WindZoneToShaderGraph : MonoBehaviour
{
    public WindZone wind;

    static readonly int WindStrengthID = Shader.PropertyToID("_WindStrength");

    void Update()
    {
        if (wind == null) return;

        float strength = WindUtil.GetStrength(wind);

        Shader.SetGlobalFloat(WindStrengthID, strength);
    }
}