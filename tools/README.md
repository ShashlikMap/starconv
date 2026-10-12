# tools/

Holds the KTX-Software `ktx` CLI used by `../convert.sh` to encode/pack the KTX2
cubemaps. The binaries are **not** committed to git — fetch them after cloning.

## Get the tooling (macOS)

```sh
sh tools/fetch-ktx.sh        # downloads KTX-Software, installs ktx into tools/
```

This downloads the official macOS installer for your arch (arm64 / x86_64),
expands it without sudo, and installs the CLI locally. What it does under the hood:

```sh
curl -fsSLO https://github.com/KhronosGroup/KTX-Software/releases/download/v4.4.2/KTX-Software-4.4.2-Darwin-arm64.pkg
pkgutil --expand-full KTX-Software-4.4.2-Darwin-arm64.pkg ktxpkg
# copy the payload binaries into tools/:
cp ktxpkg/KTX-Software-4.4.2-Darwin-arm64-tools.pkg/Payload/usr/local/bin/ktx   tools/
cp ktxpkg/KTX-Software-4.4.2-Darwin-arm64-tools.pkg/Payload/usr/local/bin/toktx tools/
cp ktxpkg/KTX-Software-4.4.2-Darwin-arm64-library.pkg/Payload/usr/local/lib/libktx.4.4.2.dylib tools/
ln -sf libktx.4.4.2.dylib tools/libktx.4.dylib   # ktx links @rpath/libktx.4.dylib
install_name_tool -add_rpath @loader_path tools/ktx   # find the dylib next to the binary
codesign --force -s - tools/ktx                        # re-sign after modifying (arm64)
```

Verify: `tools/ktx --version` → `ktx version: v4.4.2`.

Resulting (git-ignored) contents: `ktx`, `toktx`, `libktx.4.4.2.dylib`,
`libktx.4.dylib` (symlink).

## Linux / Windows

Install KTX-Software from its
[releases](https://github.com/KhronosGroup/KTX-Software/releases); `ktx` lands on
your `PATH` and `convert.sh` uses it automatically when `tools/ktx` is absent.
