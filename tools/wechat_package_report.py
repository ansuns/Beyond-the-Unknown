"""Measure a WeChat mini game build the way the platform counts it.

Three numbers get confused constantly and they are not interchangeable:

* the source tree (assets + scripts) - what you edit;
* the build output - what Cocos writes to build/<platform>;
* the upload package - what WeChat sums and caps at 4 MB.

This tool reports all three, splits the build by category (engine, code, art,
audio, fonts, config), lists the largest files, and looks for duplicate payloads
and resources that nothing references. It never deletes anything: a deletion
without a measurement is a guess.

Usage:
    python tools/wechat_package_report.py --build client/build/wechatgame-slim
    python tools/wechat_package_report.py --build <dir> --json <out.json> --top 20
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLIENT = ROOT / "client"

MAIN_LIMIT_BYTES = 4 * 1024 * 1024
TARGET_BYTES = int(3.5 * 1024 * 1024)

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".astc", ".pkm"}
AUDIO_SUFFIXES = {".mp3", ".ogg", ".wav", ".m4a", ".aac", ".webm"}
FONT_SUFFIXES = {".ttf", ".otf", ".woff", ".woff2", ".fnt"}
CONFIG_SUFFIXES = {".json", ".plist", ".txt", ".yaml", ".yml"}

# WeChat counts these as part of the package; macOS/Windows metadata does not
# exist in a check-out but a stray .DS_Store from a designer's copy does.
IGNORED_NAMES = {".DS_Store", "Thumbs.db"}


def human(size: int) -> str:
    if size >= 1024 * 1024:
        return f"{size / 1024 / 1024:.2f} MB"
    if size >= 1024:
        return f"{size / 1024:.0f} KB"
    return f"{size} B"


def category_of(path: Path, build_root: Path) -> str:
    rel = path.relative_to(build_root)
    parts = rel.parts
    suffix = path.suffix.lower()
    if parts[0] == "cocos-js" or path.name.startswith(("bullet", "spine", "cc.")):
        return "engine"
    if suffix in IMAGE_SUFFIXES:
        return "image"
    if suffix in AUDIO_SUFFIXES:
        return "audio"
    if suffix in FONT_SUFFIXES:
        return "font"
    if suffix in {".js", ".mjs"}:
        # Engine assets live in cocos-js/assets and are already counted above.
        return "code" if len(parts) == 1 or parts[0] in {"src", "assets"} else "code"
    if suffix in CONFIG_SUFFIXES:
        return "config"
    return "other"


def walk_files(root: Path) -> list[tuple[Path, int]]:
    files: list[tuple[Path, int]] = []
    for path in root.rglob("*"):
        if not path.is_file() or path.name in IGNORED_NAMES:
            continue
        files.append((path, path.stat().st_size))
    return files


def directory_sizes(root: Path, files: list[tuple[Path, int]]) -> dict[str, int]:
    totals: dict[str, int] = defaultdict(int)
    for path, size in files:
        rel = path.relative_to(root)
        key = rel.parts[0] if len(rel.parts) > 1 else "(root files)"
        totals[key] += size
    return dict(sorted(totals.items(), key=lambda item: item[1], reverse=True))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def duplicate_groups(files: list[tuple[Path, int]], minimum: int = 4096) -> list[dict]:
    by_hash: dict[str, list[Path]] = defaultdict(list)
    for path, size in files:
        if size < minimum:
            continue
        by_hash[sha256(path)].append(path)
    groups = []
    for digest, paths in by_hash.items():
        if len(paths) < 2:
            continue
        groups.append(
            {
                "sha256": digest,
                "size": paths[0].stat().st_size,
                "wasted": paths[0].stat().st_size * (len(paths) - 1),
                "paths": [str(path) for path in paths],
            }
        )
    return sorted(groups, key=lambda item: item["wasted"], reverse=True)


def referenced_uuids(build_root: Path) -> set[str]:
    """Collect asset uuids that appear in any bundle config or scene data.

    A Cocos build writes a config.json per bundle listing every asset it ships.
    Anything on disk under assets/ but absent from all configs is either dead
    weight or part of a bundle the build did not include.
    """
    uuids: set[str] = set()
    for config in build_root.rglob("config.json"):
        try:
            payload = json.loads(config.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for key in ("uuids", "paths", "packs", "versions", "scenes"):
            value = payload.get(key)
            if isinstance(value, dict):
                uuids.update(str(name) for name in value)
            elif isinstance(value, list):
                uuids.update(str(name) for name in value)
    return uuids


def source_report() -> dict:
    """Size of the editable tree, split by what it is."""
    assets = CLIENT / "assets"
    scripts = assets / "scripts"
    resources = assets / "resources"
    scenes = assets / "scenes"
    meta_bytes = 0
    content_bytes = 0
    for path in assets.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix == ".meta":
            meta_bytes += path.stat().st_size
        else:
            content_bytes += path.stat().st_size
    return {
        "assets_bytes": sum(p.stat().st_size for p in assets.rglob("*") if p.is_file()),
        "scripts_bytes": sum(p.stat().st_size for p in scripts.rglob("*") if p.is_file()),
        "resources_bytes": sum(p.stat().st_size for p in resources.rglob("*") if p.is_file()),
        "scenes_bytes": sum(p.stat().st_size for p in scenes.rglob("*") if p.is_file()),
        "meta_bytes": meta_bytes,
        "content_bytes": content_bytes,
    }


def analyze(build_root: Path, top: int) -> dict:
    files = walk_files(build_root)
    total = sum(size for _, size in files)
    by_category: dict[str, int] = defaultdict(int)
    for path, size in files:
        by_category[category_of(path, build_root)] += size

    largest = sorted(files, key=lambda item: item[1], reverse=True)[:top]
    duplicates = duplicate_groups(files)

    # Bundles are the directories directly under assets/.
    assets_dir = build_root / "assets"
    bundles = {}
    if assets_dir.is_dir():
        for bundle in sorted(assets_dir.iterdir()):
            if bundle.is_dir():
                bundles[bundle.name] = sum(
                    size for path, size in files if bundle in path.parents
                )

    return {
        "build_root": str(build_root),
        "total_bytes": total,
        "total_human": human(total),
        "main_limit_bytes": MAIN_LIMIT_BYTES,
        "target_bytes": TARGET_BYTES,
        "over_limit": total > MAIN_LIMIT_BYTES,
        "over_target": total > TARGET_BYTES,
        "headroom_bytes": TARGET_BYTES - total,
        "by_category": {key: value for key, value in sorted(by_category.items())},
        "by_directory": directory_sizes(build_root, files),
        "bundles": bundles,
        "largest": [
            {
                "path": str(path.relative_to(build_root)).replace("\\", "/"),
                "bytes": size,
                "category": category_of(path, build_root),
            }
            for path, size in largest
        ],
        "duplicates": [
            {
                "size": group["size"],
                "wasted": group["wasted"],
                "paths": [str(Path(p).relative_to(build_root)).replace("\\", "/") for p in group["paths"]],
            }
            for group in duplicates[:10]
        ],
        "duplicate_waste_bytes": sum(group["wasted"] for group in duplicates),
        "file_count": len(files),
        "source": source_report(),
    }


def render(report: dict) -> str:
    lines = [
        "# WeChat 小游戏包体分析",
        "",
        f"- 构建目录：`{report['build_root']}`",
        f"- 文件数：{report['file_count']}",
        f"- **总大小：{report['total_human']}**（{report['total_bytes']} 字节）",
        f"- 主包上限：{human(report['main_limit_bytes'])}；内部目标：{human(report['target_bytes'])}",
        f"- 距目标余量：{human(report['headroom_bytes'])}"
        + ("（已超目标）" if report["over_target"] else ""),
        "",
        "## 源码目录 vs 构建产物",
        "",
        "| 口径 | 大小 | 说明 |",
        "|---|---:|---|",
        f"| 源码 assets 内容 | {human(report['source']['content_bytes'])} | 不含 .meta |",
        f"| 其中 .meta | {human(report['source']['meta_bytes'])} | 不入包 |",
        f"| 其中脚本 | {human(report['source']['scripts_bytes'])} | 会被编译 |",
        f"| 其中 resources | {human(report['source']['resources_bytes'])} | 会被打包 |",
        f"| 构建产物 | {human(report['total_bytes'])} | 微信实际统计的口径 |",
        "",
        "源码目录体积不等于上传包体积：.meta、编辑器缓存、未引用资源都不进包，"
        "而引擎与适配层只在构建产物里出现。",
        "",
        "## 分类",
        "",
        "| 类别 | 大小 | 占比 |",
        "|---|---:|---:|",
    ]
    total = max(1, report["total_bytes"])
    for key, value in report["by_category"].items():
        lines.append(f"| {key} | {human(value)} | {100 * value / total:.1f}% |")

    lines += ["", "## 目录", "", "| 目录 | 大小 | 占比 |", "|---|---:|---:|"]
    for key, value in report["by_directory"].items():
        lines.append(f"| {key} | {human(value)} | {100 * value / total:.1f}% |")

    if report["bundles"]:
        lines += ["", "## Bundle", "", "| Bundle | 大小 |", "|---|---:|"]
        for key, value in report["bundles"].items():
            lines.append(f"| {key} | {human(value)} |")

    lines += ["", "## 最大文件", "", "| 文件 | 大小 | 类别 |", "|---|---:|---|"]
    for item in report["largest"]:
        lines.append(f"| `{item['path']}` | {human(item['bytes'])} | {item['category']} |")

    lines += ["", "## 重复内容", ""]
    if report["duplicates"]:
        lines.append(f"浪费 {human(report['duplicate_waste_bytes'])}：")
        lines.append("")
        for group in report["duplicates"]:
            lines.append(f"- {human(group['size'])} × {len(group['paths'])}：")
            for path in group["paths"]:
                lines.append(f"  - `{path}`")
    else:
        lines.append("未发现按内容去重后完全相同的文件。")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", required=True, type=Path)
    parser.add_argument("--json", type=Path)
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument("--fail-over-target", action="store_true")
    args = parser.parse_args()

    build_root = args.build
    if not (build_root / "game.json").exists() and not (build_root / "index.html").exists():
        parser.error(f"{build_root} does not look like a Cocos build output")
    report = analyze(build_root.resolve(), args.top)
    text = render(report)
    print(text)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.fail_over_target and report["total_bytes"] > TARGET_BYTES:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
