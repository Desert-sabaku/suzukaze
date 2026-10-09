using UnityEngine;
using UnityEngine.Audio;

namespace Features.Result.Scripts
{
    /// <summary>
    ///     線香花火 (Senko Hanabi VFX) に火がついている間だけ燃える音を鳴らす．
    ///     着火から火玉が落ちるまでループ再生し，火玉が落ちたらフェードアウトして止める．
    /// </summary>
    [DisallowMultipleComponent]
    [RequireComponent(typeof(SenkoHanabiController))]
    public class SenkoHanabiSound : MonoBehaviour
    {
        [SerializeField] private AudioClip clip;
        [SerializeField] private AudioMixerGroup output;
        [Range(0f, 1f)] [SerializeField] private float volume = 1f;

        [Tooltip("火玉が落ちてから音が消えるまでの秒数．")] [SerializeField]
        private float fadeOutDuration = 0.3f;

        private SenkoHanabiController _hanabi;
        private AudioSource _source;

        private void Awake()
        {
            _hanabi = GetComponent<SenkoHanabiController>();
            if (!clip)
            {
                Debug.LogError("Clipを設定してください。", this);
                enabled = false;
                return;
            }

            // 演出の一部として確実に聞こえるよう 2D で鳴らす
            _source = gameObject.AddComponent<AudioSource>();
            _source.playOnAwake = false;
            _source.clip = clip;
            _source.loop = true;
            _source.outputAudioMixerGroup = output;
            _source.spatialBlend = 0f;
            _source.volume = 0f;
        }

        private void Update()
        {
            var burning = _hanabi.IsPlaying && !_hanabi.IsDropped;
            if (burning)
            {
                _source.volume = volume;
                if (!_source.isPlaying) _source.Play();
                return;
            }

            if (!_source.isPlaying) return;
            var step = fadeOutDuration > 0f ? volume * Time.deltaTime / fadeOutDuration : volume;
            _source.volume = Mathf.MoveTowards(_source.volume, 0f, step);
            if (_source.volume <= 0f) _source.Stop();
        }

        private void OnDisable()
        {
            if (_source) _source.Stop();
        }
    }
}
