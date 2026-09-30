"""Restore the exact Unity .NET Standard 2.1 plugin set. Python 3 stdlib only."""
import hashlib
import io
from pathlib import Path
import urllib.request
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "suzukaze/Assets/GestureDelivery"
PACKAGES = (
    ("Google.Protobuf", "3.33.5",
     "7746b27bf78fb0abcb0adb786f7f6ad68d3ad18ff009fda1e67f1b429abea2b9"),
    ("System.Runtime.CompilerServices.Unsafe", "4.5.2",
     "f1e5175c658ed8b2fbb804cc6727b6882a503844e7da309c8d4846e9ca11e4ef"),
)


def download(url, checksum):
    with urllib.request.urlopen(url, timeout=60) as response:
        data = response.read()
    if hashlib.sha256(data).hexdigest() != checksum:
        raise ValueError(f"Checksum mismatch: {url}")
    return data


def metadata():
    """Stable GUIDs for integration-owned assets; never rewrite existing metadata."""
    for path in sorted(ASSETS.rglob("*")):
        if path.suffix == ".meta" or "Generated" in path.parts:
            continue
        meta = Path(str(path) + ".meta")
        if meta.exists():
            continue
        guid = uuid.uuid5(uuid.NAMESPACE_URL, "suzukaze/" + path.relative_to(ASSETS).as_posix()).hex
        text = f"fileFormatVersion: 2\nguid: {guid}\n"
        if path.is_dir():
            text += "folderAsset: yes\nDefaultImporter:\n  externalObjects: {}\n"
        elif path.suffix == ".dll":
            text += ("PluginImporter:\n  externalObjects: {}\n  serializedVersion: 2\n"
                     "  isPreloaded: 0\n  isOverridable: 0\n  isExplicitlyReferenced: 0\n"
                     "  validateReferences: 1\n  platformData:\n"
                     "  - first:\n      Any:\n    second:\n      enabled: 1\n      settings: {}\n")
        elif path.suffix == ".cs":
            text += "MonoImporter:\n  externalObjects: {}\n  serializedVersion: 2\n  defaultReferences: []\n  executionOrder: 0\n  icon: {instanceID: 0}\n"
        elif path.suffix == ".asmdef":
            text += "AssemblyDefinitionImporter:\n  externalObjects: {}\n"
        elif path.suffix == ".prefab":
            text += "PrefabImporter:\n  externalObjects: {}\n"
        elif path.suffix == ".txt":
            text += "TextScriptImporter:\n  externalObjects: {}\n"
        else:
            text += "DefaultImporter:\n  externalObjects: {}\n"
        meta.write_text(text, encoding="utf-8")


def normalized_text(data):
    # Keep upstream wording while making extracted notices stable LF text.
    return b"\n".join(line.rstrip() for line in data.splitlines()) + b"\n"


def main():
    plugins = ASSETS / "Plugins"
    licenses = plugins / "Licenses"
    licenses.mkdir(parents=True, exist_ok=True)
    for name, version, checksum in PACKAGES:
        lower = name.lower()
        url = f"https://api.nuget.org/v3-flatcontainer/{lower}/{version}/{lower}.{version}.nupkg"
        archive = zipfile.ZipFile(io.BytesIO(download(url, checksum)))
        (plugins / f"{name}.dll").write_bytes(archive.read(f"lib/netstandard2.0/{name}.dll"))
        (licenses / f"{name}.nuspec.txt").write_bytes(normalized_text(archive.read(f"{name}.nuspec")))
        if name != "Google.Protobuf":
            (licenses / f"{name}.LICENSE.txt").write_bytes(normalized_text(archive.read("LICENSE.TXT")))
        print(f"Verified and restored {name} {version}")
    license_data = download(
        "https://raw.githubusercontent.com/protocolbuffers/protobuf/v33.5/LICENSE",
        "6e5e117324afd944dcf67f36cf329843bc1a92229a8cd9bb573d7a83130fea7d")
    (licenses / "Google.Protobuf.LICENSE.txt").write_bytes(license_data)
    metadata()


if __name__ == "__main__":
    main()
