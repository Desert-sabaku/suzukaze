using UnityEngine;
using UnityEngine.InputSystem;

public class PlayerPOV : MonoBehaviour
{
    // パラメータ
    public Transform neck;
    public float sensitivity    = 2.0f;
    public float minVertical    = -90.0f;
    public float maxVertical    = 90.0f;

    // 演算用変数
    private float rotationX     = 0f;

    void Start()
    {
        Cursor.lockState = CursorLockMode.Locked;
        Cursor.visible = false;
    }

    void Update()
    {
        if (Mouse.current == null) return;

        // マウスの移動量を取得（Deltaは1フレームあたりのピクセル移動量）
        Vector2 mouseDelta = Mouse.current.delta.ReadValue();

        float mouseX = mouseDelta.x * sensitivity * 0.1f;
        float mouseY = mouseDelta.y * sensitivity * 0.1f;

        transform.Rotate(0, mouseX, 0);

        rotationX -= mouseY;
        rotationX = Mathf.Clamp(rotationX, minVertical, maxVertical);
        neck.localRotation = Quaternion.Euler(rotationX, 0, 0);
    }
}