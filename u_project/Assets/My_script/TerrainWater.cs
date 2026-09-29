using System.Collections.Generic;
using UnityEngine;

[RequireComponent(typeof(ParticleSystem))]
public class TerrainWetter : MonoBehaviour
{
    [Header("濡れ用Terrain Layerのインデックス")]
    public int wetLayerIndex = 1;
    [Header("ブラシ半径(alphamapピクセル)")]
    public int brushRadius = 4;
    [Header("1回の衝突で濡れる強さ")]
    [Range(0f, 1f)] public float strength = 0.15f;
    [Header("終了時に元のペイントに戻す")]
    public bool restoreOnQuit = true;

    ParticleSystem ps;
    readonly List<ParticleCollisionEvent> events = new List<ParticleCollisionEvent>();

    // 全インスタンスで共有(元データは最初の1回だけ保存)
    static TerrainData cachedData;
    static float[,,] original;

    void Awake() => ps = GetComponent<ParticleSystem>();

    void OnParticleCollision(GameObject other)
    {
        var terrain = other.GetComponent<Terrain>();
        if (terrain == null) return;

        var td = terrain.terrainData;
        if (restoreOnQuit && cachedData == null)
        {
            cachedData = td;
            original = td.GetAlphamaps(0, 0, td.alphamapWidth, td.alphamapHeight);
            Application.quitting += Restore;
        }

        int n = ps.GetCollisionEvents(other, events);
        for (int i = 0; i < n; i++)
            Paint(terrain, events[i].intersection);
    }

    void Paint(Terrain terrain, Vector3 worldPos)
    {
        var td = terrain.terrainData;
        Vector3 local = worldPos - terrain.transform.position;

        int cx = Mathf.RoundToInt(local.x / td.size.x * td.alphamapWidth);
        int cy = Mathf.RoundToInt(local.z / td.size.z * td.alphamapHeight);

        int x0 = Mathf.Clamp(cx - brushRadius, 0, td.alphamapWidth - 1);
        int y0 = Mathf.Clamp(cy - brushRadius, 0, td.alphamapHeight - 1);
        int x1 = Mathf.Clamp(cx + brushRadius, 0, td.alphamapWidth - 1);
        int y1 = Mathf.Clamp(cy + brushRadius, 0, td.alphamapHeight - 1);
        int w = x1 - x0 + 1, h = y1 - y0 + 1;

        float[,,] a = td.GetAlphamaps(x0, y0, w, h); // [y, x, layer]
        int layers = a.GetLength(2);

        for (int y = 0; y < h; y++)
        for (int x = 0; x < w; x++)
        {
            float dist = Vector2.Distance(new Vector2(x0 + x, y0 + y), new Vector2(cx, cy));
            if (dist > brushRadius) continue;

            float add = (1f - dist / brushRadius) * strength;
            a[y, x, wetLayerIndex] = Mathf.Min(1f, a[y, x, wetLayerIndex] + add);

            float sum = 0f;
            for (int l = 0; l < layers; l++) sum += a[y, x, l];
            for (int l = 0; l < layers; l++) a[y, x, l] /= sum;
        }
        td.SetAlphamaps(x0, y0, a);
    }

    static void Restore()
    {
        if (cachedData != null && original != null)
            cachedData.SetAlphamaps(0, 0, original);
        cachedData = null;
        original = null;
        Application.quitting -= Restore;
    }
}