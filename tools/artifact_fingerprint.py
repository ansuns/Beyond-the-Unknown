"""Fingerprint a build artifact so two builds can be compared byte for byte.

A green build is not the same as a reproducible build: the same source has to
produce the same files. This walks a build directory, hashes every file and
writes a sorted manifest, so "I ran it twice" becomes a diffable claim.

Usage:
    python tools/artifact_fingerprint.py --build client/build/wechatgame-slim --out a.json
    python tools/artifact_fingerprint.py --build client/build/wechatgame-slim --out b.json
    python tools/artifact_fingerprint.py --compare a.json b.json

`--compare` exits 1 when the two manifests differ, and prints what changed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

# Files whose content legitimately carries a timestamp or a random build id.
# Anything listed here is still hashed, but a mismatch is reported as a warning
# instead of a failure - and only for these names, never for game code.
VOLATILE_NAMES = {"project.config.json"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fingerprint(build: Path) -> dict:
    files = {}
    for path in sorted(build.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(build).as_posix()
        files[rel] = {"size": path.stat().st_size, "sha256": sha256(path)}
    total = sum(item["size"] for item in files.values())
    return {"root": str(build), "fileCount": len(files), "totalBytes": total, "files": files}


def compare(a_path: Path, b_path: Path) -> int:
    a = json.loads(a_path.read_text(encoding="utf-8"))
    b = json.loads(b_path.read_text(encoding="utf-8"))
    left, right = a["files"], b["files"]

    only_a = sorted(set(left) - set(right))
    only_b = sorted(set(right) - set(left))
    changed = sorted(
        name for name in set(left) & set(right) if left[name]["sha256"] != right[name]["sha256"]
    )

    hard = [name for name in only_a + only_b + changed if Path(name).name not in VOLATILE_NAMES]
    soft = [name for name in only_a + only_b + changed if Path(name).name in VOLATILE_NAMES]

    print(f"a: {a['fileCount']} files, {a['totalBytes'] / 1024:.0f} KB")
    print(f"b: {b['fileCount']} files, {b['totalBytes'] / 1024:.0f} KB")
    if only_a:
        print(f"only in a ({len(only_a)}): {only_a[:10]}")
    if only_b:
        print(f"only in b ({len(only_b)}): {only_b[:10]}")
    if changed:
        print(f"changed content ({len(changed)}): {changed[:10]}")
    if soft:
        print(f"volatile-only differences (tolerated): {soft}")

    if hard:
        print(f"FAIL: {len(hard)} file(s) differ between the two builds")
        return 1
    print("OK: both builds produced the same files")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path, help="build output directory to fingerprint")
    parser.add_argument("--out", type=Path, help="where to write the manifest")
    parser.add_argument("--compare", nargs=2, type=Path, metavar=("A", "B"))
    args = parser.parse_args()

    if args.compare:
        return compare(*args.compare)

    if not args.build or not args.out:
        parser.error("--build and --out are required unless --compare is used")
    if not args.build.is_dir():
        print(f"{args.build} is not a directory")
        return 2

    data = fingerprint(args.build.resolve())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{data['fileCount']} files, {data['totalBytes'] / 1024:.0f} KB -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
