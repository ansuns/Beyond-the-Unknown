# Python service (VS-1)

## Layout

```text
server/
├── app/
│   ├── api/                 # API composition and versioned router
│   ├── core/                # settings, DB session, authentication and security
│   ├── modules/
│   │   ├── auth/            # WeChat code exchange, login orchestration and persistence
│   │   ├── players/         # Player profile and player-facing API
│   │   └── characters/      # Character catalog and ownership rules
│   ├── realtime/            # WebSocket auth, connection manager and broadcasts
│   ├── schemas/             # Shared response envelopes
│   ├── workers/             # RabbitMQ consumers
│   └── main.py              # FastAPI composition root
├── migrations/              # Alembic history
├── schema/                  # Initial SQL snapshot for migration 0001
└── tests/{unit,integration}/
```

## Local development

Requires Docker Compose and Python 3.12+ with uv.

1. Copy `.env.example` to `.env` inside this directory.
2. Configure WeChat Mini Program `WECHAT_APP_ID` and `WECHAT_APP_SECRET` for real login.
3. Replace JWT and OpenID HMAC secrets with separate random values (at least 32 characters) outside local development.
4. From repository root, run `docker compose --env-file server/.env up --build -d`, then apply migrations with `docker compose --env-file server/.env run --rm api uv run --no-sync alembic -c alembic.ini upgrade head`.

- API liveness: http://localhost:8000/health/live
- API readiness: http://localhost:8000/health/ready
- OpenAPI: http://localhost:8000/docs
- RabbitMQ management: http://localhost:15672 (local credentials: beyond / beyond_dev_only)

Run tests locally after starting PostgreSQL and applying migrations:

```bash
uv sync --group dev
TEST_DATABASE_URL=postgresql+asyncpg://beyond:beyond_dev_only@localhost:5432/beyond DATABASE_URL=postgresql+asyncpg://beyond:beyond_dev_only@localhost:5432/beyond uv run pytest
uv run ruff check .
```

Integration tests use a fake WeChat provider. The production adapter calls WeChat `jscode2session`; `session_key` is neither returned nor persisted. The existing unique `wx_openid` column stores a keyed HMAC digest, not raw OpenID. Character display names and art asset IDs are placeholders until approved content/art direction is supplied.

## VS-1 endpoints

- `POST /api/v1/auth/login`: exchange a WeChat login code and create/resume the player.
- `GET /api/v1/player/me`: retrieve the authenticated player's profile.
- `GET /api/v1/player/characters`: list the player's unlocked characters.
- `PUT /api/v1/player/character`: select an owned and enabled character.

All player endpoints require a Bearer JWT. The API derives player identity from the token subject; callers must not submit a player ID.

## VS-2 shared-map endpoints

- `POST /api/v1/map/enter`: allocate or resume the player's main-map instance and return a membership session ID.
- `WS /api/v1/ws/map`: authenticate with an `AUTH` first message, then send `ENTER` or `RECONNECT`.
- Supported client messages: `MOVE_SYNC`, `ACTION_BROADCAST`, `PING`, `LEAVE`.
- Supported server events: `AUTH_OK`, `ENTER` snapshot/event, `MOVE_SYNC`, `ACTION_BROADCAST`, `PONG`, `LEAVE`, `ERROR`.

The current WebSocket connection manager is single-process/in-memory. It is a vertical-slice implementation for local integration and must be replaced by a Redis-backed presence/pub-sub adapter before horizontal scaling. AOI currently uses same-instance visibility as a fallback; radius/grid parameters remain pending GDD tuning. Spawn positions, 160 logical-units/second movement speed, 10 Hz movement cap, 5 actions per 10 seconds, 60-second reconnect grace and 20-player instance capacity are prototype configuration values, not production-certified limits.

The map instance capacity and movement/reconnect limits are configurable through the `MAP_*` environment variables. The current 20-player value is a test target only; production capacity must be established by load testing.


## VS-3 personal level runs (in review)

- `GET /api/v1/level/`: enabled level catalog; hidden levels are listed as locked until authoritative route gating is implemented.
- `POST /api/v1/level/enter`: requires Bearer JWT, `Idempotency-Key`, `level_id` and `entrance_id`. Creates one player-owned `CREATED` run, stores an idempotency record, releases the main-map membership/instance seat and evicts the in-process map socket.
- `POST /api/v1/level/start`: transitions the caller-owned run from `CREATED` to `RUNNING`; repeated start is idempotent.
- `POST /api/v1/level/abandon`: transitions a caller-owned `CREATED`/ `RUNNING` run to `ABANDONED`; repeated abandon is idempotent.
- At most one `CREATED` or `RUNNING` run may exist per player. The database partial unique index is the final concurrency guard.
- The five room catalog entries and the hidden ending use stable IDs from GDD V0.2. Spatial layout, art, exact mechanism instances and hidden-route unlock conditions remain configuration/content work.
- Settlement, score/discovery/reward writes and permanent progress are not implemented in VS-3; they belong to the later authoritative gameplay/settlement slices.


## VS-4 authoritative laws and mechanisms (in review)

- `GET /api/v1/level/rules`: returns the caller's server-owned rule permissions and tuning status. The three default laws are provisioned at player login.
- `POST /api/v1/level/rule/cast`: authoritative rule validation and effect calculation. Requires an active player-owned run and `Idempotency-Key`.
- `POST /api/v1/level/rule/maintain` and `POST /api/v1/level/rule/stop`: maintain or stop the caller's continuous Gaze effect.
- `GET /api/v1/level/state/{run_id}`: reads caller-owned mechanism states and lazily expires timed/lease-based effects.
- The first three preset combos are catalogued exactly as COMBO-001..003; matching checks target identity, order sensitivity and configured time window.
- Mechanism states are stored by `(run_id, player_id, mechanism_config_id)`; rule cooldowns and active effects are isolated by `(run_id, player_id, rule_id)`.
- GDD V0.2 leaves cooldowns, effect radii, timed durations, gaze lease and combo time windows pending. The migration deliberately stores these values as NULL and marks the catalog `TUNING_REQUIRED`; rule casting returns HTTP 503 until reviewed tuning values and actual mechanism positions are supplied. No unapproved gameplay numbers are hardcoded.
