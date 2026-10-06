using UnityEngine;

// WaterSurfaceMesh の波に乗せて、物を上下・前後に揺らしながら傾ける。
// 置いた位置を基準にし、水面の点と一緒に動く (流されてどこかへ行くことはない)。
public class FloatingObject : MonoBehaviour
{
    [Tooltip("乗せる水面。空ならシーンから探す")]
    public WaterSurfaceMesh water;
    [Tooltip("水面の高さを測る範囲の半径。物の大きさくらいにすると、細かい波で暴れず大きな波に沿って傾く")]
    [Min(0.01f)] public float footprint = 0.6f;
    [Tooltip("波の前後の動きにどれだけ付いていくか (0 で上下だけ)")]
    [Range(0f, 1f)] public float horizontalFollow = 1f;
    [Tooltip("波の傾きにどれだけ合わせて傾くか")]
    [Range(0f, 1.5f)] public float tiltAmount = 1f;
    [Tooltip("傾きが追いつくまでの速さ。小さいほどゆったり揺れる")]
    [Min(0.1f)] public float tiltResponse = 4f;

    Vector2 anchor;
    float restOffset;
    Quaternion baseRotation;
    Quaternion tilt = Quaternion.identity;

    void Start()
    {
        if (water == null) water = FindAnyObjectByType<WaterSurfaceMesh>();
        var p = transform.position;
        anchor = new Vector2(p.x, p.z);
        // 置いたときの水面との高さの差 (どれだけ沈んで浮かぶか) を保つ
        restOffset = water != null ? p.y - water.transform.position.y : 0f;
        baseRotation = transform.rotation;
    }

    void LateUpdate()
    {
        if (water == null || !water.isActiveAndEnabled) return;
        if (!water.SampleSurface(anchor, out var center, out _)) return;

        // 物の周りの 4 点の高さから傾きを決める
        water.SampleSurface(anchor + new Vector2(footprint, 0f), out var east, out _);
        water.SampleSurface(anchor - new Vector2(footprint, 0f), out var west, out _);
        water.SampleSurface(anchor + new Vector2(0f, footprint), out var north, out _);
        water.SampleSurface(anchor - new Vector2(0f, footprint), out var south, out _);
        float height = (center.y * 2f + east.y + west.y + north.y + south.y) / 6f;
        var normal = new Vector3(-(east.y - west.y) / (2f * footprint), 1f, -(north.y - south.y) / (2f * footprint)).normalized;

        transform.position = new Vector3(
            anchor.x + center.x * horizontalFollow,
            water.transform.position.y + height + restOffset,
            anchor.y + center.z * horizontalFollow);

        var target = Quaternion.SlerpUnclamped(Quaternion.identity, Quaternion.FromToRotation(Vector3.up, normal), tiltAmount);
        tilt = Quaternion.Slerp(tilt, target, 1f - Mathf.Exp(-tiltResponse * Time.deltaTime));
        transform.rotation = tilt * baseRotation;
    }
}
