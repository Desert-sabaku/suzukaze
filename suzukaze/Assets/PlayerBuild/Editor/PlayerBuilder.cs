using System;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.AddressableAssets;
using UnityEditor.AddressableAssets.Settings;
using UnityEditor.Build.Reporting;
using UnityEngine;

namespace Suzukaze.Build.Editor
{
    /// <summary>
    /// Build the player for the active build target. Called in batch mode with
    /// <c>-executeMethod Suzukaze.Build.Editor.PlayerBuilder.BuildFromCommandLine</c>;
    /// pass Unity's <c>-buildTarget</c> to choose the platform.
    /// </summary>
    public static class PlayerBuilder
    {
        const string OutputArg = "-suzukazeOutput";
        const string DevelopmentArg = "-suzukazeDevelopment";
        const string AddressablesBuildWithPlayerPref = "Addressables.BuildAddressablesWithPlayerBuild";

        public static void BuildFromCommandLine()
        {
            var args = Environment.GetCommandLineArgs();
            var target = EditorUserBuildSettings.activeBuildTarget;
            var output = GetArgValue(args, OutputArg) ?? DefaultOutputPath(target);
            var development = args.Contains(DevelopmentArg);

            int exitCode;
            try
            {
                exitCode = Build(target, output, development) ? 0 : 1;
            }
            catch (Exception e)
            {
                Debug.LogException(e);
                exitCode = 1;
            }

            EditorApplication.Exit(exitCode);
        }

        [MenuItem("Suzukaze/Build Player")]
        static void BuildFromMenu()
        {
            var target = EditorUserBuildSettings.activeBuildTarget;
            Build(target, DefaultOutputPath(target), EditorUserBuildSettings.development);
        }

        static bool Build(BuildTarget target, string output, bool development)
        {
            var scenes = EditorBuildSettings.scenes
                .Where(scene => scene.enabled)
                .Select(scene => scene.path)
                .ToArray();
            if (scenes.Length == 0)
            {
                Debug.LogError("[Build] No scenes are enabled in Build Settings.");
                return false;
            }

            if (!BuildAddressablesIfNeeded())
            {
                return false;
            }

            Debug.Log($"[Build] target={target} output={output} development={development}");
            Debug.Log($"[Build] scenes:\n  {string.Join("\n  ", scenes)}");

            var options = new BuildPlayerOptions
            {
                scenes = scenes,
                locationPathName = output,
                target = target,
                targetGroup = BuildPipeline.GetBuildTargetGroup(target),
                options = development ? BuildOptions.Development : BuildOptions.None,
            };
            var summary = BuildPipeline.BuildPlayer(options).summary;

            Debug.Log(
                $"[Build] {summary.result}: {summary.totalErrors} error(s), " +
                $"{summary.totalWarnings} warning(s), {summary.totalSize / (1024 * 1024)} MB, " +
                $"{summary.totalTime:hh\\:mm\\:ss}");
            return summary.result == BuildResult.Succeeded;
        }

        /// <summary>
        /// Build Addressables content unless the player build already does it,
        /// so the result does not depend on the local Preferences value.
        /// </summary>
        static bool BuildAddressablesIfNeeded()
        {
            var settings = AddressableAssetSettingsDefaultObject.Settings;
            if (settings == null)
            {
                return true;
            }

            var buildsWithPlayer = settings.BuildAddressablesWithPlayerBuild switch
            {
                AddressableAssetSettings.PlayerBuildOption.BuildWithPlayer => true,
                AddressableAssetSettings.PlayerBuildOption.DoNotBuildWithPlayer => false,
                _ => EditorPrefs.GetBool(AddressablesBuildWithPlayerPref, true),
            };
            if (buildsWithPlayer)
            {
                return true;
            }

            Debug.Log("[Build] Building Addressables content.");
            AddressableAssetSettings.BuildPlayerContent(out var result);
            if (!string.IsNullOrEmpty(result.Error))
            {
                Debug.LogError($"[Build] Addressables build failed: {result.Error}");
                return false;
            }

            return true;
        }

        static string DefaultOutputPath(BuildTarget target)
        {
            var projectRoot = Directory.GetParent(Application.dataPath).FullName;
            var directory = Path.Combine(projectRoot, "Builds", target.ToString());
            var name = PlayerSettings.productName;
            return target switch
            {
                BuildTarget.StandaloneWindows or BuildTarget.StandaloneWindows64 =>
                    Path.Combine(directory, name + ".exe"),
                BuildTarget.StandaloneOSX => Path.Combine(directory, name + ".app"),
                _ => Path.Combine(directory, name),
            };
        }

        static string GetArgValue(string[] args, string name)
        {
            var index = Array.IndexOf(args, name);
            return index >= 0 && index + 1 < args.Length ? args[index + 1] : null;
        }
    }
}
