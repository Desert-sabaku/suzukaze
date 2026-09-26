using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Audio;

public class UnderwaterEffect : MonoBehaviour
{
    [Header("判定基準")]
    public Transform waterPlane;
    public Camera targetCamera;

    [Header("見た目演出")]
    public Volume underwaterVolume;
    public Color fogColor = new Color(0.1f, 0.3f, 0.4f);
    public float fogDensity = 0.05f;

    [Header("プレイヤー挙動")]
    public PlayerMove playerMove;

    [Header("音")]
    public AudioMixer audioMixer;
    public AudioMixerSnapshot underwaterSnapshot;
    public AudioMixerSnapshot normalSnapshot;
    public float audioTransitionTime = 0.5f;

    [Header("気泡パーティクル")]
    public ParticleSystem bubbleParticle; // プレイヤーの子にしておく想定

    bool isUnderwater = false;

    void Update()
    {
        bool nowUnderwater = targetCamera.transform.position.y < waterPlane.position.y;

        if (nowUnderwater != isUnderwater)
        {
            isUnderwater = nowUnderwater;
            SetUnderwaterState(isUnderwater);
        }
    }

    void SetUnderwaterState(bool underwater)
    {
        // A. Post Processing(色味)
        if (underwaterVolume != null)
            underwaterVolume.weight = underwater ? 1f : 0f;

        // B. フォグ
        RenderSettings.fog = underwater;
        if (underwater)
        {
            RenderSettings.fogColor = fogColor;
            RenderSettings.fogDensity = fogDensity;
        }

        // C. プレイヤーの重力・速度
        if (playerMove != null)
            playerMove.isUnderwater = underwater;

        // D. 音のこもり
        if (audioMixer != null)
        {
            if (underwater)
                underwaterSnapshot.TransitionTo(audioTransitionTime);
            else
                normalSnapshot.TransitionTo(audioTransitionTime);
        }

        // E. 気泡パーティクル
        if (bubbleParticle != null)
        {
            if (underwater) bubbleParticle.Play();
            else bubbleParticle.Stop();
        }
    }
}