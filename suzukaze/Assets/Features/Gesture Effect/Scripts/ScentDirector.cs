using System.Linq;
using Cysharp.Threading.Tasks;
using Features.Common.Scripts;
using Sirenix.OdinInspector;
using Suzukaze.Diffuser;
using Suzukaze.Diffuser.Protocol;
using Suzukaze.Fan;
using Suzukaze.Gesture;
using Suzukaze.Gesture.Protocol;
using UnityEngine;
using Event = Suzukaze.Gesture.Protocol.Event;

namespace Features.Gesture_Effect.Scripts
{
    /// <summary>
    ///     所作に合わせてディフューザーから香りを出す
    /// </summary>
    /// <remarks>
    ///     ラムネを開けたらラムネの香りを一定時間、扇いでいる間は森の香りを出す (GameSettings で除いたシーンを除く)。
    ///     ディフューザーはファンの裏にあるので、香りを出している間はそのファンを軽く回して香りを届ける。
    ///     設定はすべて GameSettings にある。設定画面 (unity_bridge) でディフューザーを止めると、香りを止めて出さなくなる。
    /// </remarks>
    public class ScentDirector : MonoBehaviour
    {
        [Title("現在の状態")] [ReadOnly] [ShowInInspector]
        private bool _isFanning;

        [ReadOnly] [ShowInInspector] private bool _fanningScentScene;

        private GameSettings _settings;
        private GestureReceiverBehaviour _gestureReceiver;
        private ScentScheduler _scents;

        // いま下限を掛けているファン。香りが変わったときだけ掛け直す
        private FanLocation? _ramuneFan;
        private FanLocation? _forestFan;

        [ReadOnly] [ShowInInspector] private bool IsRamuneOn => _scents?.IsOn(DiffuserChannel.Ramune) ?? false;
        [ReadOnly] [ShowInInspector] private bool IsForestOn => _scents?.IsOn(DiffuserChannel.Forest) ?? false;

        private void Awake()
        {
            _scents = new ScentScheduler(channel => DiffuserOutput.Instance.Press(channel));
        }

        private void Start()
        {
            UniTask.Create(async () =>
            {
                var settings = await GameSettings.GetInstanceAsync();
                _fanningScentScene = !settings.noFanningScentScenes.Contains(gameObject.scene.name);
                _settings = settings;
            });
        }

        private void Update()
        {
            if (!_settings) return;
            if (!RuntimeControl.Instance.DiffuserEnabled)
            {
                _scents.StopAll();
                UpdateFans();
                return;
            }

            var now = Time.unscaledTimeAsDouble;
            if (_isFanning && _fanningScentScene)
                _scents.Emit(DiffuserChannel.Forest, now, _settings.fanningScentGraceSeconds);
            _scents.Update(now);
            UpdateFans();
        }

        private void OnEnable()
        {
            _gestureReceiver = GestureReceiverBehaviour.GetOrCreate();
            _gestureReceiver.Events.StateChanged += OnGestureStateChanged;
            _gestureReceiver.Events.Occurred += OnGestureOccurred;
            OnGestureStateChanged(_gestureReceiver.Events.CurrentState);
        }

        private void OnDisable()
        {
            if (_gestureReceiver)
            {
                _gestureReceiver.Events.StateChanged -= OnGestureStateChanged;
                _gestureReceiver.Events.Occurred -= OnGestureOccurred;
                _gestureReceiver = null;
            }

            // シーンを出るときは香りを止め、ファンを元に戻す
            _isFanning = false;
            _scents.StopAll();
            UpdateFans();
        }

        private void OnGestureStateChanged(StateView state)
        {
            // 追跡が切れると Gesture は None になるため、ここで自然に止まる
            _isFanning = state.Gesture == ContinuousGesture.Fanning;
        }

        // ほかのエフェクトと同じイベントを見るだけなので、採用はしない (false を返す)
        private bool OnGestureOccurred(string sessionId, Event occurrence)
        {
            if (occurrence.Gesture == OccurrenceGesture.Ramune) EmitRamune();
            return false;
        }

        [Button("ラムネの香りを出す")]
        private void EmitRamune()
        {
            if (_settings) _scents.Emit(DiffuserChannel.Ramune, Time.unscaledTimeAsDouble, _settings.ramuneScentSeconds);
        }

        private void UpdateFans()
        {
            FanLocation? ramune = IsRamuneOn ? _settings.ramuneDiffuserFan : null;
            FanLocation? forest = IsForestOn ? _settings.forestDiffuserFan : null;
            if (Equals(ramune, _ramuneFan) && Equals(forest, _forestFan)) return;

            // 2 台が同じファンの裏にあってもよいよう、止めてから回す
            var fans = FanOutput.Instance;
            foreach (var fan in new[] { _ramuneFan, _forestFan })
                if (fan is { } f && !Equals(f, ramune) && !Equals(f, forest))
                    fans.SetFloor(f.side, f.position, 0);
            var output = (byte)Mathf.Clamp(_settings.scentFanOutput, 0, 255);
            foreach (var fan in new[] { ramune, forest })
                if (fan is { } f)
                    fans.SetFloor(f.side, f.position, output);

            _ramuneFan = ramune;
            _forestFan = forest;
        }
    }
}
