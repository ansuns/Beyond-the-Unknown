# Python service (VS-0)

## Local development

Requires Docker Compose and Python 3.12+ with uv.

```bash
cp server/.env.example server/.env
docker compose up --build
```

- API liveness: http://localhost:8000/health/live
- API readiness (PostgreSQL connectivity): http://localhost:8000/health/ready
- RabbitMQ management: http://localhost:15672 (local credentials: beyond / beyond_dev_only)

Apply the reviewed initial PostgreSQL schema:

```bash
docker compose run --rm api uv run --no-sync alembic -c alembic.ini upgrade head
```

Run unit tests locally from this directory:

```bash
uv sync --group dev
uv run pytest
uv run ruff check .
```

VS-0 worker intentionally handles only `worker.ping`; gameplay task handlers, retry topology,
outbox publisher, auth, and business APIs are added in their respective vertical-slice steps.
Local compose credentials are for development only and must never be reused in deployed environments.
