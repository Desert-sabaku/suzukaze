using UnityEngine;

public class HeightmapApplier : MonoBehaviour
{
    public Texture2D depthTexture; // Inspectorで深度マップPNGをアサイン
    public Terrain terrain;
    public float heightScale = 1.0f; // 0〜1の範囲を调整(通常はTerrainDataのheightに対する比率なので1.0のままでもOK)
    public bool invertDepth = false; // 手前を高くしたい場合はtrueに
    public AnimationCurve heightCurve = AnimationCurve.Linear(0, 0, 1, 1); // 地形のメリハリを調整するカーブ

    void Start()
    {
        ApplyHeightmap();
    }

    void ApplyHeightmap()
    {
        int res = terrain.terrainData.heightmapResolution;
        float[,] heights = new float[res, res];

        for (int y = 0; y < res; y++)
        {
            for (int x = 0; x < res; x++)
            {
                float u = (float)x / (res - 1);
                float v = (float)y / (res - 1);
                Color pixel = depthTexture.GetPixelBilinear(u, v);

                float h = pixel.r; // 0〜1

                if (invertDepth) h = 1.0f - h;

                h = heightCurve.Evaluate(h); // カーブで地形のメリハリを調整

                heights[y, x] = h * heightScale;
            }
        }

        terrain.terrainData.SetHeights(0, 0, heights);
    }
}