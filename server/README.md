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
