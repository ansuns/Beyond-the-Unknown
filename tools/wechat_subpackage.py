"""Move Cocos bundles into real WeChat subpackages.

Cocos 3.8.8 has a subpackage option in the build panel, but the CLI task
accepts `bundles[].isSubpackage` and then ignores it: the artifact still has
`assets/<bundle>/` and `settings.assets.subpackages` stays empty. The engine
adapter in `engine-adapter.js` shows exactly what the build should have
produced:

    var a0 = {};                                  // bundle name -> base dir
    settings.querySettings('assets', 'subpackages').forEach(name => {
        a0[name] = 'subpackages/' + name;
    });
    // download: a0[bundle] ? 'subpackages/<bundle>/config.<ver>.json'
    //                     : 'assets/<bundle>/config.<ver>.json'

and the WeChat side needs `game.json` to declare the same directory, otherwise
the platform never downloads it. This script performs those three edits and
nothing else - no asset is rewritten, so the bundle keeps loading through the
normal `assetManager.loadBundle(name)` path.

Usage:
    python tools/wechat_subpackage.py --build client/build/wechatgame-slim --bundle resources
    python tools/wechat_subpackage.py --build <dir> --bundle a --bundle b --check
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

SUBPACKAGE_DIR = "subpackages"

# WeChat requires every subpackage root to contain a game.js entry file and
# refuses to compile without it: "未找到 subpackages/<name>/game.js". A bundle of
# assets has no code to run, so the entry is an empty stub; Cocos loads the
# bundle by reading config.<version>.json itself.
SUBPACKAGE_ENTRY = (
    "// WeChat requires a game.js entry in every subpackage root.\n"
    "// This bundle ships assets only; Cocos loads it via assetManager.loadBundle.\n"
)


def find_version(bundle_dir: Path) -> str:
    """The version suffix is part of the file name, e.g. config.6c149.json."""
    configs = sorted(bundle_dir.glob("config.*.json"))
    if not configs:
        raise SystemExit(f"{bundle_dir} has no config.<version>.json; wrong bundle?")
    return configs[0].name.split(".")[1]


def settings_file(build: Path) -> Path:
    candidates = sorted((build / "src").glob("settings*.json"))
    if not candidates:
        raise SystemExit("no src/settings*.json in the build output")
    return candidates[0]


def check(build: Path, bundles: list[str]) -> tuple[bool, list[str]]:
    problems: list[str] = []
    game = json.loads((build / "game.json").read_text(encoding="utf-8"))
    declared = {item.get("name"): item.get("root") for item in game.get("subpackages", [])}
    settings = json.loads(settings_file(build).read_text(encoding="utf-8"))
    registered = set(settings.get("assets", {}).get("subpackages", []))
    preload = {item.get("bundle") for item in settings.get("assets", {}).get("preloadBundles", [])}

    for name in bundles:
        target = build / SUBPACKAGE_DIR / name
        if not target.is_dir():
            problems.append(f"{name}: 缺少 {SUBPACKAGE_DIR}/{name}/ 目录")
        elif not any(target.glob("config.*.json")):
            problems.append(f"{name}: 分包目录里没有 config.*.json")
        if target.is_dir() and not (target / "game.js").exists():
            problems.append(f"{name}: 分包缺少 game.js 入口，微信会拒绝编译")
        if (build / "assets" / name).exists():
            problems.append(f"{name}: 主包 assets/{name}/ 仍然存在，资源被重复打包")
        if name not in declared:
            problems.append(f"{name}: game.json 未声明")
        elif not str(declared[name]).startswith(f"{SUBPACKAGE_DIR}/{name}"):
            problems.append(f"{name}: game.json root={declared[name]!r} 与目录不一致")
        if name not in registered:
            problems.append(f"{name}: settings.assets.subpackages 未登记，运行时仍按主包路径加载")
        if name in preload:
            problems.append(f"{name}: 仍在 preloadBundles 中，会在首屏被下载")
    return (not problems), problems


def apply(build: Path, bundles: list[str]) -> None:
    game_path = build / "game.json"
    game = json.loads(game_path.read_text(encoding="utf-8"))
    settings_path = settings_file(build)
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    assets = settings.setdefault("assets", {})

    subpackages = [item for item in game.get("subpackages", []) if item.get("name")]
    registered = [name for name in assets.get("subpackages", []) if name]
    preload = [item for item in assets.get("preloadBundles", []) if item.get("bundle")]

    for name in bundles:
        source = build / "assets" / name
        target = build / SUBPACKAGE_DIR / name
        if source.is_dir():
            version = find_version(source)
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                shutil.rmtree(target)
            shutil.move(str(source), str(target))
            print(f"moved assets/{name} -> {SUBPACKAGE_DIR}/{name} (config.{version}.json)")
        elif not target.is_dir():
            raise SystemExit(f"bundle {name} exists neither in assets/ nor subpackages/")

        entry_file = target / "game.js"
        if not entry_file.exists():
            entry_file.write_text(SUBPACKAGE_ENTRY, encoding="utf-8")
        entry = {"name": name, "root": f"{SUBPACKAGE_DIR}/{name}/"}
        subpackages = [item for item in subpackages if item.get("name") != name] + [entry]
        if name not in registered:
            registered.append(name)
        preload = [item for item in preload if item.get("bundle") != name]

    game["subpackages"] = subpackages
    assets["subpackages"] = registered
    assets["preloadBundles"] = preload

    game_path.write_text(json.dumps(game, ensure_ascii=False, indent=4) + "\n", encoding="utf-8")
    settings_path.write_text(
        json.dumps(settings, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", required=True, type=Path)
    parser.add_argument("--bundle", action="append", required=True)
    parser.add_argument("--check", action="store_true", help="verify only, change nothing")
    args = parser.parse_args()

    build = args.build.resolve()
    if not (build / "game.json").exists():
        print(f"{build} is not a wechatgame build output")
        return 2

    if not args.check:
        apply(build, args.bundle)

    ok, problems = check(build, args.bundle)
    for problem in problems:
        print(f"FAIL: {problem}")
    if ok:
        for name in args.bundle:
            size = sum(p.stat().st_size for p in (build / SUBPACKAGE_DIR / name).rglob("*") if p.is_file())
            print(f"OK: {SUBPACKAGE_DIR}/{name} {size / 1024:.0f} KB")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
