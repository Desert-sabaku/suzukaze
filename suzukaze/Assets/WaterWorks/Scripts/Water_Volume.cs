using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.RenderGraphModule;
using UnityEngine.Rendering.RenderGraphModule.Util;
using UnityEngine.Rendering.Universal;

public class Water_Volume : ScriptableRendererFeature
{
    class CustomRenderPass : ScriptableRenderPass
    {
        private Material _material;

        public CustomRenderPass(Material mat)
        {
            _material = mat;
        }

        // Execute / FrameCleanup の代わりにこれ1つで完結する
        public override void RecordRenderGraph(RenderGraph renderGraph, ContextContainer frameData)
        {
            UniversalCameraData cameraData = frameData.Get<UniversalCameraData>();

            // 元の if(renderingData.cameraData.cameraType != CameraType.Reflection) に相当
            if (cameraData.cameraType == CameraType.Reflection)
                return;

            if (_material == null)
                return;

            UniversalResourceData resourceData = frameData.Get<UniversalResourceData>();
            TextureHandle source = resourceData.activeColorTexture;

            // 元の GetTemporaryRT + tempRenderTarget に相当する一時テクスチャ
            TextureDesc desc = renderGraph.GetTextureDesc(source);
            desc.name = "_TemporaryColourTexture";
            desc.clearBuffer = false;
            TextureHandle tempTexture = renderGraph.CreateTexture(desc);

            // Blit(commandBuffer, source, tempRenderTarget, _material) に相当
            RenderGraphUtils.BlitMaterialParameters toTemp = new(source, tempTexture, _material, 0);
            renderGraph.AddBlitPass(toTemp, passName: "Water_Volume_Apply");

            // Blit(commandBuffer, tempRenderTarget, source) に相当(マテリアルなしの単純コピー)
            renderGraph.AddCopyPass(tempTexture, source, passName: "Water_Volume_CopyBack");
        }
    }

    [System.Serializable]
    public class _Settings
    {
        public Material material = null;
        public RenderPassEvent renderPass = RenderPassEvent.AfterRenderingSkybox;
    }

    public _Settings settings = new _Settings();

    CustomRenderPass m_ScriptablePass;

    public override void Create()
    {
        if (settings.material == null)
        {
            settings.material = (Material)Resources.Load("Water_Volume");
        }

        m_ScriptablePass = new CustomRenderPass(settings.material);
        m_ScriptablePass.renderPassEvent = settings.renderPass;
    }

    // AddRenderPasses自体は変更不要（このシグネチャのままRender Graphでも使える）
    public override void AddRenderPasses(ScriptableRenderer renderer, ref RenderingData renderingData)
    {
        renderer.EnqueuePass(m_ScriptablePass);
    }
}