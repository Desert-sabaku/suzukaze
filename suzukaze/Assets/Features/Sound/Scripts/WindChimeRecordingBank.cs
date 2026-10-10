using UnityEngine;

namespace Features.Sound.Scripts
{
    [CreateAssetMenu(menuName = "Sound/Wind Chime Recording Bank")]
    public class WindChimeRecordingBank : ScriptableObject
    {
        public AudioClip[] shortStrikes;
        public AudioClip[] longStrikes;
    }
}
