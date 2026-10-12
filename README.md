# starconv — equirectangular → ASTC/BC7 KTX2 cubemaps

Converts a 2:1 equirectangular panorama into mipmapped, 6-face **KTX2 cubemaps**
ready to use as a skybox/environment in any engine or tool that consumes KTX2.
Every run produces **both** compressed formats:

- `out/astc.ktx2` — `ASTC_4x4_SRGB_BLOCK`
- `out/bc7.ktx2` — `BC7_SRGB_BLOCK`

## Setup

Two things are needed: Python with Pillow + numpy, and the KTX-Software `ktx` CLI.

**1. Python deps** (Python 3.9+):

```sh
pip3 install pillow numpy
```

**2. The `ktx` CLI** (KTX-Software, used to encode/pack the KTX2 files):

- **macOS** — run the bundled fetcher, which downloads KTX-Software and installs
  `ktx` into `tools/` with no sudo (the `tools/` binaries are not committed, so do
  this after cloning):

  ```sh
  sh tools/fetch-ktx.sh        # -> tools/ktx version: v4.4.2
  ```

- **Linux / Windows** — install KTX-Software from its
  [releases](https://github.com/KhronosGroup/KTX-Software/releases) (`.deb`/`.rpm`/
  `.tar.bz2` / installer). That puts `ktx` on your `PATH`; `convert.sh` uses it
  automatically when `tools/ktx` is absent.

`convert.sh` prefers `tools/ktx` and otherwise falls back to a `ktx` on `PATH`.
See `tools/README.md` for what the fetcher does under the hood.

## Usage

```sh
sh convert.sh <input-image> [face_size] [brightness] [tilt] [sharpen]
```

- `input-image` — equirectangular (2:1) source image, **required**
- `face_size` — cubemap face size in px (default `256`)
- `brightness` — linear-light multiplier applied to every face (default `1.0`);
  `<1` darkens, `>1` brightens. Dimming is done in linear light so colors
  stay true. (`equirect_to_faces.py --brightness` if calling Python directly.)
- `tilt` — pitch the whole cubemap about the horizontal X axis, `0..90` degrees
  (default `0`). Rotation is applied to the sample directions, so the result
  stays seamless. (`equirect_to_faces.py --tilt`.)
- `sharpen` — unsharp-mask amount applied after downscaling (default `0` = off).
  `~0.5-1.5` tightens fine detail; higher adds more ringing around bright
  highlights. Done in linear light. (`equirect_to_faces.py --sharpen`.)

Output: `out/astc.ktx2` (plus intermediate face PNGs in `out/faces/`).

```sh
sh convert.sh panorama.tif                # 256² cubemap, full brightness, no tilt
sh convert.sh panorama.tif 512            # 512²
sh convert.sh panorama.tif 256 0.4        # 256², dimmed to 40%
sh convert.sh panorama.tif 256 0.4 30     # 256², dimmed, tilted 30°
sh convert.sh panorama.tif 512 1.0 0 1.0  # 512², sharpened
```

## Pipeline

1. **`equirect_to_faces.py`** (Python, PIL + numpy) renders 6 square faces from
   the panorama, using the KTX2/Vulkan cubemap convention (left-handed, +Y up,
   +Z forward, top-left origin), face order **+X, −X, +Y, −Y, +Z, −Z**. The whole
   sample → downscale → brightness pipeline runs in **linear light**: each face is
   6× supersampled then **area-averaged in linear space**. This preserves the
   energy of sub-pixel bright points — averaging in gamma/sRGB space collapses
   faint highlights toward black and makes them vanish. Supersample is tunable
   (`--supersample`); lower it if memory is tight at large `--size`.
2. **`tools/ktx create`** encodes the faces to `ASTC_4x4_SRGB_BLOCK`, marks the
   result as a cubemap (`--cubemap`), tags sRGB (`--assign-tf srgb`), and
   generates the full mip chain (`--generate-mipmap`).
3. **BC7** has no direct encoder in `ktx create`, so it is produced by encoding the
   same faces to UASTC and then `ktx transcode --target bc7` → `out/bc7.ktx2`.

## Verifying the output

```sh
tools/ktx info out/astc.ktx2   # vkFormat VK_FORMAT_ASTC_4x4_SRGB_BLOCK, faceCount 6
tools/ktx info out/bc7.ktx2    # vkFormat VK_FORMAT_BC7_SRGB_BLOCK,      faceCount 6
```

Use `out/astc.ktx2` / `out/bc7.ktx2` as cubemap assets in your renderer. Engines
typically select the format their GPU supports — ASTC on mobile and Apple Silicon
(Metal), BC7 on most desktop Vulkan/D3D12 GPUs.
