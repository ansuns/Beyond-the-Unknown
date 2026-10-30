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


## VS-3 personal level runs (merged)

- `GET /api/v1/level/`: enabled level catalog; hidden levels are listed as locked until authoritative route gating is implemented.
- `POST /api/v1/level/enter`: requires Bearer JWT, `Idempotency-Key`, `level_id` and `entrance_id`. Creates one player-owned `CREATED` run, stores an idempotency record, releases the main-map membership/instance seat and evicts the in-process map socket.
- `POST /api/v1/level/start`: transitions the caller-owned run from `CREATED` to `RUNNING`; repeated start is idempotent.
- `POST /api/v1/level/abandon`: transitions a caller-owned `CREATED`/ `RUNNING` run to `ABANDONED`; repeated abandon is idempotent.
- At most one `CREATED` or `RUNNING` run may exist per player. The database partial unique index is the final concurrency guard.
- The five room catalog entries and hidden ending use stable IDs from GDD V0.2. Personal run lifecycle is implemented; spatial layout, art and exact mechanism instances remain configuration/content work.
- Settlement, score/discovery/reward writes and permanent progress were added in VS-5; they remain subject to configured objectives and content readiness.


## VS-4 authoritative laws and mechanisms (merged)

- `GET /api/v1/level/rules`: returns the caller's server-owned rule permissions and tuning status. The three default laws are provisioned at player login.
- `POST /api/v1/level/rule/cast`: authoritative rule validation and effect calculation. Requires an active player-owned run and `Idempotency-Key`.
- `POST /api/v1/level/rule/maintain` and `POST /api/v1/level/rule/stop`: maintain or stop the caller's continuous Gaze effect.
- `GET /api/v1/level/state/{run_id}`: reads caller-owned mechanism states and lazily expires timed/lease-based effects.
- The first three preset combos are catalogued exactly as COMBO-001..003; matching checks target identity, order sensitivity and configured time window.
- Mechanism states are stored by `(run_id, player_id, mechanism_config_id)`; rule cooldowns and active effects are isolated by `(run_id, player_id, rule_id)`.
- GDD V0.2 leaves cooldowns, effect radii, timed durations, gaze lease and combo time windows pending. The migration deliberately stores these values as NULL and marks the catalog `TUNING_REQUIRED`; rule casting returns HTTP 503 until reviewed tuning values and actual mechanism positions are supplied. No unapproved gameplay numbers are hardcoded.


## VS-5 discovery, settlement and permanent progress (merged; content tuning pending)

- `POST /api/v1/level/settle`: accepts only the caller's run ID and idempotency key. The server verifies every configured required objective against personal mechanism state, computes completion time and writes one settlement. Client score/status fields are ignored.
- `GET /api/v1/player/progress`: latest versioned permanent snapshot; discoveries, collections, rewards and completed levels survive run exit.
- `GET /api/v1/player/discoveries`, `GET /api/v1/player/collections`: personal codex.
- `GET /api/v1/world/archive`: atomic server-owned first-discovery records. The world-first record grants no leaderboard score.
- `GET /api/v1/reward`, `POST /api/v1/reward/claim`: AUTO/CLAIM reward inbox; claim is player-owned and idempotent.
- `GET /api/v1/leaderboard`: EXPLORE/CLEAR/COLLECT × WEEKLY/MONTHLY, backed by immutable `score_events` and refreshable snapshots.
- Hidden route `HIDDEN-ROUTE-01` requires all five normal levels completed and COMBO-001 → COMBO-002 → COMBO-003 on LV-ROOM-05 before LV-HIDDEN-01 is unlocked.
- Weekly periods begin Monday 00:00 and monthly periods on day 1 at 00:00 in `SERVER_TIMEZONE` (default UTC); timestamps are stored in UTC.
- Score weights remain NULL/`TUNING_REQUIRED` until approved. No score events or leaderboard entries are fabricated while weights are unset. Reward definitions/conditions are empty until approved content is supplied.
- Objective rows for ROOM-01 exit interaction and the hidden ending remain `CONTENT_PENDING`; those levels cannot be settled until their interaction/ending content is implemented. Spatial positions and law/combination tuning also remain separate content inputs.


VS-5 was merged into `main` after the Python/Ruff, PostgreSQL migration/integration, and Docker Compose smoke jobs passed. This confirms the backend contract and tested flows only; production score weights, reward definitions, room objectives, mechanism positions, and law tuning remain content/configuration gates.


## VS-6A season settlement and transactional outbox

- Worker scheduler ensures the current weekly/monthly season rows exist and enqueues one `season.finalize` outbox record when an ACTIVE period reaches its end boundary.
- The outbox relay publishes persistent versioned task envelopes to RabbitMQ and marks records PUBLISHED only after publisher confirmation. A publish/DB commit race can create duplicate messages; `worker_task_receipts` makes processing idempotent.
- The worker finalizes all three board snapshots, changes the season to SETTLING/REVIEW, and schedules `season.auto_approve` for `SEASON_REVIEW_WINDOW_SECONDS` later.
- Automatic approval runs only after the review deadline. A protected `POST /api/v1/internal/seasons/{season_id}/review` accepts APPROVE/REJECT decisions through `X-Internal-API-Key`; the key is not exposed to the client.
- Approved rank conditions use `reward_conditions.trigger_type='SEASON_RANK'` and `condition_config={season_type,board_type,rank_min,rank_max}`. Only non-paid appearance/title/pet/badge reward types are eligible. Grant keys and player/reward/source uniqueness prevent duplicate awards.
- Worker failures use bounded exponential retry (5 attempts) and the RabbitMQ dead-letter exchange/queue. Failed outbox records remain inspectable with `status=FAILED` and `last_error`.
- The API and worker receive the same `SERVER_TIMEZONE` and `SEASON_REVIEW_WINDOW_SECONDS`; database period/review timestamps remain UTC.
- This slice does not invent score weights or rank reward tiers. Until content config is marked READY, no season rank reward is granted.
