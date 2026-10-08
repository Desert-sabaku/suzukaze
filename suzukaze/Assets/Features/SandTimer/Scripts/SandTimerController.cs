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
        [Range(0f, 1f)]
        [ShowInInspector]
        public float Progress
        {
            get => _progress;
            set
            {
                _progress = value;
                ApplyProgress(_progress);
            }
        }

        private void Start()
        {
            Progress = 0;
        }

        private void ApplyProgress(float value)
        {
            if (float.IsNaN(value) || float.IsInfinity(value)) return;

            if (alembicPlayer)
                // CurrentTime is relative to StartTime, not an absolute timestamp.
                alembicPlayer.UpdateImmediately(Progress * alembicPlayer.Duration);
        }
    }
}