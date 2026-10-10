using System;
using Suzukaze.Gesture;
using TMPro;
using UnityEngine;
using UnityEngine.InputSystem;
using UnityEngine.SceneManagement;

// スタート画面(Scene_ch) → マップ(ランダム)で遊戯 → リザルト → スタート画面 の流れを管理する。
// Scene_ch が読み込まれると Resources/GameFlowManager を自動で生成し、シーンをまたいで残る。
// Scene_ch には手を入れていない。マップのシーンを直接再生した場合は生成されず、既存の挙動のまま。
public class GameFlowManager : MonoBehaviour
{
    public enum FlowState { Title, Playing, Result }

    public const string StartScene = "Scene_ch";
    const string PrefabPath = "GameFlowManager";

    public static GameFlowManager Instance { get; private set; }

    [Header("Scenes")]
    [Tooltip("遊戯で使うマップ。この中からランダムに選ぶ(Build Settings への登録が必要)")]
    public string[] mapScenes = { "Forest", "river", "sea", "☆1湖" };

    [Header("Timing")]
    public float playSeconds = 210f;
    public float resultSeconds = 10f;

    [Header("Input")]
    [Tooltip("礼の所作が入るまでの仮の開始キー。リザルトを飛ばすのにも使う")]
    public Key startKey = Key.Space;

    [Header("UI")]
    public TMP_FontAsset font;

    public FlowState State { get; private set; } = FlowState.Title;
    public float Remaining { get; private set; }
    public FuryuScore Score { get; } = new FuryuScore();
    public event Action<FlowState> StateChanged;

    GameFlowUI ui;
    string lastMap;

    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
    static void InstallBootstrap()
    {
        SceneManager.sceneLoaded -= OnSceneLoaded;
        SceneManager.sceneLoaded += OnSceneLoaded;
        OnSceneLoaded(SceneManager.GetActiveScene(), LoadSceneMode.Single);
    }

    static void OnSceneLoaded(UnityEngine.SceneManagement.Scene scene, LoadSceneMode mode)
    {
        if (Instance != null)
        {
            Instance.HandleSceneLoaded(scene.name);
            return;
        }
        if (scene.name != StartScene) return;

        var prefab = Resources.Load<GameFlowManager>(PrefabPath);
        if (prefab != null) Instantiate(prefab).name = prefab.name;
        else new GameObject(PrefabPath).AddComponent<GameFlowManager>();
    }

    void Awake()
    {
        if (Instance != null && Instance != this)
        {
            Destroy(gameObject);
            return;
        }
        Instance = this;
        DontDestroyOnLoad(gameObject);

        Score.Attach(GestureReceiverBehaviour.GetOrCreate().Events);
        ui = new GameFlowUI(transform, font, startKey.ToString());
        SetState(FlowState.Title);
    }

    void OnDestroy()
    {
        if (Instance != this) return;
        Score.Detach();
        Instance = null;
    }

    // 礼の所作の実装からはこれを呼ぶ。スタート画面以外では無視する。
    public bool RequestStart()
    {
        if (State != FlowState.Title) return false;

        string map = PickMap();
        if (map == null)
        {
            Debug.LogError("[GameFlow] 遊戯に使えるマップがありません。mapScenes と Build Settings を確認してください。");
            return false;
        }
        SceneManager.LoadScene(map);
        BeginPlay(map);
        return true;
    }

    void HandleSceneLoaded(string sceneName)
    {
        if (sceneName == StartScene)
        {
            if (State != FlowState.Title) SetState(FlowState.Title);
        }
        else if (State == FlowState.Title && Array.IndexOf(mapScenes, sceneName) >= 0)
        {
            // Scene_ch の既存ボタンでマップを選んだ場合も、同じく時間制限付きで遊戯にする
            BeginPlay(sceneName);
        }
    }

    void Update()
    {
        if (Instance != this) return; // 破棄待ちの重複インスタンス

        var keyboard = Keyboard.current;
        bool startPressed = keyboard != null && keyboard[startKey].wasPressedThisFrame;
        bool escapePressed = keyboard != null && keyboard.escapeKey.wasPressedThisFrame;

        switch (State)
        {
            case FlowState.Title:
                if (startPressed || escapePressed) RequestStart();
                break;

            case FlowState.Playing:
                if (escapePressed)
                {
                    EnterResult();
                    break;
                }
                // Enter による手動の打ち水(ParticleOnEnter)も所作として数える
                if (keyboard != null && (keyboard.enterKey.wasPressedThisFrame
                    || keyboard.numpadEnterKey.wasPressedThisFrame))
                    Score.CountManual();
                Remaining -= Time.unscaledDeltaTime;
                if (Remaining <= 0f) EnterResult();
                break;

            case FlowState.Result:
                Remaining -= Time.unscaledDeltaTime;
                if (Remaining <= 0f || startPressed || escapePressed) ReturnToStart();
                break;
        }

        ui.SetRemaining(State, Remaining);
    }

    void BeginPlay(string map)
    {
        lastMap = map;
        Score.Reset();
        Remaining = playSeconds;
        SetState(FlowState.Playing);
    }

    void EnterResult()
    {
        Remaining = resultSeconds;
        ui.SetResult(Score);
        SetState(FlowState.Result);
    }

    void ReturnToStart()
    {
        SetState(FlowState.Title);
        SceneManager.LoadScene(StartScene);
    }

    void SetState(FlowState next)
    {
        State = next;
        Score.Counting = next == FlowState.Playing;
        ui.Show(next);
        StateChanged?.Invoke(next);
    }

    // 前回と同じマップが続かないように選ぶ
    string PickMap()
    {
        var candidates = Array.FindAll(mapScenes, Application.CanStreamedLevelBeLoaded);
        if (candidates.Length == 0) return null;
        if (candidates.Length == 1) return candidates[0];

        string map;
        do map = candidates[UnityEngine.Random.Range(0, candidates.Length)];
        while (map == lastMap);
        return map;
    }
}
