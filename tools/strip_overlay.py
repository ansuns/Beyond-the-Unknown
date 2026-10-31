"""Remove the provider's fixed corner overlay from generated images.

The image backend stamps an "AI generated" mark into the bottom-right corner of
every output. Requesting the image without it (Hunyuan `LogoAdd=0`) is the
preferred fix, but the generation tool used here does not expose that switch, so
this is the local fallback.

Two modes:

* ``alpha``   - for RGBA sprites. The mark sits outside the artwork, so clearing
                alpha in the corner discards only the mark. No pixel is invented.
* ``crop``    - for opaque art. Trim the band that carries the mark. Lossless:
                no pixel is invented, but the canvas shrinks.
* ``inpaint`` - last resort for opaque art when the canvas size must not change.
                Requires OpenCV. Large glyph strokes over structured art come out
                melted, so treat the result as a placeholder, not production art.

The mark is a fixed overlay, so the region is fixed too. Before touching
anything the tool reports how much opaque content the region holds; if the
artwork actually reaches into the corner the command refuses unless ``--force``
is given, because then the "overlay" is partly artwork.

Provenance is not handled by pixels. Assets produced this way must still be
recorded as generated content with review, which is what
docs/engineering/assets/asset-generation-backend-findings.md requires.

Usage:
    python tools/strip_overlay.py src.png dst.png [--mode alpha|inpaint]
        [--box 0.75,0.90,1.0,1.0] [--force]
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image

DEFAULT_BOX = (0.75, 0.90, 1.0, 1.0)
OPAQUE_ALERT_RATIO = 0.02


def _parse_box(value: str) -> tuple[float, float, float, float]:
    parts = [float(piece) for piece in value.split(",")]
    if len(parts) != 4 or not all(0.0 <= part <= 1.0 for part in parts):
        raise argparse.ArgumentTypeError("box must be four fractions between 0 and 1")
    return parts[0], parts[1], parts[2], parts[3]


def _box_pixels(size: tuple[int, int], box: tuple[float, float, float, float]) -> tuple[int, int, int, int]:
    width, height = size
    left = int(box[0] * width)
    top = int(box[1] * height)
    right = int(box[2] * width)
    bottom = int(box[3] * height)
    return left, top, right, bottom


def _opaque_ratio(image: Image.Image, rect: tuple[int, int, int, int]) -> float:
    region = image.crop(rect)
    if region.mode != "RGBA":
        return 1.0
    alpha = region.getchannel("A")
    total = region.size[0] * region.size[1]
    if total == 0:
        return 0.0
    opaque = sum(alpha.histogram()[200:])
    return opaque / total


def strip_alpha(image: Image.Image, rect: tuple[int, int, int, int]) -> Image.Image:
    out = image.convert("RGBA")
    left, top, right, bottom = rect
    transparent = Image.new("L", (right - left, bottom - top), 0)
    out.paste((0, 0, 0, 0), rect)
    out.putalpha(out.getchannel("A"))
    del transparent
    return out


def strip_inpaint(
    image: Image.Image, rect: tuple[int, int, int, int], mask_mode: str = "pale"
) -> Image.Image:
    try:
        import cv2
        import numpy as np
    except ImportError as exc:  # pragma: no cover - depends on local environment
        raise SystemExit(
            "inpaint mode needs opencv: pip install opencv-python-headless"
        ) from exc

    rgb = image.convert("RGB")
    array = np.array(rgb)
    mask = np.zeros(array.shape[:2], dtype=np.uint8)
    left, top, right, bottom = rect
    if mask_mode == "box":
        # Reconstruct the whole corner: large glyph strokes leave readable ghosts
        # when only their pale pixels are masked.
        mask[top:bottom, left:right] = 255
        radius = 7
    else:
        patch = array[top:bottom, left:right]
        pale = (patch.min(axis=2) > 150) & (patch.max(axis=2) - patch.min(axis=2) < 40)
        mask[top:bottom, left:right] = np.where(pale, 255, 0).astype(np.uint8)
        radius = 3
    repaired = cv2.inpaint(array, mask, radius, cv2.INPAINT_TELEA)
    return Image.fromarray(repaired)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source")
    parser.add_argument("destination")
    parser.add_argument("--mode", choices=["alpha", "crop", "inpaint", "auto"], default="auto")
    parser.add_argument("--crop-bottom", type=float, default=0.072)
    parser.add_argument("--crop-right", type=float, default=0.0)
    parser.add_argument("--box", type=_parse_box, default=DEFAULT_BOX)
    parser.add_argument("--mask", choices=["pale", "box"], default="box")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    with Image.open(args.source) as image:
        rect = _box_pixels(image.size, args.box)
        ratio = _opaque_ratio(image, rect)
        mode = args.mode
        if mode == "auto":
            mode = "alpha" if image.mode == "RGBA" else "inpaint"
        if mode == "alpha" and image.mode != "RGBA":
            raise SystemExit(f"alpha mode needs an RGBA image, got {image.mode}")
        if ratio > OPAQUE_ALERT_RATIO and not args.force:
            raise SystemExit(
                f"overlay box {rect} is {ratio:.1%} opaque; artwork may reach into the "
                "corner. Inspect the image, then re-run with --force if the mark really "
                "belongs there."
            )
        if mode == "alpha":
            result = strip_alpha(image, rect)
        elif mode == "crop":
            width, height = image.size
            keep_w = width - int(args.crop_right * width)
            keep_h = height - int(args.crop_bottom * height)
            result = image.crop((0, 0, keep_w, keep_h))
        else:
            result = strip_inpaint(image, rect, args.mask)
        Path(args.destination).parent.mkdir(parents=True, exist_ok=True)
        result.save(args.destination, "PNG", optimize=True)
    print(f"wrote {args.destination} (mode={mode}, box={rect}, opaque_ratio={ratio:.2%})")


if __name__ == "__main__":
    main()
