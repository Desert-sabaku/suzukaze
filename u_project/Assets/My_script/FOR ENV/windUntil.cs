using UnityEngine;

public static class WindUtil
{
    public static float GetStrength(WindZone wind, float pulseInfluence = 1f)
    {
        if (wind == null) return 0f;
        return wind.windMain + wind.windPulseMagnitude * Mathf.Sin(Time.time * wind.windPulseFrequency) * pulseInfluence;
    }
}