# tools/

Local copy of the KTX-Software `ktx` CLI (v4.4.2, Darwin arm64), used by
`../convert.sh` to ASTC-encode and pack the cubemap KTX2.

KTX-Software is **not** available as a Homebrew formula, so these binaries were
extracted from the official macOS installer (no system-wide install / sudo):

```sh
curl -fsSLO https://github.com/KhronosGroup/KTX-Software/releases/download/v4.4.2/KTX-Software-4.4.2-Darwin-arm64.pkg
pkgutil --expand-full KTX-Software-4.4.2-Darwin-arm64.pkg ktxpkg
# copy bin/ktx, bin/toktx and lib/libktx.4.4.2.dylib here, then:
ln -sf libktx.4.4.2.dylib libktx.4.dylib        # ktx links @rpath/libktx.4.dylib
install_name_tool -add_rpath @loader_path ktx    # find the dylib next to the binary
codesign --force -s - ktx                         # re-sign after modifying (arm64)
```

Verify: `./ktx --version` → `ktx version: v4.4.2`.

Contents: `ktx`, `toktx`, `libktx.4.4.2.dylib`, `libktx.4.dylib` (symlink).
