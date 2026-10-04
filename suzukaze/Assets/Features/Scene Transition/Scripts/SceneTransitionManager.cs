using System;
using System.Threading.Tasks;
using Cysharp.Threading.Tasks;
using Features.Common.Scripts;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace Features.Scene_Transition.Scripts
{
    /// <summary>
    /// シーン遷移を管理する
    /// </summary>
    public class SceneTransitionManager : SingletonMonoBehaviourAutoCreate<SceneTransitionManager>
    {
        private void Awake()
        {
            DontDestroyOnLoad(gameObject);
        }
        
        public async UniTask LoadSceneAsync(string sceneName)
        {
            var currentScene = SceneManager.GetActiveScene();
            
            // 現在のシーンからカメラを取得
            var currentCamera = Camera.main;
        }
    }
}