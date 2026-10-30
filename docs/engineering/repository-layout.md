# Repository directory and module boundaries

- Version: 1.0
- Date: 2026-10-30
- Status: current repository baseline

## 1. Top-level layout

```text
Beyond-the-Unknown/
├── client/                         # Cocos Creator 3.x + TypeScript client
│   └── README.md
├── server/                         # Python 3.12+ backend
│   ├── app/
│   │   ├── api/                    # API composition and version routing
│   │   ├── core/                   # settings, DB session, auth and security
│   │   ├── modules/                # modular-monolith business domains
│   │   │   ├── auth/
│   │   │   ├── players/
│   │   │   ├── characters/
│   │   │   ├── maps/               # map instance and spawn allocation
│   │   │   ├── levels/             # add in VS-3
│   │   │   ├── rules/              # add in VS-4
│   │   │   ├── discoveries/        # add in VS-5
│   │   │   └── settlements/        # add in VS-5
│   │   ├── realtime/               # WebSocket auth, connection lifecycle and broadcasts
│   │   ├── schemas/                # shared envelope/error structures
│   │   ├── workers/                # RabbitMQ consumer entrypoints
│   │   └── main.py                 # FastAPI composition root
│   ├── migrations/                 # append-only Alembic history
│   ├── schema/                     # initial SQL snapshot used by migration 0001
│   └── tests/{unit,integration,contract}/
├── docs/
│   ├── gdd/                        # GDD overview and chapters
│   │   └── chapters/               # chapters 1–18
│   ├── reviews/                    # audit and revision reports
│   └── engineering/                # API, DB, level, realtime and delivery contracts
├── .github/workflows/              # CI automation
├── docker-compose.yml              # local dependencies and services
└── README.md                       # single repository entrypoint
```

## 2. Backend module responsibilities

| Directory | Put here | Keep out |
|---|---|---|
| `app/api` | router aggregation and version mounting | SQL and business rules |
| `app/core` | settings, database session, JWT, auth dependency, middleware | player/level-specific rules |
| `app/modules/<domain>` | domain router, schemas, service, repository, provider and errors | another domain's private repository |
| `app/schemas` | shared envelope, pagination and generic error shapes | domain DTOs |
| `app/workers` | RabbitMQ consumer startup and task registration | REST endpoints |
| `migrations` | versioned schema/data changes | edits to already released migration history |
| `tests` | unit, integration and contract tests | production runtime code |

## 3. Domain module convention

Create files only when a domain needs them; do not create empty future packages.

```text
modules/<domain>/
├── __init__.py
├── router.py          # HTTP adapter; validation and response mapping
├── schemas.py         # Pydantic request/response DTOs
├── service.py         # use cases, business rules and transaction boundaries
├── repository.py      # domain-owned SQL/persistence
├── models.py          # only when ORM mappings are needed
├── provider.py        # external platform adapters, if needed
└── errors.py          # expected domain errors, if needed
```

## 4. Dependency rules

1. Dependency direction: `api/router → domain service → domain repository`.
2. A domain must not import another domain's repository. Cross-domain calls go through public services or an application use case.
3. `core` never imports a business domain. Domains may use core infrastructure.
4. Routers do not assemble SQL or own multi-step transactions; services/use cases own transaction boundaries.
5. PostgreSQL is the source of business truth; Redis is a rebuildable cache/online-state layer.
6. RabbitMQ consumers use manual ACK, idempotency, bounded retries and DLQ; critical writes use Transactional Outbox.
7. All API routes are mounted through `app/api/router.py`; `main.py` remains the composition root.
8. New domains must add tests and update OpenAPI or message schemas in the same PR.

## 5. Initial SQL source of truth

- `server/schema/0001_initial_schema.sql` is the executable source consumed by Alembic 0001 and copied into the container with `COPY server/`.
- `docs/engineering/database/0001_initial_schema.sql` is the review/documentation mirror.
- Changes to the initial snapshot must update both copies; CI uses `cmp` to detect drift.
- Once a migration is shared, do not rewrite it. Add a new `server/migrations/versions/000N_*.py`.

## 6. Naming and configuration

- Python files/packages: snake_case; classes: PascalCase; constants: UPPER_SNAKE_CASE.
- Domain packages use clear names such as players, characters, maps, levels and discoveries.
- API version is mounted once at `/api/v1`.
- Secrets are injected through environment variables; local .env files are ignored by Git.
- Do not pre-create empty future domains. Add each module with the vertical slice that needs it.

## 7. Current implementation

- Established: api, core, modules/auth, modules/players, modules/characters, modules/maps, realtime, schemas and workers.
- VS-2 backend prototype: map allocation, player presence, WebSocket AUTH/ENTER/RECONNECT, MOVE_SYNC, ACTION_BROADCAST, PING/PONG and LEAVE.
- VS-3 adds levels and personal run/mechanism isolation.
- VS-4 adds rules and mechanisms.
- VS-5 adds discoveries, collections, settlements, leaderboards and rewards.
