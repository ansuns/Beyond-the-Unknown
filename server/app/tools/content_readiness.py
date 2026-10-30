import asyncio
import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.config import get_settings
from app.core.database import engine


QUERIES: dict[str, str] = {
    "rule_tuning": """
        SELECT rule_id AS id, config_status,
               cooldown_ms, radius, duration_ms, lease_timeout_ms
        FROM rule_catalog
        WHERE is_enabled = true
          AND (
              config_status <> 'READY'
              OR cooldown_ms IS NULL
              OR radius IS NULL
              OR (duration_type = 'TIMED' AND duration_ms IS NULL)
              OR (duration_type = 'WHILE_CASTING' AND lease_timeout_ms IS NULL)
          )
        ORDER BY priority DESC, rule_id
    """,
    "mechanism_content": """
        SELECT level_id, mechanism_config_id AS id,
               config->>'config_status' AS config_status,
               position_x, position_y
        FROM level_mechanism_catalog
        WHERE is_enabled = true
          AND (
              position_x IS NULL
              OR position_y IS NULL
              OR COALESCE(config->>'config_status', '') <> 'READY'
          )
        ORDER BY level_id, mechanism_config_id
    """,
    "combo_tuning": """
        SELECT combo_id AS id, config_status, time_window_ms
        FROM combo_catalog
        WHERE config_status <> 'READY' OR time_window_ms IS NULL
        ORDER BY combo_id
    """,
    "required_objectives": """
        SELECT level_id, objective_id AS id, mechanism_config_id, config_status
        FROM level_objectives
        WHERE is_required = true AND config_status <> 'READY'
        ORDER BY level_id, objective_id
    """,
    "discovery_content": """
        SELECT discovery_id AS id, config_status, score_reason
        FROM discovery_catalog
        WHERE is_enabled = true AND config_status <> 'READY'
        ORDER BY discovery_id
    """,
    "hidden_routes": """
        SELECT hidden_route_id AS id, is_enabled, config_status
        FROM hidden_routes
        WHERE is_enabled = false OR config_status <> 'READY'
        ORDER BY hidden_route_id
    """,
    "score_weights": """
        SELECT reason AS id, board_type::text AS board_type, delta, config_status
        FROM score_rule_config
        WHERE is_enabled = true
          AND (config_status <> 'READY' OR delta IS NULL)
        ORDER BY reason
    """,
    "reward_conditions": """
        SELECT condition_id AS id, trigger_type, config_status
        FROM reward_conditions
        WHERE is_enabled = true AND config_status <> 'READY'
        ORDER BY condition_id
    """,
}


async def build_content_readiness_report(connection: AsyncConnection) -> dict[str, Any]:
    blockers: dict[str, list[dict[str, Any]]] = {}
    for category, query in QUERIES.items():
        rows = (
            await connection.execute(text(query))
        ).mappings().all()
        blockers[category] = [dict(row) for row in rows]

    blocker_count = sum(len(items) for items in blockers.values())
    return {
        "status": "READY" if blocker_count == 0 else "BLOCKED",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "app_env": get_settings().app_env,
        "blocker_count": blocker_count,
        "categories": blockers,
    }


async def main() -> int:
    try:
        async with engine.connect() as connection:
            report = await build_content_readiness_report(connection)
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
        return 0 if report["status"] == "READY" else 2
    finally:
        await engine.dispose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
