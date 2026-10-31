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
DEFAULT_BUDGET_BYTES = int(3.5 * 1024 * 1024)
DUPLICATE_WARN_BYTES = 64 * 1024


def check(report: dict, budget_bytes: int, config_path: Path | None) -> tuple[list[str], list[str]]:
    failures: list[str] = []
    warnings: list[str] = []

    total = report["total_bytes"]
    if total > budget_bytes:
        failures.append(
            f"包体 {human(total)} 超过预算 {human(budget_bytes)}（微信上限 {human(PLATFORM_LIMIT_BYTES)}）"
        )
    if total > PLATFORM_LIMIT_BYTES:
        failures.append(
            f"包体 {human(total)} 超过微信 {human(PLATFORM_LIMIT_BYTES)} 硬限制，会被拒绝上传"
        )

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
            if bundle.get("isSubpackage") and not report.get("bundles", {}).get(
                bundle.get("name", "")
            ):
                warnings.append(
                    f"bundle {bundle.get('name')} 声明为分包，但构建产物里没有对应目录"
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
    else:
        build_root = args.build
        if not (build_root / "game.json").exists():
            print(f"FAIL: {build_root} 不是微信小游戏构建产物（缺少 game.json）")
            return 2
        report = analyze(build_root.resolve(), top=20)
    budget = int(args.budget * 1024 * 1024)
    failures, warnings = check(report, budget, args.config)

    print(f"主包：{report['total_human']} / 预算 {human(budget)} / 上限 {human(PLATFORM_LIMIT_BYTES)}")
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
