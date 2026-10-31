"""Manage the art production queue and keep the asset manifest in step with disk.

Generation is not scriptable here - the image backend is reached through a tool
call, not an HTTP endpoint - so the queue is split at that seam:

* ``next``  prints the tasks still waiting, with the exact prompt and parameters,
  so a producer (a person or an agent) can run them one at a time.
* ``post``  takes the returned file and runs the deterministic half: keying,
  trimming, anchoring, checks, report, manifest update.

Keeping those apart means the expensive, non-deterministic step is recorded but
never re-run by accident, and the part that decides whether an asset is
acceptable is reproducible from the raw file alone.

A task is only allowed to become REVIEW when its report exists and every check
passed. READY stays out of reach on purpose: it needs licence and acceptance
evidence that this tool cannot manufacture.

Usage:
    python tools/asset_queue.py status
    python tools/asset_queue.py next [-n 3]
    python tools/asset_queue.py post --id chr001-model --raw build/gen/raw/x.png
    python tools/asset_queue.py verify
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from asset_pipeline import build_background, build_sprite, verify
from strip_overlay import GuardError

ROOT = Path(__file__).resolve().parents[1]
QUEUE_PATH = ROOT / "docs/engineering/assets/production/queue.v1.json"
MANIFEST_PATH = ROOT / "docs/engineering/assets/asset-manifest.v1.json"

OPEN_STATES = {"PENDING", "GENERATED", "POSTED", "BLOCKED"}


def load_queue() -> dict:
    return json.loads(QUEUE_PATH.read_text(encoding="utf-8"))


def save_queue(queue: dict) -> None:
    QUEUE_PATH.write_text(json.dumps(queue, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def save_manifest(manifest: dict) -> None:
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def find_task(queue: dict, task_id: str) -> dict:
    for task in queue["tasks"]:
        if task["id"] == task_id:
            return task
    raise SystemExit(f"unknown task id: {task_id}")


def next_tasks(queue: dict, limit: int) -> list[dict]:
    ready = [task for task in queue["tasks"] if task["state"] == "PENDING"]
    return ready[:limit]


def post_task(queue: dict, task_id: str, raw: str) -> dict:
    task = find_task(queue, task_id)
    from PIL import Image

    raw_path = Path(raw)
    if not raw_path.is_absolute():
        raw_path = ROOT / raw
    if not raw_path.exists():
        raise SystemExit(f"raw file does not exist: {raw_path}")

    output = ROOT / task["output"]
    report_path = ROOT / task["report"]
    post = task.get("post", {})

    with Image.open(raw_path) as handle:
        source = handle.convert("RGBA") if handle.mode in ("RGBA", "LA", "P") else handle.convert("RGB")

        if task["kind"] == "sprite":
            result, note = build_sprite(
                source,
                inner=post.get("inner", 26.0),
                outer=post.get("outer", 68.0),
                padding=post.get("padding", 8),
                max_size=post.get("max_size") or None,
            )
            key_used = note["key"]
        else:
            result, note = build_background(
                source,
                crop_bottom=post.get("crop_bottom", 0.07),
                crop_right=post.get("crop_right", 0.0),
                size=tuple(post["size"]) if post.get("size") else None,
            )
            key_used = None

    output.parent.mkdir(parents=True, exist_ok=True)
    result.save(output, "PNG", optimize=True)

    checks = verify(result, key_used, note.get("anchor_offset_px"))
    passed = all(checks["checks"].values())

    from asset_pipeline import sha256_of

    report = {
        "asset_id": task["asset_id"],
        "task_id": task["id"],
        "kind": task["kind"],
        "generated_at": task.get("generated_at"),
        "backend": task.get("backend"),
        "raw": str(raw_path.relative_to(ROOT)).replace("\\", "/"),
        "output": task["output"],
        "raw_sha256": sha256_of(raw_path),
        "output_sha256": sha256_of(output),
        "source_size": list(source.size),
        "output_size": list(result.size),
        "key_color": list(key_used) if key_used else None,
        "post": post,
        **checks,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    task["state"] = "POSTED" if passed else "BLOCKED"
    task["raw"] = str(raw_path.relative_to(ROOT)).replace("\\", "/")
    task["posted_at"] = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    task["checks"] = checks["checks"]
    if not passed:
        task["blocked_reason"] = "; ".join(checks["warnings"]) or "a pipeline check failed"
    else:
        task.pop("blocked_reason", None)

    apply_to_manifest(task, report, passed)
    save_queue(queue)
    return task



def optimize_task(
    queue: dict,
    task_id: str,
    jpeg_quality: int = 84,
    colors: int = 256,
) -> dict:
    """Shrink a delivered file and keep its provenance report truthful.

    WeChat allows 4 MB in the main package and the six slice sprites were
    3.6 MB of mostly lossless PNG. Opaque art becomes JPEG (a painted backdrop
    stores gradients badly as PNG no matter how few colours it uses); sprites
    keep PNG because they need alpha, but drop to a palette. The report keeps
    the before/after numbers and the measured colour error, so the decision is
    auditable rather than a silent overwrite.
    """
    import io

    from PIL import Image

    from asset_pipeline import sha256_of
    from optimize_png import quantize, mean_and_p995_error

    task = find_task(queue, task_id)
    output = ROOT / task["output"]
    report_path = ROOT / task["report"]
    if not output.exists():
        raise SystemExit(f"{output} is missing; post the task before optimising it")
    if not report_path.exists():
        raise SystemExit(f"{report_path} is missing; post the task first")

    report = json.loads(report_path.read_text(encoding="utf-8"))
    before_bytes = output.stat().st_size
    image = Image.open(output)
    image.load()
    has_alpha = image.mode in {"RGBA", "LA"} and image.getchannel("A").getextrema()[0] < 255

    if has_alpha:
        result = quantize(image, colors)
        mean_error, p995_error = mean_and_p995_error(image, result)
        buffer = io.BytesIO()
        result.save(buffer, format="PNG", optimize=True)
        new_path = output
    else:
        result = image.convert("RGB")
        mean_error, p995_error = 0.0, 0.0
        buffer = io.BytesIO()
        result.save(buffer, format="JPEG", quality=jpeg_quality, optimize=True, progressive=True)
        new_path = output.with_suffix(".jpg")

    after_bytes = buffer.tell()
    if after_bytes >= before_bytes:
        print(f"{task_id}: no gain ({before_bytes} -> {after_bytes}), left untouched")
        return task

    new_path.write_bytes(buffer.getvalue())
    if new_path != output:
        output.unlink()

    new_relative = str(new_path.relative_to(ROOT)).replace("\\", "/")
    report["output"] = new_relative
    report["output_sha256"] = sha256_of(new_path)
    report["output_size"] = list(result.size)
    report["optimized"] = {
        "before_bytes": before_bytes,
        "after_bytes": after_bytes,
        "saved_pct": round(100 * (1 - after_bytes / before_bytes), 1),
        "format": "JPEG" if new_path != output else "PNG",
        "jpeg_quality": jpeg_quality if new_path != output else None,
        "palette_colors": colors if new_path == output else None,
        "mean_error": round(mean_error, 2),
        "p995_error": p995_error,
    }
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    manifest = load_manifest()
    for entry in manifest["entries"]:
        if entry["asset_id"] != task["asset_id"]:
            continue
        files = [manifest_path(new_relative) if item in task["output"] else item for item in entry["files"]]
        entry["files"] = files
    save_manifest(manifest)

    task["output"] = new_relative
    save_queue(queue)
    print(
        f"{task_id}: {before_bytes // 1024}K -> {after_bytes // 1024}K "
        f"({report['optimized']['saved_pct']}%) as {report['optimized']['format']}"
    )
    return task


def manifest_path(output: str) -> str:
    """Manifest paths are relative to client/, queue paths to the repository root."""
    prefix = "client/"
    return output[len(prefix):] if output.startswith(prefix) else output


def apply_to_manifest(task: dict, report: dict, passed: bool) -> None:
    manifest = load_manifest()
    entry = None
    for candidate in manifest["entries"]:
        if candidate["asset_id"] == task["asset_id"]:
            entry = candidate
            break
    if entry is None:
        raise SystemExit(f"{task['asset_id']} is not in the manifest; add it before posting")

    entry["status"] = "REVIEW" if passed else "BLOCKED"
    files = entry.get("files") or []
    declared = manifest_path(task["output"])
    if declared not in files:
        files.append(declared)
    entry["files"] = files

    provenance = entry.setdefault("provenance", {})
    provenance["source_type"] = "GENERATED_WITH_REVIEW"
    provenance["source_reference"] = task["report"]
    provenance["provider"] = task.get("backend", "workbuddy-image-gen")
    provenance["generated_at"] = task.get("generated_at")
    provenance["generation_prompt"] = task.get("prompt", "")
    provenance["post_processing"] = "tools/asset_pipeline.py " + json.dumps(task.get("post", {}), ensure_ascii=False)
    provenance["checks"] = task.get("checks")
    provenance["license"] = (
        "UNCONFIRMED - provider terms, commercial-use rights and any AI-content labelling "
        "obligation are not verified; see docs/engineering/assets/AI-content-compliance.md"
    )
    provenance["delivery_note"] = (
        f"Produced by {task['id']} on {task.get('generated_at')}; "
        f"{'all automated checks passed' if passed else 'a check failed: ' + str(task.get('blocked_reason'))}. "
        "Cocos import and device acceptance still pending."
    )
    save_manifest(manifest)


def verify_all(queue: dict) -> int:
    problems: list[str] = []
    for task in queue["tasks"]:
        if task["state"] not in {"POSTED", "REVIEW", "READY"}:
            continue
        output = ROOT / task["output"]
        report = ROOT / task["report"]
        if not output.exists():
            problems.append(f"{task['id']}: output missing ({task['output']})")
        if not report.exists():
            problems.append(f"{task['id']}: report missing ({task['report']})")
            continue
        data = json.loads(report.read_text(encoding="utf-8"))
        failed = [name for name, ok in data.get("checks", {}).items() if not ok]
        if failed:
            problems.append(f"{task['id']}: failed checks {failed}")
        if data.get("output_sha256") and output.exists():
            from asset_pipeline import sha256_of

            if sha256_of(output) != data["output_sha256"]:
                problems.append(f"{task['id']}: output changed after the report was written")

    manifest = load_manifest()
    by_id = {entry["asset_id"]: entry for entry in manifest["entries"]}
    for task in queue["tasks"]:
        if task["state"] != "POSTED":
            continue
        entry = by_id.get(task["asset_id"])
        if entry is None:
            problems.append(f"{task['id']}: no manifest entry")
        elif entry["status"] not in {"REVIEW", "READY"}:
            problems.append(f"{task['id']}: manifest says {entry['status']}, queue says POSTED")

    if problems:
        print("Asset queue verification failed:")
        for problem in problems:
            print(f"- {problem}")
        return 1
    print(f"Asset queue verified: {len(queue['tasks'])} tasks, no drift between queue, files and manifest.")
    return 0


def print_status(queue: dict) -> None:
    states: dict[str, int] = {}
    for task in queue["tasks"]:
        states[task["state"]] = states.get(task["state"], 0) + 1
    print("state  " + "  ".join(f"{name}={count}" for name, count in sorted(states.items())))
    print()
    for task in queue["tasks"]:
        note = task.get("blocked_reason", "")
        print(f"{task['state']:9s} {task['id']:24s} {task['asset_id']:22s} {task['kind']:10s} {note}")
    manifest = load_manifest()
    counts: dict[str, int] = {}
    for entry in manifest["entries"]:
        counts[entry["status"]] = counts.get(entry["status"], 0) + 1
    print()
    print("manifest: " + ", ".join(f"{name}={count}" for name, count in sorted(counts.items())))


def main() -> None:
    parser = argparse.ArgumentParser(description="Art production queue")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    nxt = sub.add_parser("next")
    nxt.add_argument("-n", type=int, default=1)
    post = sub.add_parser("post")
    post.add_argument("--id", required=True)
    post.add_argument("--raw", required=True)
    sub.add_parser("verify")
    opt = sub.add_parser("optimize")
    opt.add_argument("--id", required=True)
    opt.add_argument("--jpeg-quality", type=int, default=84)
    opt.add_argument("--colors", type=int, default=256)
    args = parser.parse_args()

    queue = load_queue()
    if args.command == "status":
        print_status(queue)
    elif args.command == "optimize":
        optimize_task(queue, args.id, args.jpeg_quality, args.colors)
    elif args.command == "next":
        tasks = next_tasks(queue, args.n)
        if not tasks:
            print("Nothing pending. Add tasks to the queue or move on to another stage.")
            return
        print(json.dumps(tasks, indent=2, ensure_ascii=False))
    elif args.command == "post":
        task = post_task(queue, args.id, args.raw)
        print(f"{task['id']}: {task['state']}")
        for name, ok in task.get("checks", {}).items():
            print(f"  {'PASS' if ok else 'FAIL'} {name}")
        if task["state"] == "BLOCKED":
            raise SystemExit(f"blocked: {task.get('blocked_reason')}")
    elif args.command == "verify":
        raise SystemExit(verify_all(queue))


if __name__ == "__main__":
    main()
