"""Remove the provider's fixed corner overlay from generated images.

The image backend stamps an "AI generated" mark into the bottom-right corner of
every output. Asking the service for an unmarked image (Hunyuan `LogoAdd=0`) is
the preferred fix, but the generation tool used here does not expose that
switch, so this is the local fallback.

Three modes, each with its own guard - they fail differently, so one shared
check cannot serve all of them:

* ``alpha``   - RGBA sprites. The mark sits outside the artwork, so clearing
                alpha in the corner discards only the mark. Guard: refuse when
                the corner is mostly opaque, because then it holds artwork.
* ``crop``    - any mode, for opaque backgrounds where the mark is painted over
                scenery. Guard: refuse when the trim is too shallow to cover the
                mark, or so deep it eats a quarter of the image.
* ``inpaint`` - last resort. Requires OpenCV. Large glyph strokes over
                structured art come out melted; treat the result as a
                placeholder, not production art.

Removing the overlay does not change what the asset is. Generated material still
has to be recorded as generated content with review, and provider terms plus any
applicable AI-content labelling rules still have to be confirmed separately.

Usage:
    python tools/strip_overlay.py src.png dst.png [--mode alpha|crop|inpaint|auto]
        [--box 0.75,0.90,1.0,1.0] [--crop-bottom 0.072] [--crop-right 0.0]
        [--force]
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

from PIL import Image

DEFAULT_BOX = (0.75, 0.90, 1.0, 1.0)
# The mark occupies roughly the bottom 7% of the frame; a shallower crop leaves
# part of it behind, which is exactly the failure this mode must prevent.
MARK_TOP_FRAC = 0.93
MIN_CROP_FRAC = round(1.0 - MARK_TOP_FRAC, 3)
MAX_CROP_FRAC = 0.25
# The glyphs alone cover ~7% of the corner box, so the alpha guard only trips
# when the region is mostly filled - that means artwork, not an overlay.
ALPHA_ARTWORK_RATIO = 0.35
MIN_SIDE = 16


class GuardError(Exception):
    """Raised when a guard refuses to modify the image."""


def _parse_box(value: str) -> tuple[float, float, float, float]:
    parts = [float(piece) for piece in value.split(",")]
    if len(parts) != 4 or not all(0.0 <= part <= 1.0 for part in parts):
        raise argparse.ArgumentTypeError("box must be four fractions between 0 and 1")
    left, top, right, bottom = parts
    if not (left < right and top < bottom):
        raise argparse.ArgumentTypeError("box must satisfy left<right and top<bottom")
    return left, top, right, bottom


def box_pixels(
    size: tuple[int, int], box: tuple[float, float, float, float]
) -> tuple[int, int, int, int]:
    width, height = size
    left = min(int(box[0] * width), max(width - 1, 0))
    top = min(int(box[1] * height), max(height - 1, 0))
    right = min(max(int(box[2] * width), left + 1), width)
    bottom = min(max(int(box[3] * height), top + 1), height)
    return left, top, right, bottom


def alpha_opaque_ratio(image: Image.Image, rect: tuple[int, int, int, int]) -> float:
    """Share of pixels in ``rect`` that are opaque enough to be artwork."""
    if image.mode != "RGBA":
        raise GuardError(f"alpha ratio needs an RGBA image, got {image.mode}")
    region = image.crop(rect).getchannel("A")
    total = (rect[2] - rect[0]) * (rect[3] - rect[1])
    if total <= 0:
        return 0.0
    return sum(region.histogram()[200:]) / total


def check_alpha(image: Image.Image, rect: tuple[int, int, int, int], force: bool) -> str:
    ratio = alpha_opaque_ratio(image, rect)
    if ratio > ALPHA_ARTWORK_RATIO and not force:
        raise GuardError(
            f"alpha box {rect} is {ratio:.1%} opaque, so it likely holds artwork "
            "rather than only the mark. Inspect the corner, then re-run with --force."
        )
    return f"opaque_ratio={ratio:.2%}"


def check_crop(
    size: tuple[int, int], crop_bottom: float, crop_right: float, force: bool
) -> str:
    if crop_bottom < 0 or crop_right < 0:
        raise GuardError("crop fractions must not be negative")
    depth = max(crop_bottom, crop_right)
    if depth <= 0:
        raise GuardError("crop mode needs a positive --crop-bottom or --crop-right")
    if depth < MIN_CROP_FRAC and not force:
        raise GuardError(
            f"cropping {depth:.3%} does not reach the mark (needs at least "
            f"{MIN_CROP_FRAC:.1%}); part of the overlay would survive."
        )
    if depth > MAX_CROP_FRAC and not force:
        raise GuardError(
            f"cropping {depth:.1%} removes more than {MAX_CROP_FRAC:.0%} of the image; "
            "confirm with --force if that is intended."
        )

    # Rounding must not be allowed to quietly satisfy the fractional guard while
    # removing nothing: a 14px-tall frame at 7% truncates to 0 rows.
    width, height = size
    cut_right, cut_bottom = cut_pixels(size, crop_bottom, crop_right)
    if cut_bottom >= height or cut_right >= width:
        raise GuardError(
            f"cropping {cut_bottom} row(s) of {height} and {cut_right} column(s) of "
            f"{width} would leave an empty image."
        )
    if crop_bottom > 0 and cut_bottom < 1:
        raise GuardError(
            f"image is {height}px tall, so a {crop_bottom:.1%} trim rounds to zero "
            "rows and the mark survives."
        )
    if crop_right > 0 and cut_right < 1:
        raise GuardError(
            f"image is {width}px wide, so a {crop_right:.1%} trim rounds to zero "
            "columns and the mark survives."
        )
    return f"crop_depth={depth:.3%} cut={cut_right}x{cut_bottom}px"


def check_inpaint(image: Image.Image, rect: tuple[int, int, int, int], force: bool) -> str:
    width, height = image.size
    if min(width, height) < MIN_SIDE:
        raise GuardError(f"image is {width}x{height}, too small to reconstruct a corner")
    if (rect[2] - rect[0]) <= 0 or (rect[3] - rect[1]) <= 0:
        raise GuardError("inpaint box is empty")
    return f"box={rect}"


def strip_alpha(image: Image.Image, rect: tuple[int, int, int, int]) -> Image.Image:
    out = image.convert("RGBA")
    out.paste((0, 0, 0, 0), rect)
    return out


def cut_pixels(
    size: tuple[int, int], crop_bottom: float, crop_right: float
) -> tuple[int, int]:
    """Pixels to drop on the right and bottom, rounded up.

    ``int()`` truncates, so the old code removed less than the fraction the guard
    had just approved - 7% of 150 rows is 10.5, and 10 rows is 6.67%. Rounding up
    keeps the real trim at or above the approved one.
    """
    width, height = size
    # 0.07 * 400 is 28.000000000000004 in binary floating point; rounding to nine
    # decimals first stops ceil() from adding a phantom row on exact fractions.
    cut_right = math.ceil(round(crop_right * width, 9)) if crop_right > 0 else 0
    cut_bottom = math.ceil(round(crop_bottom * height, 9)) if crop_bottom > 0 else 0
    return cut_right, cut_bottom


def strip_crop(image: Image.Image, crop_bottom: float, crop_right: float) -> Image.Image:
    width, height = image.size
    cut_right, cut_bottom = cut_pixels(image.size, crop_bottom, crop_right)
    keep_w = max(1, width - cut_right)
    keep_h = max(1, height - cut_bottom)
    return image.crop((0, 0, keep_w, keep_h))


def strip_inpaint(
    image: Image.Image, rect: tuple[int, int, int, int], mask_mode: str = "box"
) -> Image.Image:
    try:
        import cv2
        import numpy as np
    except ImportError as exc:  # pragma: no cover - depends on local environment
        raise GuardError(
            "inpaint mode needs opencv: pip install opencv-python-headless"
        ) from exc

    array = np.array(image.convert("RGB"))
    mask = np.zeros(array.shape[:2], dtype=np.uint8)
    left, top, right, bottom = rect
    if mask_mode == "box":
        mask[top:bottom, left:right] = 255
        radius = 7
    else:
        patch = array[top:bottom, left:right]
        pale = (patch.min(axis=2) > 150) & (patch.max(axis=2) - patch.min(axis=2) < 40)
        mask[top:bottom, left:right] = np.where(pale, 255, 0).astype(np.uint8)
        radius = 3
    return Image.fromarray(cv2.inpaint(array, mask, radius, cv2.INPAINT_TELEA))


def process(
    image: Image.Image,
    mode: str = "auto",
    box: tuple[float, float, float, float] = DEFAULT_BOX,
    crop_bottom: float = MIN_CROP_FRAC,
    crop_right: float = 0.0,
    mask_mode: str = "box",
    force: bool = False,
) -> tuple[Image.Image, str, str]:
    """Return (image, mode_used, guard_note). Raises ``GuardError`` when refused."""
    width, height = image.size
    if width < 1 or height < 1:
        raise GuardError(f"image is {width}x{height}; there is nothing to process")
    if mode == "auto":
        mode = "alpha" if image.mode == "RGBA" else "crop"
    if mode == "alpha" and image.mode != "RGBA":
        raise GuardError(f"alpha mode needs an RGBA image, got {image.mode}")

    rect = box_pixels(image.size, box)
    if mode == "alpha":
        return strip_alpha(image, rect), mode, check_alpha(image, rect, force)
    if mode == "crop":
        note = check_crop(image.size, crop_bottom, crop_right, force)
        return strip_crop(image, crop_bottom, crop_right), mode, note
    if mode == "inpaint":
        return strip_inpaint(image, rect, mask_mode), mode, check_inpaint(image, rect, force)
    raise GuardError(f"unknown mode {mode}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source")
    parser.add_argument("destination")
    parser.add_argument("--mode", choices=["alpha", "crop", "inpaint", "auto"], default="auto")
    parser.add_argument("--box", type=_parse_box, default=DEFAULT_BOX)
    parser.add_argument("--crop-bottom", type=float, default=MIN_CROP_FRAC)
    parser.add_argument("--crop-right", type=float, default=0.0)
    parser.add_argument("--mask", choices=["pale", "box"], default="box")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    with Image.open(args.source) as image:
        try:
            result, mode, note = process(
                image,
                args.mode,
                args.box,
                args.crop_bottom,
                args.crop_right,
                args.mask,
                args.force,
            )
        except GuardError as exc:
            raise SystemExit(str(exc)) from exc
        out = Path(args.destination)
        out.parent.mkdir(parents=True, exist_ok=True)
        result.save(out, "PNG", optimize=True)
    print(f"wrote {args.destination} (mode={mode} {note}, {result.size[0]}x{result.size[1]})")


if __name__ == "__main__":
    main()
