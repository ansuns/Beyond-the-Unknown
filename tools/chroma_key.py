"""Key a flat chroma background out of a generated PNG and emit a real RGBA sprite.

The image backend never returns an alpha channel: ``background="transparent"``
produces an RGB PNG with a painted checkerboard. Border flood-filling cannot
handle sprites whose silhouette encloses background (gaps between stone blocks,
holes in a banner), so opaque generations are requested on a flat key colour and
removed here by colour distance.

Usage:
    python tools/chroma_key.py <src.png> <dst.png> [--key 162,38,98] [--inner 30] [--outer 72]
"""

from __future__ import annotations

import argparse

from PIL import Image, ImageFilter


def _parse_key(value: str) -> tuple[int, int, int]:
    parts = [int(piece) for piece in value.split(",")]
    if len(parts) != 3:
        raise argparse.ArgumentTypeError("key must be r,g,b")
    return parts[0], parts[1], parts[2]


def key_image(
    source: Image.Image,
    key: tuple[int, int, int],
    inner: float,
    outer: float,
    despill: bool = True,
) -> Image.Image:
    rgb = source.convert("RGB")
    width, height = rgb.size
    pixels = rgb.load()
    alpha = Image.new("L", (width, height), 255)
    alpha_pixels = alpha.load()
    kr, kg, kb = key

    for y in range(height):
        for x in range(width):
            r, g, b = pixels[x, y]
            distance = max(abs(r - kr), abs(g - kg), abs(b - kb))
            if distance <= inner:
                alpha_pixels[x, y] = 0
            elif distance >= outer:
                alpha_pixels[x, y] = 255
            else:
                ratio = (distance - inner) / (outer - inner)
                alpha_pixels[x, y] = round(255 * ratio)

    # Erode one pixel so no key-coloured rim survives, then soften the new edge.
    alpha = alpha.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(0.6))

    out = rgb.convert("RGBA")
    out.putalpha(alpha)

    if despill:
        _despill(out, key, alpha)
    return out


def _despill(image: Image.Image, key: tuple[int, int, int], alpha: Image.Image) -> None:
    """Pull edge pixels away from the key hue so no magenta fringe remains."""
    pixels = image.load()
    alpha_pixels = alpha.load()
    width, height = image.size
    kr, kg, kb = key
    for y in range(height):
        for x in range(width):
            a = alpha_pixels[x, y]
            if a == 0 or a == 255:
                continue
            r, g, b, _ = pixels[x, y]
            # Keep the pixel's own hue but cap any channel driven towards the key.
            if kr > g and kb > g:  # magenta-like key: green is the neutral channel
                r = min(r, g + 24)
                b = min(b, g + 24)
            pixels[x, y] = (r, g, b, a)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source")
    parser.add_argument("destination")
    parser.add_argument("--key", type=_parse_key, default=(162, 38, 98))
    parser.add_argument("--inner", type=float, default=30)
    parser.add_argument("--outer", type=float, default=72)
    args = parser.parse_args()

    with Image.open(args.source) as image:
        result = key_image(image, args.key, args.inner, args.outer)
        result.save(args.destination, "PNG", optimize=True)
    print(f"wrote {args.destination} ({result.size[0]}x{result.size[1]}, {result.mode})")


if __name__ == "__main__":
    main()
