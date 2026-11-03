"""Prove that moving assets did not change a single asset UUID.

Cocos addresses every asset by the uuid stored in its `.meta`. Moving a file and
letting the editor re-import it produces a new uuid and silently breaks every
scene, prefab and script that referenced the old one - which is why "the build
still works" is not evidence that the move was safe.

This compares the committed (HEAD) `.meta` files against the working tree and
reports, per asset, whether the uuid survived. It also reports assets that
disappeared or appeared, so a move cannot hide behind a matching total.

Usage:
    python tools/assert_asset_uuid.py --before client/assets/resources --after client/assets/gameplay
    python tools/assert_asset_uuid.py --before client/assets/resources --after client/assets/gameplay --json out.json
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def git_show(repo: Path, relpath: str) -> str | None:
    result = subprocess.run(
        ["git", "show", f"HEAD:{relpath}"],
        cwd=repo,
        capture_output=True,
        encoding="utf-8",
    )
    return result.stdout if result.returncode == 0 else None


def git_ls(repo: Path, relpath: str) -> list[str]:
    result = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", "HEAD", relpath],
        cwd=repo,
        capture_output=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        return []
    return [line for line in result.stdout.splitlines() if line.endswith(".meta")]


def head_meta_map(repo: Path, relpath: str) -> dict[str, dict]:
    """basename -> parsed meta, for every .meta committed under `relpath`."""
    out: dict[str, dict] = {}
    for path in git_ls(repo, relpath):
        text = git_show(repo, path)
        if text is None:
            continue
        try:
            meta = json.loads(text)
        except json.JSONDecodeError:
            continue
        out[Path(path).name] = {"uuid": meta.get("uuid"), "path": path, "userData": meta.get("userData")}
    return out


def worktree_meta_map(root: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for path in sorted(root.rglob("*.meta")):
        try:
            meta = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        out[path.name] = {"uuid": meta.get("uuid"), "path": str(path)}
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", required=True, help="asset directory as committed at HEAD")
    parser.add_argument("--after", required=True, help="asset directory in the working tree")
    parser.add_argument("--json", type=Path, help="write the full comparison here")
    args = parser.parse_args()

    repo = Path(
        subprocess.run(
            ["git", "rev-parse", "--show-toplevel"], capture_output=True, encoding="utf-8"
        ).stdout.strip()
    )
    before_root = Path(args.before).as_posix()
    after_root = Path(args.after)

    before = head_meta_map(repo, before_root)
    after = worktree_meta_map(after_root)

    kept, changed, lost, added = [], [], [], []
    for name, item in sorted(after.items()):
        previous = before.get(name)
        if previous is None:
            added.append({"name": name, "path": item["path"], "uuid": item["uuid"]})
        elif previous["uuid"] == item["uuid"]:
            kept.append(
                {
                    "name": name,
                    "uuid": item["uuid"],
                    "from": previous["path"],
                    "to": item["path"],
                }
            )
        else:
            changed.append(
                {"name": name, "before": previous["uuid"], "after": item["uuid"], "to": item["path"]}
            )
    for name, item in sorted(before.items()):
        if name not in after:
            lost.append({"name": name, "uuid": item["uuid"], "from": item["path"]})

    print(f"kept    {len(kept):3d} meta files kept their uuid")
    print(f"changed {len(changed):3d} meta files got a NEW uuid")
    print(f"missing {len(lost):3d} committed meta files are absent from {after_root.as_posix()}")
    print(f"added   {len(added):3d} meta files did not exist at HEAD")
    for item in changed:
        print(f"  FAIL changed: {item['name']} {item['before']} -> {item['after']}")
    for item in lost:
        print(f"  note missing: {item['name']} ({item['uuid']}) was {item['from']}")
    for item in added:
        print(f"  note added: {item['name']} ({item['uuid']})")

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(
                {"kept": kept, "changed": changed, "lost": lost, "added": added},
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

    if changed:
        print("FAIL: at least one uuid changed; references to it are broken")
        return 1
    print("OK: no uuid changed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
