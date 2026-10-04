using Cysharp.Threading.Tasks;
using UnityEngine;
using UnityEngine.InputSystem;

namespace Features.SceneTransition
{
    public class TitleSceneTransition : MonoBehaviour
    {
        [SerializeField] private float transitionDuration = 0.5f;

        private GameInputs _input;

        private void Start()
        {
            _input = new GameInputs();
            _input.Debug.Enable();

            _input.Debug.NextStep.performed += OnTransition;
        }

        private void OnDestroy()
        {
            _input.Debug.NextStep.performed -= OnTransition;
            _input.Dispose();
        }

        private void OnTransition(InputAction.CallbackContext ctx)
        {
            SceneTransitionUtils.LoadSceneAsync("Sea", transitionDuration).Forget();
        }
    }
}