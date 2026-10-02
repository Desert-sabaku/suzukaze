using UnityEngine;
using UnityEngine.InputSystem;

public class ParticleOnEnter : MonoBehaviour
{
    public ParticleSystem particlePrefab; // Prefab化したものをアサイン
    public Transform player;              // プレイヤーのTransform(位置基準にする)

    public Transform neck;

    public float heightOffset = 1f;
    void Update()
    {
        if (Keyboard.current == null) return;

        if (Keyboard.current.enterKey.wasPressedThisFrame ||
            Keyboard.current.numpadEnterKey.wasPressedThisFrame)
        {
            Debug.Log("Enter Key is pushed.");
            Vector3 spawnPos = neck.position + Vector3.up * heightOffset;
            Instantiate(particlePrefab, spawnPos, neck.rotation);
        }
    }
}