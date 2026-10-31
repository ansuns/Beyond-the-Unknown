"""Convert a flattened checkerboard "fake transparency" PNG into a real RGBA sprite.

The image backend returns RGB PNGs with a painted checkerboard instead of an
alpha channel. This tool removes the checkerboard by flood-filling inward from
the image border, so enclosed light regions that belong to the artwork (white
cloth, eyes) survive.

Usage:
    python tools/matte_sprite.py <src.png> <dst.png> [--tolerance 46] [--feather 1]
"""

from __future__ import annotations

import argparse
from collections import deque

from PIL import Image, ImageFilter


def _is_background(pixel: tuple[int, int, int], tolerance: int) -> bool:
    r, g, b = pixel
    return (
        min(r, g, b) > 200
        and max(r, g, b) - min(r, g, b) <= 12
        and 255 - min(r, g, b) <= tolerance
    )


def matte(source: Image.Image, tolerance: int, feather: int) -> Image.Image:
    rgba = source.convert("RGB")
    width, height = rgba.size
    src = rgba.load()

    background = bytearray(width * height)
    queue: deque[tuple[int, int]] = deque()

    def push(x: int, y: int) -> None:
        index = y * width + x
        if background[index]:
            return
        if not _is_background(src[x, y], tolerance):
            return
        background[index] = 1
        queue.append((x, y))

    for x in range(width):
        push(x, 0)
        push(x, height - 1)
    for y in range(height):
        push(0, y)
        push(width - 1, y)

    while queue:
        x, y = queue.popleft()
        if x > 0:
            push(x - 1, y)
        if x + 1 < width:
            push(x + 1, y)
        if y > 0:
            push(x, y - 1)
        if y + 1 < height:
            push(x, y + 1)

    mask = Image.frombytes("L", (width, height), bytes(0 if v else 255 for v in background))
    if feather > 0:
        # Erode then soften so the hard checkerboard edge does not leave a light fringe.
        mask = mask.filter(ImageFilter.MinFilter(feather * 2 + 1))
        mask = mask.filter(ImageFilter.GaussianBlur(0.8))

    out = rgba.convert("RGBA")
    out.putalpha(mask)
    return _decontaminate(out)


def _decontaminate(image: Image.Image) -> Image.Image:
    """Remove the light background colour that bleeds into soft edge pixels.

    The checkerboard is much lighter than the artwork, so partially transparent
    edge pixels are biased towards white. Solving colour = alpha * fg + (1 - alpha) * bg
    for fg restores the true edge colour and removes the white rim.
    """
    width, height = image.size
    pixels = image.load()
    background = 240.0
    for y in range(height):
        for x in range(width):
            r, g, b, a = pixels[x, y]
            if a == 0 or a == 255:
                continue
            alpha = a / 255.0
            pixels[x, y] = (
                _unpremultiply(r, alpha, background),
                _unpremultiply(g, alpha, background),
                _unpremultiply(b, alpha, background),
                a,
            )
    return image


def _unpremultiply(channel: int, alpha: float, background: float) -> int:
    value = (channel - (1.0 - alpha) * background) / max(alpha, 0.05)
    return max(0, min(255, round(value)))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source")
    parser.add_argument("destination")
    parser.add_argument("--tolerance", type=int, default=46)
    parser.add_argument("--feather", type=int, default=1)
    args = parser.parse_args()

    with Image.open(args.source) as image:
        result = matte(image, args.tolerance, args.feather)
        result.save(args.destination, "PNG", optimize=True)
    print(f"wrote {args.destination} ({result.size[0]}x{result.size[1]}, {result.mode})")


if __name__ == "__main__":
    main()
