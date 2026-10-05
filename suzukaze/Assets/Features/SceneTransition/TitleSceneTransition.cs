using Cysharp.Threading.Tasks;
using UnityEngine;
using UnityEngine.InputSystem;

namespace Features.SceneTransition
{
    public class TitleSceneTransition : MonoBehaviour
    {
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
            _input.Disable();
            _input.Dispose();
        }

        private void OnTransition(InputAction.CallbackContext ctx)
        {
            SceneTransitionManager.Instance.LoadSceneAsync("Sea").Forget();
        }
    }
}