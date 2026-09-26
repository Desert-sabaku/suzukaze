using UnityEngine;

public class WaterfallScroll : MonoBehaviour
{
    public float speed = 1.0f;
    public string normalPropertyName = "Texture2D_6d0f902902b04ba687ee00a51db7ba6d"; // 確認したReference名に置き換える
    Renderer rend;

    void Start() => rend = GetComponent<Renderer>();

    void Update()
    {
        float offset = Time.time * speed;
        rend.material.SetTextureOffset(normalPropertyName, new Vector2(0, -offset));
    }
}