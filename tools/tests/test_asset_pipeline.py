"""Tests for tools/asset_pipeline.py.

The chain has four ways to produce a file that looks fine in a thumbnail and is
wrong in the engine: a key measured from the wrong place, a sprite trimmed so the
foot line floats, an upscale that softens a 1024px render, and a magenta rim that
only shows on a dark background. Each gets a test.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from PIL import Image

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

from asset_pipeline import (  # noqa: E402
    alpha_bbox,
    alpha_stats,
    bleed_pixel_count,
    build_background,
    build_sprite,
    contain,
    detect_key_color,
    duplicate_index,
    pad_to_anchor,
    remove_key_bleed,
    verify,
)
from strip_overlay import GuardError  # noqa: E402

MAGENTA = (251, 48, 247)


def magenta_plate(width: int = 320, height: int = 320) -> Image.Image:
    return Image.new("RGB", (width, height), MAGENTA)


def plate_with_shape(width: int = 320, height: int = 320) -> Image.Image:
    """A magenta plate with an opaque blob whose bottom touches y=280."""
    board = magenta_plate(width, height)
    board.paste((60, 120, 90), (120, 80, 200, 280))
    return board


class TestKeyDetection:
    def test_measures_the_border_not_the_prompt(self) -> None:
        """The backend returns (251,48,247) when asked for #FF00FF; the tool must follow it."""
        assert detect_key_color(magenta_plate()) == MAGENTA

    def test_ignores_artwork_in_the_middle(self) -> None:
        assert detect_key_color(plate_with_shape()) == MAGENTA

    def test_refuses_a_frame_too_small_to_sample(self) -> None:
        with pytest.raises(GuardError, match="too small"):
            detect_key_color(Image.new("RGB", (2, 2), MAGENTA))


class TestAlphaMaths:
    def test_counts_transparent_and_opaque_separately(self) -> None:
        image = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
        image.paste((1, 2, 3, 255), (0, 0, 5, 10))
        transparent, opaque, semi, coverage = alpha_stats(image)
        assert (transparent, opaque, semi) == (50, 50, 0)
        assert coverage == pytest.approx(0.5)

    def test_bbox_tracks_the_artwork(self) -> None:
        image = Image.new("RGBA", (20, 20), (0, 0, 0, 0))
        image.paste((9, 9, 9, 255), (4, 6, 12, 14))
        assert alpha_bbox(image) == (4, 6, 12, 14)

    def test_alpha_stats_reject_rgb(self) -> None:
        with pytest.raises(GuardError, match="RGBA"):
            alpha_stats(Image.new("RGB", (4, 4), (0, 0, 0)))


class TestAnchor:
    def test_content_sits_on_the_canvas_bottom(self) -> None:
        image = Image.new("RGBA", (40, 40), (0, 0, 0, 0))
        image.paste((5, 5, 5, 255), (10, 5, 20, 30))
        anchored, offset = pad_to_anchor(image, padding=6)
        assert offset == 0
        assert anchored.size == (10 + 12, 25 + 6)
        assert anchored.getpixel((6, anchored.size[1] - 1))[3] == 255

    def test_empty_image_cannot_be_anchored(self) -> None:
        with pytest.raises(GuardError, match="no opaque pixels"):
            pad_to_anchor(Image.new("RGBA", (8, 8), (0, 0, 0, 0)), padding=2)


class TestScaling:
    def test_downscales_the_long_edge(self) -> None:
        assert contain(Image.new("RGBA", (400, 200)), 100).size == (100, 50)

    def test_never_upscales(self) -> None:
        source = Image.new("RGBA", (64, 32))
        assert contain(source, 512).size == (64, 32)

    def test_keeps_aspect_ratio(self) -> None:
        scaled = contain(Image.new("RGBA", (300, 100)), 150)
        assert scaled.size == (150, 50)


class TestBleed:
    def test_removes_magenta_family_pixels(self) -> None:
        """(157,89,145) is 102 away from the key, so distance keying keeps it."""
        image = Image.new("RGBA", (4, 4), (157, 89, 145, 255))
        cleaned, removed = remove_key_bleed(image, MAGENTA)
        assert removed == 16
        assert cleaned.getchannel("A").getextrema() == (0, 0)

    def test_keeps_artwork_green_and_brown(self) -> None:
        image = Image.new("RGBA", (4, 4), (60, 120, 90, 255))
        cleaned, removed = remove_key_bleed(image, MAGENTA)
        assert removed == 0
        assert cleaned.getpixel((0, 0))[3] == 255

    def test_noop_for_a_non_magenta_key(self) -> None:
        image = Image.new("RGBA", (4, 4), (10, 200, 30, 255))
        cleaned, removed = remove_key_bleed(image, (0, 200, 0))
        assert removed == 0
        assert cleaned is image

    def test_bleed_count_matches_what_removal_takes(self) -> None:
        image = Image.new("RGBA", (2, 2), (150, 90, 150, 255))
        assert bleed_pixel_count(image, MAGENTA) == 4


class TestSprites:
    def test_end_to_end_sprite_has_alpha_and_a_flat_base(self) -> None:
        result, note = build_sprite(plate_with_shape(), padding=4)
        assert result.mode == "RGBA"
        assert note["key"] == MAGENTA
        assert note["anchor_offset_px"] == 0
        assert result.getchannel("A").getextrema()[0] == 0

    def test_trimmed_sprite_keeps_the_shape_ratio(self) -> None:
        result, _ = build_sprite(plate_with_shape(), padding=2)
        # The blob is 80x200 with 2px of padding; keying's erode/blur softens the
        # edge by a pixel or two, so compare the shape, not the exact count.
        assert abs(result.size[0] - (80 + 4)) <= 4
        assert abs(result.size[1] - (200 + 2)) <= 4
        assert 0.35 < result.size[0] / result.size[1] < 0.48

    def test_watermark_corner_is_cleared(self) -> None:
        board = plate_with_shape()
        board.paste((250, 250, 250), (260, 300, 310, 315))  # pale mark bottom-right
        result, _ = build_sprite(board, padding=0)
        width, height = result.size
        assert result.getpixel((width - 2, height - 2))[3] < 255

    def test_max_size_caps_the_long_edge(self) -> None:
        result, _ = build_sprite(plate_with_shape(), max_size=64)
        assert max(result.size) == 64

    def test_report_checks_pass_on_a_clean_sprite(self) -> None:
        result, note = build_sprite(plate_with_shape())
        checks = verify(result, note["key"], note["anchor_offset_px"])
        assert checks["checks"]["has_transparency"]
        assert checks["checks"]["anchor_at_bottom"]
        assert checks["checks"]["no_key_bleed"]


class TestBackgrounds:
    def test_crops_the_watermark_band(self) -> None:
        plate = Image.new("RGB", (400, 400), (30, 60, 90))
        result, note = build_background(plate, crop_bottom=0.07)
        assert note["cropped_bottom_px"] == 28
        assert result.size == (400, 372)

    def test_resizes_after_cropping(self) -> None:
        plate = Image.new("RGB", (400, 400), (30, 60, 90))
        result, _ = build_background(plate, crop_bottom=0.07, size=(200, 186))
        assert result.size == (200, 186)

    def test_refuses_to_crop_everything(self) -> None:
        with pytest.raises(GuardError, match="leave nothing"):
            build_background(Image.new("RGB", (40, 40)), crop_bottom=1.0)

    def test_background_has_no_anchor_check(self) -> None:
        plate = Image.new("RGB", (100, 100), (1, 2, 3))
        result, _ = build_background(plate)
        assert "anchor_at_bottom" not in verify(result, None, None)["checks"]


class TestDuplicates:
    def test_identical_files_share_a_hash(self, tmp_path: Path) -> None:
        image = Image.new("RGBA", (8, 8), (1, 2, 3, 255))
        image.save(tmp_path / "a.png")
        image.save(tmp_path / "b.png")
        Image.new("RGBA", (8, 8), (4, 5, 6, 255)).save(tmp_path / "c.png")
        index = duplicate_index(tmp_path)
        hashes = sorted(len(paths) for paths in index.values())
        assert hashes == [1, 2]
