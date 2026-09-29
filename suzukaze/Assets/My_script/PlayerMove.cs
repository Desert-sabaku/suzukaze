using UnityEngine;
using UnityEngine.InputSystem;

public class PlayerMove : MonoBehaviour
{
    public float moveSpeed  = 5f;
    public float gravity    = -9.8f;
    public CharacterController controller;

    [Header("水中設定")]
    public bool isUnderwater = false; // UnderwaterEffectから切り替えられる
    public float underwaterGravityMultiplier = 0.2f;
    public float underwaterSpeedMultiplier = 0.5f;

    private Vector3 velocity;
    private bool isGrounded;

    void Update()
    {
        isGrounded = controller.isGrounded;

        if (isGrounded && velocity.y < 0)
        {
            velocity.y = -2f;
        }

        float h = 0f;
        float v = 0f;

        if (Keyboard.current != null)
        {
            if (Keyboard.current.aKey.isPressed || Keyboard.current.leftArrowKey.isPressed) h -= 1f;
            if (Keyboard.current.dKey.isPressed || Keyboard.current.rightArrowKey.isPressed) h += 1f;
            if (Keyboard.current.sKey.isPressed || Keyboard.current.downArrowKey.isPressed) v -= 1f;
            if (Keyboard.current.wKey.isPressed || Keyboard.current.upArrowKey.isPressed) v += 1f;
        }

        // 水中なら速度と重力を弱める
        float currentSpeed = isUnderwater ? moveSpeed * underwaterSpeedMultiplier : moveSpeed;
        float currentGravity = isUnderwater ? gravity * underwaterGravityMultiplier : gravity;

        Vector3 moveDirection = transform.TransformDirection(new Vector3(h, 0, v)) * currentSpeed;

        velocity.y += currentGravity * Time.deltaTime;

        controller.Move((moveDirection + velocity) * Time.deltaTime);
    }
}