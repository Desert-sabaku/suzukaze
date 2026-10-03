using System.IO;
using UnityEditor;
using UnityEngine;

namespace Suzukaze.Bridge.Editor
{
    /// <summary>Report missing buf output; Generated/*.cs is not committed.</summary>
    [InitializeOnLoad]
    internal static class GeneratedBindingsCheck
    {
        static GeneratedBindingsCheck()
        {
            var generated = Path.Combine(Application.dataPath, "Bridge", "Generated");
            if (Directory.Exists(generated) && Directory.GetFiles(generated, "*.cs").Length > 0)
            {
                return;
            }

            Debug.LogError(
                "Gesture protobuf bindings are missing in Assets/Bridge/Generated. " +
                "Run `buf generate` in the repository's proto/ directory.");
        }
    }
}
