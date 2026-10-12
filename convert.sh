#!/usr/bin/env sh
# Convert an equirectangular panorama into ASTC 4x4 and BC7 sRGB KTX2 cubemaps.
# Both formats are always produced (astc.ktx2 + bc7.ktx2).
#
# Usage: sh convert.sh <input-image> [face_size] [brightness] [tilt] [sharpen]
#   input-image equirectangular (2:1) source  (required)
#   face_size   cubemap face size in px        (default 256)
#   brightness  linear-light multiplier, <1 darkens (default 1.0, e.g. 0.5 = dimmer)
#   tilt        tilt the cubemap about the X axis, 0..90 degrees (default 0)
#   sharpen     unsharp-mask amount after downscale, 0=off ~0.5-1.5 crisper (default 0)
set -eu

IN="${1:?usage: sh convert.sh <input-image> [face_size] [brightness] [tilt] [sharpen]}"
SIZE="${2:-256}"
BRIGHTNESS="${3:-1.0}"
TILT="${4:-0}"
SHARPEN="${5:-0}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
OUT_DIR="$SCRIPT_DIR/out"
FACES="$OUT_DIR/faces"
mkdir -p "$FACES"

# Prefer the bundled ktx in tools/, otherwise fall back to one on PATH.
if [ -x "$SCRIPT_DIR/tools/ktx" ]; then
  KTX="$SCRIPT_DIR/tools/ktx"
elif command -v ktx >/dev/null 2>&1; then
  KTX="ktx"
else
  echo "error: ktx CLI not found. Run 'sh tools/fetch-ktx.sh' (macOS) or install" \
       "KTX-Software so 'ktx' is on PATH. See tools/README.md." >&2
  exit 1
fi

echo ">> rendering cube faces from $IN"
python3 -I "$SCRIPT_DIR/equirect_to_faces.py" "$IN" "$FACES" \
  --size "$SIZE" --brightness "$BRIGHTNESS" --tilt "$TILT" --sharpen "$SHARPEN"

# The six cube faces, in KTX2 order (+X,-X,+Y,-Y,+Z,-Z), shared by both encoders.
set -- "$FACES/px.png" "$FACES/nx.png" \
       "$FACES/py.png" "$FACES/ny.png" \
       "$FACES/pz.png" "$FACES/nz.png"

echo ">> encoding ASTC 4x4 sRGB cubemap -> $OUT_DIR/astc.ktx2"
"$KTX" create \
  --format ASTC_4x4_SRGB_BLOCK \
  --cubemap \
  --assign-tf srgb \
  --generate-mipmap \
  --astc-quality thorough \
  "$@" "$OUT_DIR/astc.ktx2"

# BC7 has no direct encoder in `ktx create`; encode to UASTC then transcode to BC7.
echo ">> encoding BC7 sRGB cubemap -> $OUT_DIR/bc7.ktx2"
UASTC_TMP="$OUT_DIR/.uastc.ktx2"
"$KTX" create \
  --format R8G8B8A8_SRGB \
  --encode uastc \
  --cubemap \
  --assign-tf srgb \
  --generate-mipmap \
  "$@" "$UASTC_TMP"
"$KTX" transcode --target bc7 "$UASTC_TMP" "$OUT_DIR/bc7.ktx2"
rm -f "$UASTC_TMP"

echo ">> done: $OUT_DIR/astc.ktx2  $OUT_DIR/bc7.ktx2"
