using System.Linq;
using Sirenix.OdinInspector;
using UnityEngine;
using Random = UnityEngine.Random;

namespace Features.Sound.Scripts
{
    /// <summary>
    ///     夕涼みで感覚が開けたころ、庭の奥でししおどしが鳴る。
    ///     夕涼みを続けるあいだは、竹筒に水が溜まるたびに間をあけて鳴る。
    ///     状態は SoundSensitivity (YusuzumiSoundDirector が動かす) から読むので、所作を直接は購読しない
    /// </summary>
    [RequireComponent(typeof(AudioSource))]
    public class ShishiOdoshiSoundEmitter : MonoBehaviour
    {
        [Title("ししおどし")] [SerializeField] [Required]
        private AudioClip clip;

        [SerializeField] [Range(0f, 1f)] private float volume = 0.7f;

        [Tooltip("SoundSensitivity.Level がこの値を超えたら、ひと呼吸おいて鳴る")] [SerializeField] [Range(0.05f, 1f)]
        private float sensitivityThreshold = 0.5f;

        [Tooltip("感覚が開けてから最初に鳴るまでの間 (秒)。所作に即答せず、気づいたら鳴っていたように聞かせる")]
        [SerializeField] [MinMaxSlider(0f, 5f, true)]
        private Vector2 firstStrikeDelaySeconds = new(0.6f, 1.6f);

        [Tooltip("夕涼みを続けているとき、竹筒に水が溜まって次に鳴るまでの間 (秒)")] [SerializeField] [MinMaxSlider(3f, 40f, true)]
        private Vector2 refillSeconds = new(11f, 17f);

        [Tooltip("夕涼みを一瞬やめて戻ったときにも、これより短い間では鳴り直さない (秒)")] [SerializeField] [Min(0f)]
        private float minimumIntervalSeconds = 8f;

        [Tooltip("一打ごとの音の高さと強さの揺らぎ。竹と水の加減で毎回わずかに違う")] [SerializeField] [Range(0f, 0.1f)]
        private float pitchJitter = 0.03f;

        [SerializeField] [Range(0f, 0.5f)] private float volumeJitter = 0.15f;

        [Tooltip("聞き手から見たししおどしの位置。縁側の先、少し低い庭の奥に置く")] [SerializeField]
        private Vector3 offsetFromListener = new(-2.5f, -0.8f, 5f);

        [Title("現在の状態")] [ReadOnly] [ShowInInspector]
        private bool _awake;

        private float _lastStrikeTime = float.NegativeInfinity;
        private AudioListener _listener;
        private float _nextStrikeTime = float.PositiveInfinity;
        private AudioSource _source;

        private void Awake()
        {
            _source = GetComponent<AudioSource>();
            _source.playOnAwake = false;
            _source.loop = false;
            // 取り込み設定では事前に読み込まないため、最初の一打が遅れないよう先に読み込んでおく
            if (clip) clip.LoadAudioData();
            _listener = FindObjectsByType<AudioListener>()
                .FirstOrDefault(candidate =>
                    candidate.isActiveAndEnabled && candidate.gameObject.scene == gameObject.scene);
        }

        private void LateUpdate()
        {
            // Soundscape の下に置いたまま、聞き手から見た位置に保つ
            if (_listener) transform.position = _listener.transform.TransformPoint(offsetFromListener);
            Tick(SoundSensitivity.Level, Time.time);
        }

        private void OnDisable()
        {
            // 鳴り終わりの余韻は切らない。次に有効になったときは、改めて感覚が開けるのを待つ
            _awake = false;
            _nextStrikeTime = float.PositiveInfinity;
        }

        private void OnValidate()
        {
            refillSeconds.y = Mathf.Max(refillSeconds.x, refillSeconds.y);
            firstStrikeDelaySeconds.y = Mathf.Max(firstStrikeDelaySeconds.x, firstStrikeDelaySeconds.y);
        }

        private void Tick(float sensitivity, float now)
        {
            var awake = sensitivity >= sensitivityThreshold;
            if (awake != _awake)
            {
                _awake = awake;
                // 夕涼みをやめたら、溜まりかけた水はそのまま。戻ってきたら最低限の間をおいて鳴る
                _nextStrikeTime = awake
                    ? Mathf.Max(now + Random.Range(firstStrikeDelaySeconds.x, firstStrikeDelaySeconds.y),
                        _lastStrikeTime + minimumIntervalSeconds)
                    : float.PositiveInfinity;
            }

            if (!_awake || now < _nextStrikeTime) return;
            Strike(now);
        }

        private void Strike(float now)
        {
            _lastStrikeTime = now;
            _nextStrikeTime = now + Random.Range(refillSeconds.x, refillSeconds.y);
            if (!_source || !clip) return;
            _source.pitch = 1f + Random.Range(-pitchJitter, pitchJitter);
            _source.PlayOneShot(clip, volume * (1f - Random.Range(0f, volumeJitter)));
        }

        [Button("ししおどしを鳴らす")]
        private void StrikeNow()
        {
            Strike(Time.time);
        }
    }
}
