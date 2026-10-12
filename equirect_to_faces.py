#!/usr/bin/env python3
"""Convert a 2:1 equirectangular panorama into 6 square cubemap face PNGs.

Faces are written with the KTX2/Vulkan cubemap convention (left-handed, +Y up,
+Z forward, top-left texcoord origin) so they can be fed directly to
`ktx create --cubemap` in the order +X, -X, +Y, -Y, +Z, -Z.
"""

import argparse
import math
import os

import numpy as np
from PIL import Image

# Per-face direction basis. For normalized face coords a (left->right) and
# b (top->bottom), both in [-1, 1], the sampled direction is:
#     dir = forward + a * right + b * down
# Listed in KTX2 cubemap order.
FACES = [
    ("px", (1.0, 0.0, 0.0), (0.0, 0.0, -1.0), (0.0, -1.0, 0.0)),   # +X -> dir (1,-b,-a)
    ("nx", (-1.0, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, -1.0, 0.0)),   # -X -> dir (-1,-b,a)
    ("py", (0.0, 1.0, 0.0), (1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),     # +Y -> dir (a,1,b)
    ("ny", (0.0, -1.0, 0.0), (1.0, 0.0, 0.0), (0.0, 0.0, -1.0)),   # -Y -> dir (a,-1,-b)
    ("pz", (0.0, 0.0, 1.0), (1.0, 0.0, 0.0), (0.0, -1.0, 0.0)),    # +Z -> dir (a,-b,1)
    ("nz", (0.0, 0.0, -1.0), (-1.0, 0.0, 0.0), (0.0, -1.0, 0.0)),  # -Z -> dir (-a,-b,-1)
]


def srgb_to_linear(c):
    """sRGB [0,1] -> linear [0,1] (elementwise)."""
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(c):
    """linear [0,1] -> sRGB [0,1] (elementwise)."""
    c = np.clip(c, 0.0, 1.0)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1.0 / 2.4) - 0.055)


def downscale_linear(face, size):
    """Area-average a linear-light face down to size x size.

    face is (size*k, size*k, 3). Averaging in linear light (not gamma)
    preserves the energy of sub-pixel point sources, so faint stars survive
    the minification instead of collapsing toward black. Box/area averaging
    (rather than LANCZOS) avoids ringing halos around bright stars.
    """
    src_res = face.shape[0]
    if src_res == size:
        return face
    k = src_res // size
    return face.reshape(size, k, size, k, 3).mean(axis=(1, 3))


def _blur_axis(a, kernel, axis):
    """1D convolution of array a with kernel along axis, reflect-padded."""
    r = len(kernel) // 2
    pad = [(r, r) if ax == axis else (0, 0) for ax in range(a.ndim)]
    ap = np.pad(a, pad, mode="reflect")
    out = np.zeros_like(a)
    for i, w in enumerate(kernel):
        sl = [slice(None)] * a.ndim
        sl[axis] = slice(i, i + a.shape[axis])
        out += w * ap[tuple(sl)]
    return out


def gaussian_blur(face, sigma):
    """Separable Gaussian blur of a float image (H, W, 3)."""
    r = max(1, int(round(3.0 * sigma)))
    x = np.arange(-r, r + 1, dtype=np.float64)
    k = np.exp(-(x * x) / (2.0 * sigma * sigma))
    k /= k.sum()
    return _blur_axis(_blur_axis(face, k, 0), k, 1)


def sharpen_linear(face, amount, radius=1.0):
    """Unsharp-mask a linear-light face: face + amount*(face - blur(face)).

    Run in linear light so sharpening boosts star/dust-lane energy consistently
    with the rest of the pipeline. amount == 0 is a no-op; ~0.5-1.5 is a sensible
    range, higher = crisper (and more ringing around bright stars).
    """
    if amount == 0.0:
        return face
    blurred = gaussian_blur(face, radius)
    return face + amount * (face - blurred)


def bilinear_wrap(src, u, v):
    """Sample src[H,W,3] float array at pixel coords (u,v).

    u wraps horizontally (seamless 360), v clamps vertically (poles).
    u, v are float arrays of matching shape giving fractional pixel positions.
    """
    h, w = src.shape[:2]

    x0 = np.floor(u).astype(np.int64)
    y0 = np.floor(v).astype(np.int64)
    x1 = x0 + 1
    y1 = y0 + 1

    fx = (u - x0)[..., None]
    fy = (v - y0)[..., None]

    x0 = np.mod(x0, w)
    x1 = np.mod(x1, w)
    y0 = np.clip(y0, 0, h - 1)
    y1 = np.clip(y1, 0, h - 1)

    c00 = src[y0, x0]
    c10 = src[y0, x1]
    c01 = src[y1, x0]
    c11 = src[y1, x1]

    top = c00 * (1.0 - fx) + c10 * fx
    bot = c01 * (1.0 - fx) + c11 * fx
    return top * (1.0 - fy) + bot * fy


def render_face(src, forward, right, down, res, rot=None):
    """Render a single face at res x res by sampling the equirect source.

    rot, if given, is a 3x3 matrix applied to each sample direction before it is
    projected into the panorama (used to tilt the whole cubemap).
    """
    h, w = src.shape[:2]

    # Pixel centers -> normalized [-1, 1]; +0.5 centers the sample in the texel.
    lin = (np.arange(res, dtype=np.float64) + 0.5) * (2.0 / res) - 1.0
    a, b = np.meshgrid(lin, lin)  # a: columns (x), b: rows (y, top->bottom)

    f = np.asarray(forward)
    r = np.asarray(right)
    d = np.asarray(down)
    dirs = f[None, None, :] + a[..., None] * r[None, None, :] + b[..., None] * d[None, None, :]

    if rot is not None:
        dirs = dirs @ np.asarray(rot).T

    norm = np.linalg.norm(dirs, axis=-1)
    dx = dirs[..., 0] / norm
    dy = dirs[..., 1] / norm
    dz = dirs[..., 2] / norm

    lon = np.arctan2(dx, dz)          # [-pi, pi]
    lat = np.arcsin(np.clip(dy, -1.0, 1.0))  # [-pi/2, pi/2]

    u = (lon / (2.0 * math.pi) + 0.5) * w - 0.5
    v = (0.5 - lat / math.pi) * h - 0.5

    return bilinear_wrap(src, u, v)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input", help="equirectangular source image (2:1)")
    ap.add_argument("out_dir", help="directory to write face PNGs into")
    ap.add_argument("--size", type=int, default=256, help="output face size (px), default 256")
    ap.add_argument("--supersample", type=int, default=6,
                    help="render at size*supersample then area-average down (default 6)")
    ap.add_argument("--brightness", type=float, default=1.0,
                    help="linear-light brightness multiplier; <1 darkens, >1 brightens (default 1.0)")
    ap.add_argument("--tilt", type=float, default=0.0,
                    help="tilt the cubemap about the horizontal X axis, 0..90 degrees (default 0)")
    ap.add_argument("--sharpen", type=float, default=0.0,
                    help="unsharp-mask amount applied after downscale; 0=off, ~0.5-1.5 crisper (default 0)")
    args = ap.parse_args()

    tilt = math.radians(max(0.0, min(90.0, args.tilt)))
    ct, st = math.cos(tilt), math.sin(tilt)
    rot = None if tilt == 0.0 else np.array([
        [1.0, 0.0, 0.0],
        [0.0, ct, -st],
        [0.0, st, ct],
    ])

    os.makedirs(args.out_dir, exist_ok=True)

    img = Image.open(args.input).convert("RGB")
    # Everything downstream runs in LINEAR light so sampling, area-averaging and
    # brightness all preserve the energy of sub-pixel stars.
    src = srgb_to_linear(np.asarray(img, dtype=np.float64) / 255.0)
    print(f"source: {img.width}x{img.height}  faces: {args.size}  "
          f"supersample: {args.supersample}x  brightness: {args.brightness}  "
          f"tilt: {args.tilt}  sharpen: {args.sharpen}")

    render_res = args.size * max(1, args.supersample)
    for name, forward, right, down in FACES:
        face = render_face(src, forward, right, down, render_res, rot)  # linear
        face = downscale_linear(face, args.size)                       # linear area-average
        face = sharpen_linear(face, args.sharpen)                      # linear unsharp mask
        face *= args.brightness                                        # linear gain
        out = np.clip(linear_to_srgb(face) * 255.0 + 0.5, 0, 255).astype(np.uint8)
        out_path = os.path.join(args.out_dir, f"{name}.png")
        Image.fromarray(out, "RGB").save(out_path)
        print(f"  wrote {out_path}")


if __name__ == "__main__":
    main()
