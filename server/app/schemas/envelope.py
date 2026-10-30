from typing import Any


def success_envelope(data: dict[str, Any], request_id: str) -> dict[str, Any]:
    return {"code": 0, "message": "ok", "data": data, "request_id": request_id}
