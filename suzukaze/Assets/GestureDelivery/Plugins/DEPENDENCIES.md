# Pinned managed plugins

| Installed DLL (netstandard2.0) | NuGet version | License |
| --- | --- | --- |
| Google.Protobuf | **3.33.5** | BSD-3-Clause, Google |
| System.Runtime.CompilerServices.Unsafe | **4.5.2** | MIT, Microsoft |

`tools/restore_unity_protobuf.py` pins both NuGet package SHA-256 values and
the upstream Google license SHA-256. Both actual DLLs and extracted `.nuspec`
metadata/licenses are committed (DLLs follow the repository's Git LFS rules).
Restore requires Python 3 and HTTPS access
to NuGet and GitHub; using the committed DLLs requires neither Python nor
NuGet. All plugins use Unity auto-reference; the generated protocol assembly
therefore resolves Google.Protobuf without schema edits.

Google.Protobuf's netstandard2.0 target declares System.Memory >=4.5.3 and
Unsafe >=4.5.2. The .NET Standard 2.1 API profile in Unity 6000 supplies the
Memory/Span, Buffers, and Numerics.Vectors APIs. Those framework types must
**not** be duplicated by copying their netstandard2.0 compatibility DLLs into
Assets. The transitive graph for the 2.0 compatibility packages would be:

* System.Memory 4.5.3 -> System.Buffers 4.4.0,
  System.Numerics.Vectors 4.4.0, Unsafe 4.5.2.
* Buffers/Vectors/Unsafe's netstandard2.0 targets add no other packages.

Thus only Unsafe is deployed alongside Protobuf for the supported **2.1**
profile. Other API profiles are not supported by this plugin set. In the
portable .NET 8 runner Unsafe is framework-supplied, so that runner does not
prove Unity's loading of the shipped Unsafe DLL; verify Unity import/player
linking on Windows before rollout. Preserve the license texts when distributing
players containing these libraries.
