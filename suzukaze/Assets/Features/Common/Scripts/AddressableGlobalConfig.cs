using System;
using Cysharp.Threading.Tasks;
using UnityEngine;
using UnityEngine.AddressableAssets;

namespace Features.Common.Scripts
{
    internal sealed class AddressableGlobalConfigAttribute : Attribute
    {
        public AddressableGlobalConfigAttribute(string address)
        {
            Address = address;
        }

        public string Address { get; }
    }

    public abstract class AddressableGlobalConfig<T> : ScriptableObject where T : AddressableGlobalConfig<T>
    {
        private static T _instance;

        public static async UniTask<T> GetInstanceAsync()
        {
            if (_instance != null) return _instance;

            var attribute = (AddressableGlobalConfigAttribute)Attribute.GetCustomAttribute(
                typeof(T),
                typeof(AddressableGlobalConfigAttribute)
            );
            if (attribute == null)
                throw new InvalidOperationException(
                    $"AddressableGlobalConfigAttribute is not defined for {typeof(T).Name}");

            var instance = await Addressables.LoadAssetAsync<T>(attribute.Address);
            if (instance == null)
                throw new InvalidOperationException($"Failed to load AddressableGlobalConfig for {typeof(T).Name}");
            _instance = instance;
            return _instance;
        }
    }
}