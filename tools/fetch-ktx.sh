#!/usr/bin/env sh
# Download the KTX-Software `ktx` CLI and install it into this tools/ directory
# (no sudo, no system-wide install). macOS only (uses pkgutil/install_name_tool/
# codesign). On Linux/Windows install KTX-Software from its releases instead; its
# `ktx` goes on PATH and convert.sh will find it there.
#
# Usage: sh tools/fetch-ktx.sh
set -eu

VER=4.4.2
TOOLS_DIR="$(cd "$(dirname "$0")" && pwd)"

case "$(uname -s)" in
  Darwin) ;;
  *) echo "This script is macOS-only. Install KTX-Software ${VER} from" \
          "https://github.com/KhronosGroup/KTX-Software/releases and ensure" \
          "'ktx' is on your PATH." >&2; exit 1;;
esac

case "$(uname -m)" in
  arm64) ARCH=arm64;;
  x86_64) ARCH=x86_64;;
  *) echo "Unsupported arch: $(uname -m)" >&2; exit 1;;
esac

PKG="KTX-Software-${VER}-Darwin-${ARCH}.pkg"
URL="https://github.com/KhronosGroup/KTX-Software/releases/download/v${VER}/${PKG}"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

echo ">> downloading ${PKG}"
curl -fsSL -o "$WORK/ktx.pkg" "$URL"

echo ">> expanding"
pkgutil --expand-full "$WORK/ktx.pkg" "$WORK/ktxpkg"

BIN="$WORK/ktxpkg/KTX-Software-${VER}-Darwin-${ARCH}-tools.pkg/Payload/usr/local/bin"
LIB="$WORK/ktxpkg/KTX-Software-${VER}-Darwin-${ARCH}-library.pkg/Payload/usr/local/lib"

echo ">> installing into $TOOLS_DIR"
cp "$BIN/ktx" "$BIN/toktx" "$LIB/libktx.${VER}.dylib" "$TOOLS_DIR/"
chmod +x "$TOOLS_DIR/ktx" "$TOOLS_DIR/toktx"
ln -sf "libktx.${VER}.dylib" "$TOOLS_DIR/libktx.4.dylib"   # ktx links @rpath/libktx.4.dylib

for b in ktx toktx; do
  install_name_tool -add_rpath @loader_path "$TOOLS_DIR/$b" 2>/dev/null || true
  codesign --force -s - "$TOOLS_DIR/$b" >/dev/null 2>&1 || true   # re-sign after edit (arm64)
done

echo ">> done:"
"$TOOLS_DIR/ktx" --version
