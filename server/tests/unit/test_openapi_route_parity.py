"""Keep docs/engineering/api/openapi.yaml in step with the mounted routes.

The spec had drifted from the implementation: it advertised /collection,
/discovery and /season (no such routes) and omitted /level/position and
/level/mechanism/interact. It also declared two paths with the same
operationId, which is invalid OpenAPI.

This guard compares the served paths against the documented ones so the drift
cannot silently return. It reads the YAML with a regular expression instead of
adding a YAML dependency to the runtime image.
"""

import re
from pathlib import Path

from app.main import app

API_PREFIX = "/api/v1"
SPEC_PATH = Path(__file__).resolve().parents[3] / "docs" / "engineering" / "api" / "openapi.yaml"
_PATH_LINE = re.compile(r"^  (/\S*):\s*$")
_OPERATION_ID = re.compile(r"^\s+operationId:\s*(\S+)\s*$")


def _documented_paths() -> set[str]:
    paths = set()
    for line in SPEC_PATH.read_text(encoding="utf-8").splitlines():
        match = _PATH_LINE.match(line)
        if match:
            paths.add(match.group(1).rstrip("/") or "/")
    return paths


def _served_paths() -> set[str]:
    # FastAPI keeps included routers nested, so read the generated schema instead of
    # walking app.routes, which would only expose the top-level health endpoints.
    paths = set()
    for path in app.openapi()["paths"]:
        if path.startswith(API_PREFIX):
            path = path[len(API_PREFIX) :]
        elif path.startswith("/health"):
            continue
        paths.add(path.rstrip("/") or "/")
    return paths


def _documented_operation_ids() -> list[str]:
    return _OPERATION_ID.findall(SPEC_PATH.read_text(encoding="utf-8"))


def test_openapi_paths_match_served_routes() -> None:
    documented = _documented_paths()
    served = _served_paths()
    assert documented, "no paths parsed from openapi.yaml"
    assert served - documented == set(), f"served but undocumented: {sorted(served - documented)}"
    assert documented - served == set(), f"documented but not served: {sorted(documented - served)}"


def test_openapi_operation_ids_are_unique() -> None:
    operation_ids = _documented_operation_ids()
    duplicates = {value for value in operation_ids if operation_ids.count(value) > 1}
    assert duplicates == set(), f"duplicate operationId values: {sorted(duplicates)}"
