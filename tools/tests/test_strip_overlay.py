"""Regression tests for tools/strip_overlay.py.

The bug these tests exist for: the first version judged every mode by image
alpha, so a plain RGB image reported "100% opaque" and crop mode refused to run
without --force - while the documented command passes no --force. The guard now
checks what each mode actually needs.

The CLI test runs the exact command from tools/README.md, because the guard was
only ever exercised through a flag the documentation did not mention.
"""

from __future__ import annotations

import math
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

from strip_overlay import (  # noqa: E402
    MIN_CROP_FRAC,
    GuardError,
    alpha_opaque_ratio,
    box_pixels,
    cut_pixels,
    process,
)


def make_rgb(width: int = 200, height: int = 150, color: tuple[int, int, int] = (40, 120, 200)) -> Image.Image:
    return Image.new("RGB", (width, height), color)


def make_rgba_empty_corner(width: int = 200, height: int = 150) -> Image.Image:
    """Artwork on the left, transparent corner - the shape of a real sprite."""
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    image.paste((90, 60, 40, 255), (10, 10, width // 2, height - 10))
    return image


def make_rgba_full_corner(width: int = 200, height: int = 150) -> Image.Image:
    """Artwork reaching into the bottom-right corner."""
    return Image.new("RGBA", (width, height), (90, 60, 40, 255))


class TestCropMode:
    def test_rgb_crop_without_force_succeeds(self) -> None:
        """P0-1 regression: an RGB image must not be blocked by an alpha check."""
        image = make_rgb()
        result, mode, note = process(image, mode="crop")
        assert mode == "crop"
        assert "crop_depth" in note
        # P0-2 regression: the trimmed rows must be at least the approved fraction,
        # not the truncation of it. 7% of 150 is 10.5, so 11 rows go, not 10.
        assert result.height == 150 - math.ceil(MIN_CROP_FRAC * 150)
        assert 1 - result.height / 150 >= MIN_CROP_FRAC

    def test_auto_mode_uses_crop_for_rgb(self) -> None:
        result, mode, _ = process(make_rgb(), mode="auto")
        assert mode == "crop"
        assert result.height < 150

    def test_crop_shallower_than_the_mark_is_rejected(self) -> None:
        with pytest.raises(GuardError, match="does not reach the mark"):
            process(make_rgb(), mode="crop", crop_bottom=MIN_CROP_FRAC / 2)

    def test_crop_deeper_than_a_quarter_is_rejected(self) -> None:
        with pytest.raises(GuardError, match="removes more than"):
            process(make_rgb(), mode="crop", crop_bottom=0.4)

    def test_crop_with_force_allows_a_deep_trim(self) -> None:
        result, _, _ = process(make_rgb(), mode="crop", crop_bottom=0.4, force=True)
        assert result.height == 150 - int(0.4 * 150)

    def test_crop_right_edge_also_satisfies_the_guard(self) -> None:
        result, _, _ = process(make_rgb(), mode="crop", crop_bottom=0.0, crop_right=MIN_CROP_FRAC)
        assert result.width < 200

    def test_crop_without_any_depth_is_rejected(self) -> None:
        with pytest.raises(GuardError, match="positive"):
            process(make_rgb(), mode="crop", crop_bottom=0.0, crop_right=0.0)

    def test_negative_crop_is_rejected(self) -> None:
        with pytest.raises(GuardError, match="not be negative"):
            process(make_rgb(), mode="crop", crop_bottom=-0.1)


class TestAlphaMode:
    def test_alpha_clears_only_the_corner(self) -> None:
        image = make_rgba_empty_corner()
        result, mode, _ = process(image, mode="alpha")
        assert mode == "alpha"
        assert result.getpixel((195, 145))[3] == 0
        assert result.getpixel((20, 20))[3] == 255

    def test_alpha_refuses_when_the_corner_holds_artwork(self) -> None:
        with pytest.raises(GuardError, match="likely holds artwork"):
            process(make_rgba_full_corner(), mode="alpha")

    def test_alpha_force_allows_a_filled_corner(self) -> None:
        result, _, note = process(make_rgba_full_corner(), mode="alpha", force=True)
        assert result.getpixel((195, 145))[3] == 0
        assert "opaque_ratio" in note

    def test_alpha_mode_rejects_rgb_input(self) -> None:
        with pytest.raises(GuardError, match="needs an RGBA image"):
            process(make_rgb(), mode="alpha")

    def test_auto_mode_uses_alpha_for_rgba(self) -> None:
        _, mode, _ = process(make_rgba_empty_corner(), mode="auto")
        assert mode == "alpha"

    def test_fully_transparent_image_is_handled(self) -> None:
        image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        result, _, note = process(image, mode="alpha")
        assert alpha_opaque_ratio(image, box_pixels(image.size, (0.75, 0.9, 1.0, 1.0))) == 0.0
        assert result.getchannel("A").getextrema() == (0, 0)
        assert "opaque_ratio=0.00%" in note


class TestGeometryEdges:
    @pytest.mark.parametrize("size", [(16, 16), (17, 13), (31, 999), (999, 31)])
    def test_odd_sizes_do_not_crash(self, size: tuple[int, int]) -> None:
        result, mode, _ = process(Image.new("RGB", size, (10, 20, 30)), mode="crop")
        assert mode == "crop"
        assert result.width >= 1 and result.height >= 1

    def test_box_pixels_clamps_to_the_image(self) -> None:
        rect = box_pixels((10, 10), (0.9, 0.9, 1.5, 1.5))
        assert rect[2] <= 10 and rect[3] <= 10
        assert rect[0] < rect[2] and rect[1] < rect[3]

    def test_tiny_image_is_refused_by_inpaint_guard(self) -> None:
        with pytest.raises(GuardError, match="too small"):
            process(Image.new("RGB", (8, 8), (0, 0, 0)), mode="inpaint")


class TestCropRounding:
    """The trim must never come out shallower than the fraction it was approved at.

    ``int(0.07 * 150)`` is 10, i.e. 6.67% - less than the 7% the guard demanded.
    On a 14px-tall frame it is 0, so the command reported success and removed
    nothing. Both cases are real, both are covered here.
    """

    @pytest.mark.parametrize("height", [14, 15, 20, 150, 400, 1024, 1536])
    def test_rgb_trim_reaches_the_approved_fraction(self, height: int) -> None:
        result, _, _ = process(Image.new("RGB", (300, height), (5, 5, 5)), mode="crop")
        removed = height - result.height
        assert removed >= cut_pixels((300, height), MIN_CROP_FRAC, 0.0)[1]
        assert removed / height >= MIN_CROP_FRAC

    @pytest.mark.parametrize("height", [14, 15, 150, 1024])
    def test_rgba_trim_reaches_the_approved_fraction(self, height: int) -> None:
        image = Image.new("RGBA", (300, height), (5, 5, 5, 255))
        result, _, _ = process(image, mode="crop")
        removed = height - result.height
        assert removed / height >= MIN_CROP_FRAC

    def test_rgba_and_rgb_crop_identically(self) -> None:
        rgb, _, _ = process(Image.new("RGB", (300, 400), (1, 2, 3)), mode="crop")
        rgba, _, _ = process(Image.new("RGBA", (300, 400), (1, 2, 3, 255)), mode="crop")
        assert rgb.size == rgba.size

    def test_cut_pixels_rounds_up(self) -> None:
        assert cut_pixels((300, 150), MIN_CROP_FRAC, 0.0) == (0, 11)
        assert cut_pixels((300, 14), MIN_CROP_FRAC, 0.0) == (0, 1)
        assert cut_pixels((300, 100), 0.0, 0.0) == (0, 0)

    def test_bottom_and_right_are_both_applied(self) -> None:
        result, _, note = process(
            Image.new("RGB", (400, 400), (9, 9, 9)), mode="crop", crop_bottom=0.1, crop_right=0.1
        )
        assert result.size == (400 - 40, 400 - 40)
        assert "cut=40x40px" in note

    def test_crop_that_would_empty_the_frame_is_refused(self) -> None:
        with pytest.raises(GuardError, match="empty image"):
            process(Image.new("RGB", (40, 40), (0, 0, 0)), mode="crop", crop_bottom=1.0, force=True)

    def test_crop_is_still_applied_when_a_frame_is_too_thin(self) -> None:
        """A 1px frame cannot lose 7% of itself; the guard must say so."""
        with pytest.raises(GuardError, match="empty image"):
            process(Image.new("RGB", (40, 1), (0, 0, 0)), mode="crop")

    def test_degenerate_crop_of_a_zero_height_image_is_refused(self) -> None:
        with pytest.raises(GuardError):
            process(Image.new("RGB", (16, 0), (0, 0, 0)), mode="crop")


class TestBadInput:
    def test_unknown_mode_is_rejected(self) -> None:
        with pytest.raises(GuardError, match="unknown mode"):
            process(Image.new("RGB", (64, 64), (0, 0, 0)), mode="blur")

    def test_empty_image_passes_geometry_without_crashing(self) -> None:
        empty = Image.new("RGBA", (0, 0))
        with pytest.raises(GuardError, match="nothing to process"):
            process(empty, mode="alpha")

    def test_corrupt_file_exits_non_zero(self, tmp_path: Path) -> None:
        broken = tmp_path / "broken.png"
        broken.write_bytes(b"\x89PNG\r\n\x1a\nnot-really-a-png")
        completed = subprocess.run(
            [sys.executable, str(TOOLS / "strip_overlay.py"), str(broken), str(tmp_path / "o.png"), "--mode", "crop"],
            capture_output=True,
            text=True,
        )
        assert completed.returncode != 0
        assert not (tmp_path / "o.png").exists()

    def test_missing_file_exits_non_zero(self, tmp_path: Path) -> None:
        completed = subprocess.run(
            [sys.executable, str(TOOLS / "strip_overlay.py"), str(tmp_path / "nope.png"), str(tmp_path / "o.png")],
            capture_output=True,
            text=True,
        )
        assert completed.returncode != 0


class TestDocumentedCommand:
    def test_readme_crop_command_runs_without_force(self, tmp_path: Path) -> None:
        """The command printed in tools/README.md must work as written."""
        source = tmp_path / "raw.png"
        target = tmp_path / "final.png"
        make_rgb(300, 400).save(source)

        completed = subprocess.run(
            [sys.executable, str(TOOLS / "strip_overlay.py"), str(source), str(target), "--mode", "crop"],
            capture_output=True,
            text=True,
        )
        assert completed.returncode == 0, completed.stderr
        assert target.exists()
        with Image.open(target) as produced:
            assert produced.height == 400 - int(MIN_CROP_FRAC * 400)

    def test_readme_alpha_command_runs_on_a_sprite(self, tmp_path: Path) -> None:
        source = tmp_path / "keyed.png"
        target = tmp_path / "final.png"
        make_rgba_empty_corner(300, 400).save(source)

        completed = subprocess.run(
            [sys.executable, str(TOOLS / "strip_overlay.py"), str(source), str(target), "--mode", "alpha"],
            capture_output=True,
            text=True,
        )
        assert completed.returncode == 0, completed.stderr
        with Image.open(target) as produced:
            assert produced.mode == "RGBA"
            assert produced.size == (300, 400)

    def test_a_refused_run_exits_non_zero(self, tmp_path: Path) -> None:
        source = tmp_path / "raw.png"
        target = tmp_path / "final.png"
        make_rgb(300, 400).save(source)

        completed = subprocess.run(
            [
                sys.executable,
                str(TOOLS / "strip_overlay.py"),
                str(source),
                str(target),
                "--mode",
                "crop",
                "--crop-bottom",
                "0.01",
            ],
            capture_output=True,
            text=True,
        )
        assert completed.returncode != 0
        assert "does not reach the mark" in completed.stderr
        assert not target.exists()
