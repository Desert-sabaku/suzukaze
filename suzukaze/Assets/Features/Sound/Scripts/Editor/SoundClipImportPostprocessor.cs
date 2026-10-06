using System.IO;
using UnityEditor;
using UnityEngine;

namespace Features.Sound.Scripts.Editor
{
    /// <summary>
    ///     Sound/Clips に追加した音声の初回インポート設定を揃える。手で変えた設定は上書きしない。
    ///     長い環境音 (Ambient) はストリーミング、それ以外はメモリに圧縮して載せる
    /// </summary>
    public class SoundClipImportPostprocessor : AssetPostprocessor
    {
        private const string ClipsRoot = "Assets/Features/Sound/Clips/";

        private void OnPreprocessAudio()
        {
            if (!assetPath.StartsWith(ClipsRoot)) return;
            var importer = (AudioImporter)assetImporter;
            if (!importer.importSettingsMissing) return;

            // 2D で流すベッド (ファイル名が *Bed) は左右の広がりを残し、3D 音源は定位のためモノラルにする
            var isBed = Path.GetFileNameWithoutExtension(assetPath).EndsWith("Bed");
            importer.forceToMono = !isBed;
            importer.loadInBackground = true;

            var settings = importer.defaultSampleSettings;
            settings.compressionFormat = AudioCompressionFormat.Vorbis;
            settings.quality = 0.6f;
            settings.sampleRateSetting = AudioSampleRateSetting.PreserveSampleRate;
            settings.loadType = assetPath.Contains("/Ambient/")
                ? AudioClipLoadType.Streaming
                : AudioClipLoadType.CompressedInMemory;
            importer.defaultSampleSettings = settings;
        }
    }
}
