"""Tests for the package gate.

A gate that passes everything is worse than no gate: it turns "we have a check"
into a reason to stop looking. Every test here builds a synthetic build tree
with one specific defect and asserts the gate refuses it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from package_gate import check, check_subpackages  # noqa: E402
from wechat_package_report import analyze  # noqa: E402

MB = 1024 * 1024


def write(path: Path, size: int, marker: bytes = b"x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(marker * size)


def make_build(
    root: Path,
    *,
    main_bytes: int = 2 * MB,
    subpackage: bool = True,
    subpackage_bytes: int = 700 * 1024,
    declare_in_game_json: bool = True,
    register_in_settings: bool = True,
    preload: bool = False,
    duplicate_in_main: bool = False,
    entry_file: bool = True,
    config_file: bool = True,
) -> Path:
    write(root / "game.js", 1024)
    write(root / "cocos-js" / "cc.js", main_bytes)
    game = {"deviceOrientation": "landscape"}
    settings = {
        "assets": {
            "subpackages": [],
            "preloadBundles": [{"bundle": "main"}],
        }
    }

    if subpackage:
        bundle = root / "subpackages" / "resources"
        bundle.mkdir(parents=True, exist_ok=True)
        write(bundle / "native" / "bg.jpg", subpackage_bytes)
        if entry_file:
            write(bundle / "game.js", 128)
        if config_file:
            (bundle / "config.abc12.json").write_text("{}", encoding="utf-8")
        if declare_in_game_json:
            game["subpackages"] = [{"name": "resources", "root": "subpackages/resources/"}]
        if register_in_settings:
            settings["assets"]["subpackages"] = ["resources"]
        if preload:
            settings["assets"]["preloadBundles"].append({"bundle": "resources"})
        if duplicate_in_main:
            write(root / "assets" / "resources" / "native" / "bg.jpg", subpackage_bytes)

    (root / "game.json").write_text(json.dumps(game), encoding="utf-8")
    (root / "src").mkdir(exist_ok=True)
    (root / "src" / "settings.abc.json").write_text(json.dumps(settings), encoding="utf-8")
    return root


def run_gate(root: Path, budget_mb: float = 3.5):
    report = analyze(root, top=5)
    return check(report, int(budget_mb * MB), None, root)


def test_clean_build_passes(tmp_path: Path) -> None:
    root = make_build(tmp_path)
    failures, warnings = run_gate(root)
    assert failures == []
    assert warnings == []


def test_main_package_over_budget_fails(tmp_path: Path) -> None:
    root = make_build(tmp_path, main_bytes=4 * MB)
    failures, _ = run_gate(root)
    assert any("超过预算" in item for item in failures)
    assert any("硬限制" in item for item in failures)


def test_subpackage_weight_does_not_count_against_the_main_budget(tmp_path: Path) -> None:
    """2.9 MB of art in a subpackage must not fail a 3.5 MB main-package budget."""
    root = make_build(tmp_path, main_bytes=2 * MB, subpackage_bytes=2_900_000)
    failures, _ = run_gate(root, budget_mb=3.5)
    assert failures == []


def test_declared_but_missing_subpackage_fails(tmp_path: Path) -> None:
    root = make_build(tmp_path, subpackage=False)
    (root / "game.json").write_text(
        json.dumps({"subpackages": [{"name": "resources", "root": "subpackages/resources/"}]}),
        encoding="utf-8",
    )
    failures, _ = run_gate(root)
    assert any("目录不存在" in item for item in failures)


def test_unregistered_subpackage_fails(tmp_path: Path) -> None:
    root = make_build(tmp_path, register_in_settings=False)
    failures, _ = run_gate(root)
    assert any("settings.assets.subpackages" in item for item in failures)


def test_subpackage_still_in_main_package_fails(tmp_path: Path) -> None:
    root = make_build(tmp_path, duplicate_in_main=True)
    failures, _ = run_gate(root)
    assert any("资源被重复打包" in item for item in failures)


def test_missing_entry_file_fails(tmp_path: Path) -> None:
    root = make_build(tmp_path, entry_file=False)
    failures, _ = run_gate(root)
    assert any("game.js" in item for item in failures)


def test_missing_bundle_config_fails(tmp_path: Path) -> None:
    root = make_build(tmp_path, config_file=False)
    failures, _ = run_gate(root)
    assert any("config.*.json" in item for item in failures)


def test_still_preloaded_warns(tmp_path: Path) -> None:
    root = make_build(tmp_path, preload=True)
    failures, warnings = run_gate(root)
    assert failures == []
    assert any("preloadBundles" in item for item in warnings)


def test_stray_directory_under_subpackages_fails(tmp_path: Path) -> None:
    root = make_build(tmp_path)
    write(root / "subpackages" / "orphan" / "blob.bin", 4096)
    failures, _ = run_gate(root)
    assert any("未在 game.json 声明" in item for item in failures)


def test_declared_isSubpackage_without_artifact_fails(tmp_path: Path) -> None:
    root = make_build(tmp_path, subpackage=False)
    config = tmp_path / "config.json"
    config.write_text(
        json.dumps({"bundles": [{"name": "resources", "isSubpackage": True}]}),
        encoding="utf-8",
    )
    report = analyze(root, top=5)
    failures, _ = check(report, 3 * MB, config, root)
    assert any("声明为分包" in item for item in failures)


@pytest.mark.parametrize("size", [0, 1])
def test_check_subpackages_ignores_builds_without_declaration(tmp_path: Path, size: int) -> None:
    root = tmp_path / "build"
    root.mkdir()
    (root / "game.json").write_text(json.dumps({"subpackages": []}), encoding="utf-8")
    (root / "src").mkdir()
    (root / "src" / "settings.json").write_text("{}", encoding="utf-8")
    failures, warnings = check_subpackages(root)
    assert failures == []
    assert warnings == []
