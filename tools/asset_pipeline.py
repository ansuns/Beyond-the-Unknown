"""Turn a raw generated image into a Cocos-importable PNG plus a check report.

The generation backend returns flat RGB images: no alpha, a magenta backdrop when
asked for one, and a baked corner watermark. Getting from that to a sprite the
engine can lay out needs a fixed chain, and every step has a way to fail quietly:

* keying    - the model does not hit the requested hex, so the key is measured
              from the border instead of assumed.
* trimming  - alpha bounding box, so the sprite has no invisible margin and the
              foot baseline is where the anchor maths expects it.
* scaling   - contained inside the target box, never upscaled past the source.
* checking  - transparent coverage, key-colour fringe, anchor offset and the
              final file hash. A report without these numbers is not evidence.

Two shapes of asset share the chain:

* ``sprite``     - characters, mechanisms, effects, UI elements. Keyed, trimmed,
                   padded, anchored on the foot line.
* ``background`` - maps and scene plates. Opaque, so the watermark is removed by
                   cropping the bottom edge before any resizing.

Usage:
    python tools/asset_pipeline.py sprite --src raw.png --dst out.png --report r.json
    python tools/asset_pipeline.py background --src raw.png --dst out.png --report r.json
    python tools/asset_pipeline.py check --src out.png
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageFilter

from chroma_key import key_image
from strip_overlay import MIN_CROP_FRAC, GuardError, cut_pixels, strip_crop

# Fraction of the frame the corner watermark occupies, measured on 1024x1024 and
# 1024x1536 outputs. Cropping starts here, never shallower.
DEFAULT_PADDING = 8
DEFAULT_INNER = 26.0
DEFAULT_OUTER = 68.0
# A key-coloured pixel this close to the silhouette edge means keying under-ran.
FRINGE_DISTANCE = 40
FRINGE_RATIO_LIMIT = 0.02


@dataclass
class CheckReport:
    """Everything a reviewer needs to decide whether the file is usable."""

    source: str
    output: str
    kind: str
    source_size: tuple[int, int]
    output_size: tuple[int, int]
    mode: str
    key_color: tuple[int, int, int] | None = None
    transparent_pixels: int = 0
    opaque_pixels: int = 0
    semi_pixels: int = 0
    alpha_coverage: float = 0.0
    fringe_ratio: float = 0.0
    bbox: tuple[int, int, int, int] | None = None
    anchor_offset_px: int | None = None
    cropped_bottom_px: int = 0
    bleed_pixels_removed: int = 0
    sha256: str = ""
    warnings: list[str] = field(default_factory=list)
    checks: dict[str, bool] = field(default_factory=dict)

    def to_dict(self) -> dict:
        data = {
            "source": self.source,
            "output": self.output,
            "kind": self.kind,
            "source_size": list(self.source_size),
            "output_size": list(self.output_size),
            "mode": self.mode,
            "key_color": list(self.key_color) if self.key_color else None,
            "transparent_pixels": self.transparent_pixels,
            "opaque_pixels": self.opaque_pixels,
            "semi_pixels": self.semi_pixels,
            "alpha_coverage": round(self.alpha_coverage, 6),
            "fringe_ratio": round(self.fringe_ratio, 6),
            "bbox": list(self.bbox) if self.bbox else None,
            "anchor_offset_px": self.anchor_offset_px,
            "cropped_bottom_px": self.cropped_bottom_px,
            "bleed_pixels_removed": self.bleed_pixels_removed,
            "sha256": self.sha256,
            "warnings": self.warnings,
            "checks": self.checks,
        }
        return data


def detect_key_color(image: Image.Image, samples: int = 64) -> tuple[int, int, int]:
    """Measure the backdrop from the frame border instead of trusting the prompt.

    Generators drift away from the requested hex - a #FF00FF request came back as
    (251, 48, 247). Reading the dominant border colour keeps the key honest.
    """
    rgb = image.convert("RGB")
    width, height = rgb.size
    if width < 3 or height < 3:
        raise GuardError(f"image is {width}x{height}; too small to sample a border")

    pixels: list[tuple[int, int, int]] = []
    step_x = max(1, width // samples)
    step_y = max(1, height // samples)
    for x in range(0, width, step_x):
        pixels.append(rgb.getpixel((x, 0)))
        pixels.append(rgb.getpixel((x, height - 1)))
    for y in range(0, height, step_y):
        pixels.append(rgb.getpixel((0, y)))
        pixels.append(rgb.getpixel((width - 1, y)))
    return Counter(pixels).most_common(1)[0][0]


def alpha_stats(image: Image.Image) -> tuple[int, int, int, float]:
    if image.mode != "RGBA":
        raise GuardError(f"alpha stats need RGBA, got {image.mode}")
    histogram = image.getchannel("A").histogram()
    transparent = histogram[0]
    opaque = histogram[255]
    total = image.size[0] * image.size[1]
    semi = total - transparent - opaque
    coverage = (total - transparent) / total if total else 0.0
    return transparent, opaque, semi, coverage


def alpha_bbox(image: Image.Image) -> tuple[int, int, int, int] | None:
    if image.mode != "RGBA":
        raise GuardError(f"alpha bbox needs RGBA, got {image.mode}")
    return image.getchannel("A").getbbox()


def fringe_ratio(image: Image.Image, key: tuple[int, int, int]) -> float:
    """Share of edge-adjacent pixels still sitting on the key colour.

    Keying leaves a rim when ``outer`` is too small. Measuring only the pixels
    next to transparency keeps artwork that happens to be magenta from counting.
    """
    alpha = image.getchannel("A")
    edge = alpha.filter(ImageFilter.MinFilter(3))
    edge_bytes = edge.tobytes()
    rgb_bytes = image.convert("RGB").tobytes()
    kr, kg, kb = key
    fringe = 0
    candidates = 0
    for index, value in enumerate(edge_bytes):
        if value == 255:
            continue
        candidates += 1
        offset = index * 3
        r = rgb_bytes[offset]
        g = rgb_bytes[offset + 1]
        b = rgb_bytes[offset + 2]
        if max(abs(r - kr), abs(g - kg), abs(b - kb)) <= FRINGE_DISTANCE:
            fringe += 1
    if candidates == 0:
        return 0.0
    return fringe / candidates


def pad_to_anchor(image: Image.Image, padding: int) -> tuple[Image.Image, int]:
    """Crop to the alpha box and sit the content on the bottom edge.

    A character sprite's origin is its feet. Padding goes left, right and above,
    but not below, so the baseline is the canvas bottom and the engine can anchor
    at bottom-centre without per-asset offsets.
    """
    box = alpha_bbox(image)
    if box is None:
        raise GuardError("image has no opaque pixels; nothing to anchor")
    cropped = image.crop(box)
    width, height = cropped.size
    canvas = Image.new("RGBA", (width + padding * 2, height + padding), (0, 0, 0, 0))
    canvas.paste(cropped, (padding, padding))
    anchor_offset = canvas.size[1] - (padding + height)
    return canvas, anchor_offset


def contain(image: Image.Image, max_size: int) -> Image.Image:
    """Scale down to fit a square box; never upscale, upscaling only blurs."""
    width, height = image.size
    longest = max(width, height)
    if longest <= max_size:
        return image
    scale = max_size / longest
    target = (max(1, round(width * scale)), max(1, round(height * scale)))
    return image.resize(target, Image.LANCZOS)


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def remove_key_bleed(
    image: Image.Image,
    key: tuple[int, int, int],
    threshold: int = 45,
    feather: int = 24,
) -> tuple[Image.Image, int]:
    """Drop pixels that are a blend of artwork and backdrop, not pure backdrop.

    Keying by RGB distance misses the soft gradient the generator paints where a
    glow meets the backdrop: those pixels came back as (157, 89, 145), which is
    102 away from the key and therefore kept, leaving a purple cap above the
    sprite. Hue identifies them where distance cannot - magenta keeps red and
    blue far above green whatever its lightness.
    """
    import numpy as np

    kr, kg, kb = key
    if not (kr > kg + 40 and kb > kg + 40):
        return image, 0  # the rule below only describes a magenta-family key

    array = np.array(image.convert("RGBA"), dtype=np.int16)
    red = array[:, :, 0]
    green = array[:, :, 1]
    blue = array[:, :, 2]
    alpha = array[:, :, 3]
    bleed = np.minimum(red, blue) - green

    hard = (bleed > threshold) & (alpha > 0)
    soft = (bleed > threshold - feather) & (bleed <= threshold) & (alpha > 0)

    array[:, :, 3] = np.where(hard, 0, alpha)
    if feather > 0:
        ramp = np.clip((threshold - bleed) / float(feather), 0.0, 1.0)
        scaled = (alpha * ramp).astype(np.int16)
        array[:, :, 3] = np.where(soft, scaled, array[:, :, 3])

    removed = int(hard.sum())
    return Image.fromarray(np.clip(array, 0, 255).astype(np.uint8), "RGBA"), removed


def bleed_pixel_count(image: Image.Image, key: tuple[int, int, int], threshold: int = 45) -> int:
    """Pixels still carrying a magenta-family tint after keying."""
    import numpy as np

    kr, kg, kb = key
    if not (kr > kg + 40 and kb > kg + 40):
        return 0
    array = np.array(image.convert("RGBA"), dtype=np.int16)
    bleed = np.minimum(array[:, :, 0], array[:, :, 2]) - array[:, :, 1]
    return int(((bleed > threshold) & (array[:, :, 3] > 40)).sum())


def build_sprite(
    source: Image.Image,
    key: tuple[int, int, int] | None = None,
    inner: float = DEFAULT_INNER,
    outer: float = DEFAULT_OUTER,
    padding: int = DEFAULT_PADDING,
    max_size: int | None = None,
    clear_corner: bool = True,
    bleed_removal: bool = True,
) -> tuple[Image.Image, dict]:
    """Key, trim, pad and optionally clear the watermark corner. Returns (image, note)."""
    measured = key or detect_key_color(source)
    keyed = key_image(source, measured, inner, outer)
    bled = 0
    if bleed_removal:
        keyed, bled = remove_key_bleed(keyed, measured)
    if clear_corner:
        # The watermark survives keying because it is pale grey, not magenta, but
        # it sits on the backdrop, so clearing the corner alpha removes only it.
        from strip_overlay import box_pixels

        left, top, right, bottom = box_pixels(keyed.size, (0.75, 0.90, 1.0, 1.0))
        keyed.paste((0, 0, 0, 0), (left, top, right, bottom))
    anchored, anchor_offset = pad_to_anchor(keyed, padding)
    if max_size:
        anchored = contain(anchored, max_size)
    return anchored, {
        "key": measured,
        "anchor_offset_px": anchor_offset,
        "cleared_corner": clear_corner,
        "bleed_pixels_removed": bled,
    }


def build_background(
    source: Image.Image,
    crop_bottom: float = MIN_CROP_FRAC,
    crop_right: float = 0.0,
    size: tuple[int, int] | None = None,
) -> tuple[Image.Image, dict]:
    """Crop the watermark off an opaque plate, then fit it to the requested size."""
    cut_right, cut_bottom = cut_pixels(source.size, crop_bottom, crop_right)
    if cut_bottom >= source.size[1] or cut_right >= source.size[0]:
        raise GuardError(
            f"cropping {cut_bottom} of {source.size[1]} rows would leave nothing"
        )
    plate = strip_crop(source, crop_bottom, crop_right)
    if size:
        if plate.size != size:
            plate = plate.resize(size, Image.LANCZOS)
    return plate, {"cropped_bottom_px": cut_bottom, "cropped_right_px": cut_right}


def verify(image: Image.Image, key: tuple[int, int, int] | None, anchor_offset: int | None) -> dict:
    """Run the numeric checks. Failing one does not raise; it is recorded."""
    checks: dict[str, bool] = {}
    warnings: list[str] = []
    if image.mode == "RGBA":
        transparent, opaque, semi, coverage = alpha_stats(image)
        checks["has_transparency"] = transparent > 0
        checks["has_content"] = opaque > 0
        ratio = fringe_ratio(image, key) if key else 0.0
        checks["no_key_fringe"] = ratio <= FRINGE_RATIO_LIMIT
        leftover = bleed_pixel_count(image, key) if key else 0
        checks["no_key_bleed"] = leftover <= max(16, opaque // 2000)
        if not checks["has_transparency"]:
            warnings.append("no transparent pixels: this is not a cut-out sprite")
        if not checks["has_content"]:
            warnings.append("no fully opaque pixels: the sprite is a ghost")
        if ratio > FRINGE_RATIO_LIMIT:
            warnings.append(f"key-coloured fringe covers {ratio:.2%} of the edge band")
        if not checks["no_key_bleed"]:
            warnings.append(f"{leftover} pixels still carry a key-coloured tint")
    else:
        transparent = opaque = semi = 0
        coverage = 1.0
        ratio = 0.0
        checks["has_content"] = True

    # Backgrounds have no baseline to anchor, so the check only applies to sprites.
    if anchor_offset is not None:
        checks["anchor_at_bottom"] = anchor_offset <= 2
        if anchor_offset > 2:
            warnings.append(f"content sits {anchor_offset}px above the canvas bottom")

    return {
        "checks": checks,
        "warnings": warnings,
        "transparent_pixels": transparent,
        "opaque_pixels": opaque,
        "semi_pixels": semi,
        "alpha_coverage": coverage,
        "fringe_ratio": ratio,
    }


def duplicate_index(root: Path) -> dict[str, list[str]]:
    """Map sha256 -> paths so a repeated generation cannot silently ship twice."""
    index: dict[str, list[str]] = {}
    for path in sorted(root.rglob("*.png")):
        index.setdefault(sha256_of(path), []).append(str(path))
    return index


def _parse_size(value: str) -> tuple[int, int]:
    parts = value.lower().split("x")
    if len(parts) != 2 or not all(part.isdigit() for part in parts):
        raise argparse.ArgumentTypeError("size must look like 512x512")
    return int(parts[0]), int(parts[1])


def _load(path: str) -> Image.Image:
    with Image.open(path) as handle:
        return handle.convert("RGBA") if handle.mode in ("RGBA", "LA", "P") else handle.convert("RGB")


def run(kind: str, src: str, dst: str, report_path: str | None, args: argparse.Namespace) -> CheckReport:
    source = _load(src)
    if kind == "sprite":
        key = None
        if args.key and args.key != "auto":
            parts = [int(piece) for piece in args.key.split(",")]
            if len(parts) != 3:
                raise GuardError("--key must be auto or r,g,b")
            key = (parts[0], parts[1], parts[2])
        result, note = build_sprite(
            source,
            key=key,
            inner=args.inner,
            outer=args.outer,
            padding=args.padding,
            max_size=args.max_size,
            clear_corner=not args.keep_corner,
            bleed_removal=not args.keep_bleed,
        )
        keyed_with = note["key"]
    else:
        result, note = build_background(
            source,
            crop_bottom=args.crop_bottom,
            crop_right=args.crop_right,
            size=args.resize,
        )
        keyed_with = None

    target = Path(dst)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.suffix.lower() in (".jpg", ".jpeg"):
        result.convert("RGB").save(target, "JPEG", quality=92, optimize=True)
    else:
        result.save(target, "PNG", optimize=True)

    verification = verify(result, keyed_with, note.get("anchor_offset_px"))
    report = CheckReport(
        source=src,
        output=dst,
        kind=kind,
        source_size=source.size,
        output_size=result.size,
        mode="sprite" if kind == "sprite" else "background",
        key_color=keyed_with,
        bbox=alpha_bbox(result) if result.mode == "RGBA" else None,
        anchor_offset_px=note.get("anchor_offset_px"),
        cropped_bottom_px=note.get("cropped_bottom_px", 0),
        bleed_pixels_removed=note.get("bleed_pixels_removed", 0),
        sha256=sha256_of(target),
        **verification,
    )
    if report_path:
        out = Path(report_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a Cocos-ready asset from a raw generation")
    sub = parser.add_subparsers(dest="command", required=True)

    def common(target: argparse.ArgumentParser) -> None:
        target.add_argument("--src", required=True)
        target.add_argument("--dst", required=True)
        target.add_argument("--report")

    sprite = sub.add_parser("sprite")
    common(sprite)
    sprite.add_argument("--key", default="auto", help="auto, or r,g,b")
    sprite.add_argument("--inner", type=float, default=DEFAULT_INNER)
    sprite.add_argument("--outer", type=float, default=DEFAULT_OUTER)
    sprite.add_argument("--padding", type=int, default=DEFAULT_PADDING)
    sprite.add_argument("--max-size", type=int, default=0)
    sprite.add_argument("--keep-corner", action="store_true", help="do not clear the watermark corner")
    sprite.add_argument("--keep-bleed", action="store_true", help="keep backdrop-tinted edge pixels")

    background = sub.add_parser("background")
    common(background)
    background.add_argument("--crop-bottom", type=float, default=MIN_CROP_FRAC)
    background.add_argument("--crop-right", type=float, default=0.0)
    background.add_argument("--resize", type=_parse_size, default=None)

    check = sub.add_parser("check")
    check.add_argument("--src", required=True)

    args = parser.parse_args()
    try:
        if args.command == "check":
            image = _load(args.src)
            verification = verify(image, None, None)
            print(json.dumps({
                "src": args.src,
                "size": list(image.size),
                "mode": image.mode,
                "sha256": sha256_of(Path(args.src)),
                **verification,
            }, indent=2, ensure_ascii=False))
            return
        report = run(args.command, args.src, args.dst, args.report, args)
        print(
            f"{args.dst}: {report.output_size[0]}x{report.output_size[1]} "
            f"coverage={report.alpha_coverage:.1%} fringe={report.fringe_ratio:.3%} "
            f"anchor_offset={report.anchor_offset_px}"
        )
        for name, passed in report.checks.items():
            print(f"  {'PASS' if passed else 'FAIL'} {name}")
        for warning in report.warnings:
            print(f"  WARN {warning}")
        if not all(report.checks.values()):
            raise SystemExit(1)
    except GuardError as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
