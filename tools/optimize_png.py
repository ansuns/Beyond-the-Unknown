"""Shrink delivered PNGs without changing how they look.

A WeChat mini game ships its first screen inside a 4 MB main package, and the
six vertical-slice sprites alone were 3.6 MB - most of it a 1.7 MB preview that
nobody sees at full size. Lossless PNG of soft-painted art is the wrong format
for that budget, but converting to JPEG would destroy the alpha channel the
sprites depend on.

So this quantises to a palette while keeping the alpha channel, which is where
most of the redundancy in flat-shaded cartoon art sits, and reports the colour
error it caused so a bad result is visible rather than assumed.

Usage:
    python tools/optimize_png.py <file.png> [--colors 192] [--max-size 512] [--dry-run]
    python tools/optimize_png.py --all-assets [--dry-run]
"""

from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[1]
ASSET_ROOT = REPO_ROOT / "client" / "assets" / "resources"

# Perceptual guard: a palette that shifts average colour by more than this is
# visible as banding on the soft gradients these backdrops rely on.
MAX_MEAN_ERROR = 3.0
# A single stray pixel is invisible; a systematically shifted image is not.
# So the guard uses the 99.5th percentile rather than the absolute maximum.
MAX_P995_ERROR = 28


def mean_and_p995_error(original: Image.Image, candidate: Image.Image) -> tuple[float, float]:
    left = original.convert("RGBA")
    right = candidate.convert("RGBA")
    if left.size != right.size:
        raise ValueError("images must be the same size to compare")
    total = 0
    errors: list[int] = []
    for (lr, lg, lb, _), (rr, rg, rb, _) in zip(
        left.get_flattened_data(), right.get_flattened_data()
    ):
        errors.append(max(abs(lr - rr), abs(lg - rg), abs(lb - rb)))
        total += abs(lr - rr) + abs(lg - rg) + abs(lb - rb)
    errors.sort()
    index = min(len(errors) - 1, int(len(errors) * 0.995))
    return total / (len(errors) * 3), float(errors[index])


def quantize(image: Image.Image, colors: int) -> Image.Image:
    """Palette-reduce while preserving alpha.

    ``quantize`` drops alpha, so the image is split first and the alpha band is
    reattached afterwards; that keeps soft sprite edges intact.
    """
    rgba = image.convert("RGBA")
    alpha = rgba.getchannel("A")
    reduced = rgba.convert("RGB").quantize(colors=colors, method=Image.Quantize.FASTOCTREE)
    result = reduced.convert("RGBA")
    result.putalpha(alpha)
    return result


def optimize(path: Path, colors: int, max_size: int | None, dry_run: bool) -> dict:
    original = Image.open(path)
    original.load()
    before = path.stat().st_size
    working = original

    resized = False
    if max_size is not None:
        width, height = working.size
        longest = max(width, height)
        if longest > max_size:
            scale = max_size / longest
            working = working.resize(
                (max(1, round(width * scale)), max(1, round(height * scale))),
                Image.Resampling.LANCZOS,
            )
            resized = True

    candidate = quantize(working, colors)
    mean_error, p995_error = mean_and_p995_error(working, candidate)
    buffer = io.BytesIO()
    candidate.save(buffer, format="PNG", optimize=True)
    after = buffer.tell()

    verdict = "ok"
    if mean_error > MAX_MEAN_ERROR or p995_error > MAX_P995_ERROR:
        verdict = "rejected-quality"
    if after >= before:
        verdict = "rejected-no-gain"

    if verdict == "ok" and not dry_run:
        path.write_bytes(buffer.getvalue())

    return {
        "file": str(path.relative_to(REPO_ROOT)).replace("\\", "/"),
        "before_bytes": before,
        "after_bytes": after,
        "saved_pct": round(100 * (1 - after / before), 1) if before else 0.0,
        "resized": resized,
        "size": candidate.size,
        "mean_error": round(mean_error, 2),
        "p995_error": p995_error,
        "verdict": verdict,
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="*", type=Path)
    parser.add_argument("--all-assets", action="store_true")
    parser.add_argument("--colors", type=int, default=192)
    parser.add_argument("--max-size", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    targets = list(args.files)
    if args.all_assets:
        targets.extend(sorted(ASSET_ROOT.rglob("*.png")))
    if not targets:
        parser.error("pass at least one file or --all-assets")

    failures = 0
    total_before = 0
    total_after = 0
    for path in targets:
        result = optimize(path, args.colors, args.max_size, args.dry_run)
        total_before += result["before_bytes"]
        total_after += result["after_bytes"]
        if result["verdict"] != "ok":
            failures += 1
        print(
            f"{result['verdict']:20s} {result['file']:70s} "
            f"{result['before_bytes'] // 1024:5d}K -> {result['after_bytes'] // 1024:5d}K "
            f"({result['saved_pct']:5.1f}%) err={result['mean_error']}/{result['p995_error']}"
        )
    print(
        f"total {total_before // 1024}K -> {total_after // 1024}K "
        f"({100 * (1 - total_after / total_before):.1f}% smaller), {failures} rejected"
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
