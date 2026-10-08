using Sirenix.OdinInspector;
using UnityEngine;
using UnityEngine.Formats.Alembic.Importer;

namespace Features.SandTimer.Scripts
{
    [DisallowMultipleComponent]
    public class SandTimerController : MonoBehaviour
    {
        [Header("Alembic")] [SerializeField] private AlembicStreamPlayer alembicPlayer;

        private float _progress;

        [Header("Progress")]
        [ShowInInspector]
        [Range(0f, 1f)]
        public float Progress
        {
            get => _progress;
            set
            {
                _progress = Mathf.Clamp01(value);
                SetProgress(_progress);
            }
        }

        private void Start()
        {
            SetProgress(Progress);
        }

        private void SetProgress(float value)
        {
            if (float.IsNaN(value) || float.IsInfinity(value)) return;

            Progress = Mathf.Clamp01(value);

            if (alembicPlayer)
                // CurrentTime is relative to StartTime, not an absolute timestamp.
                alembicPlayer.UpdateImmediately(Progress * alembicPlayer.Duration);
        }
    }
}