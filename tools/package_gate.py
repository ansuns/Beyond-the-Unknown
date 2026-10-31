"""Release gate for the WeChat package.

Fails the build instead of leaving the number to memory. The checks are the ones
that actually went wrong during this project:

* the package silently grew past 4 MB and only DevTools noticed, at upload time;
* art was delivered at full size and nobody measured it;
* a bundle can be configured and then quietly ship inside the main package.

Thresholds are arguments, not constants, so CI can tighten them per release.

Usage:
    python tools/package_gate.py --build client/build/wechatgame-slim
    python tools/package_gate.py --build <dir> --budget 3.5 --strict
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from wechat_package_report import analyze, human  # noqa: E402

PLATFORM_LIMIT_BYTES = 4 * 1024 * 1024
# WeChat's total for the main package plus every local subpackage.
PLATFORM_TOTAL_LIMIT_BYTES = 20 * 1024 * 1024
DEFAULT_BUDGET_BYTES = int(3.5 * 1024 * 1024)
DUPLICATE_WARN_BYTES = 64 * 1024


def check_subpackages(build_root: Path) -> tuple[list[str], list[str]]:
    """Verify a declared subpackage is real, registered and not double-shipped."""
    failures: list[str] = []
    warnings: list[str] = []
    game_path = build_root / "game.json"
    if not game_path.exists():
        return failures, warnings
    game = json.loads(game_path.read_text(encoding="utf-8"))
    declared = game.get("subpackages") or []
    if not declared:
        return failures, warnings

    settings_files = sorted((build_root / "src").glob("settings*.json"))
    if not settings_files:
        failures.append("缺少 src/settings*.json，无法确认分包是否被运行时识别")
        return failures, warnings
    assets = json.loads(settings_files[0].read_text(encoding="utf-8")).get("assets", {})
    registered = set(assets.get("subpackages", []))
    preload = {item.get("bundle") for item in assets.get("preloadBundles", [])}

    for item in declared:
        name = item.get("name")
        root = str(item.get("root") or "").strip("/")
        if not name or not root:
            failures.append(f"分包声明不完整：{item}")
            continue
        directory = build_root / root
        if not directory.is_dir():
            failures.append(f"{name}: game.json 声明了 {root}/ 但目录不存在")
            continue
        if not (directory / "game.js").exists():
            failures.append(f"{name}: 分包缺少 game.js，微信会拒绝编译")
        if not any(directory.glob("config.*.json")):
            failures.append(f"{name}: 分包里没有 config.*.json，运行时读不到资源索引")
        if name not in registered:
            failures.append(
                f"{name}: 未写入 settings.assets.subpackages，运行时仍按主包路径加载"
            )
        if name in preload:
            warnings.append(f"{name}: 仍在 preloadBundles 中，会拖慢首屏")
        if (build_root / "assets" / name).exists():
            failures.append(f"{name}: assets/{name}/ 仍然存在，资源被重复打包")
    return failures, warnings


def check(report: dict, budget_bytes: int, config_path: Path | None, build_root: Path | None) -> tuple[list[str], list[str]]:
    failures: list[str] = []
    warnings: list[str] = []

    # The platform caps the main package; subpackage bytes are counted apart.
    main_bytes = report.get("main_bytes", report["total_bytes"])
    if main_bytes > budget_bytes:
        failures.append(
            f"主包 {human(main_bytes)} 超过预算 {human(budget_bytes)}（微信上限 {human(PLATFORM_LIMIT_BYTES)}）"
        )
    if main_bytes > PLATFORM_LIMIT_BYTES:
        failures.append(
            f"主包 {human(main_bytes)} 超过微信 {human(PLATFORM_LIMIT_BYTES)} 硬限制，会被拒绝上传"
        )
    if report["total_bytes"] > PLATFORM_TOTAL_LIMIT_BYTES:
        failures.append(
            f"主包加全部分包 {human(report['total_bytes'])} 超过微信总包 {human(PLATFORM_TOTAL_LIMIT_BYTES)} 限制"
        )
    if report.get("stray_subpackage_bytes"):
        failures.append(
            f"subpackages/ 下有 {human(report['stray_subpackage_bytes'])} 未在 game.json 声明"
        )

    if build_root is not None:
        sub_failures, sub_warnings = check_subpackages(build_root)
        failures.extend(sub_failures)
        warnings.extend(sub_warnings)

    # A bundle configured as a subpackage but still counted in the main total
    # means the split never happened - the exact failure this gate exists for.
    if config_path and config_path.exists():
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            failures.append(f"构建配置无法解析：{error}")
            config = {}
        declared = config.get("bundles") or config.get("bundleConfigs") or []
        for bundle in declared:
            if not isinstance(bundle, dict):
                continue
            if bundle.get("isSubpackage") and not report.get("subpackage_bytes", {}).get(
                bundle.get("name", "")
            ):
                failures.append(
                    f"bundle {bundle.get('name')} 声明为分包，但产物里没有对应分包大小"
                )

    if report["duplicate_waste_bytes"] > DUPLICATE_WARN_BYTES:
        warnings.append(
            f"重复内容浪费 {human(report['duplicate_waste_bytes'])}，考虑合并或图集"
        )

    if report["by_category"].get("audio", 0) > 512 * 1024:
        warnings.append(
            f"音频 {human(report['by_category']['audio'])} 偏大，建议转远程或压缩码率"
        )

    if report["file_count"] > 400:
        warnings.append(f"包内文件数 {report['file_count']}，小游戏读写会变慢，考虑合并")

    return failures, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--build", type=Path, help="build output to measure")
    source.add_argument(
        "--from-report",
        type=Path,
        help="re-check a recorded report (CI cannot run the Cocos editor)",
    )
    parser.add_argument("--budget", type=float, default=3.5, help="internal budget in MB")
    parser.add_argument("--config", type=Path, help="build config used for this build")
    parser.add_argument("--json", type=Path)
    parser.add_argument("--strict", action="store_true", help="treat warnings as failures")
    args = parser.parse_args()

    if args.from_report:
        # CI has no Cocos editor, so it re-checks the last verified measurement
        # instead of pretending to rebuild. Refresh the file by running the real
        # gate locally after a build.
        payload = json.loads(args.from_report.read_text(encoding="utf-8"))
        report = payload.get("report", payload)
        measured_root = None
    else:
        build_root = args.build
        if not (build_root / "game.json").exists():
            print(f"FAIL: {build_root} 不是微信小游戏构建产物（缺少 game.json）")
            return 2
        report = analyze(build_root.resolve(), top=20)
        measured_root = build_root.resolve()
    budget = int(args.budget * 1024 * 1024)
    failures, warnings = check(report, budget, args.config, measured_root)

    print(
        f"主包：{report['main_human']} / 预算 {human(budget)} / "
        f"上限 {human(PLATFORM_LIMIT_BYTES)}；总计 {report['total_human']}"
    )
    if report.get("subpackage_bytes"):
        for name, size in report["subpackage_bytes"].items():
            print(f"分包 {name}：{human(size)}")
    print(f"分类：" + ", ".join(f"{k} {human(v)}" for k, v in report["by_category"].items()))
    for item in warnings:
        print(f"WARN: {item}")
    for item in failures:
        print(f"FAIL: {item}")

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(
                {"report": report, "failures": failures, "warnings": warnings},
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

    if failures:
        return 1
    if warnings and args.strict:
        return 1
    print("PASS: 包体门禁通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
