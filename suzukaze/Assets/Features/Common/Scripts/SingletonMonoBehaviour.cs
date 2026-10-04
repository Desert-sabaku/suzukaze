using UnityEngine;

namespace Features.Common.Scripts
{
    public abstract class SingletonMonoBehaviour<T> : MonoBehaviour where T : SingletonMonoBehaviour<T>
    {
        private static T _instance;

        public static T Instance => _instance ??= FindAnyObjectByType<T>();
    }

    public abstract class SingletonMonoBehaviourAutoCreate<T> : MonoBehaviour
        where T : SingletonMonoBehaviourAutoCreate<T>
    {
        private static T _instance;

        public static T Instance
        {
            get
            {
                if (_instance != null) return _instance;
                _instance = FindAnyObjectByType<T>();

                if (_instance != null) return _instance;
                var obj = new GameObject(typeof(T).Name);
                _instance = obj.AddComponent<T>();
                DontDestroyOnLoad(obj);
                return _instance;
            }
        }
    }
}