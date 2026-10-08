# HR Management & Attendance

The MVP follows [AGENTS.md](AGENTS.md) in phase order. Phases 1 and 2 are complete:
application scaffolding, the MySQL schema, Alembic migrations, and reference seeding.
Authentication, attendance, leave, and admin workflows follow in Phases 3–10;
the current frontend is an application shell.

## Requirements

- Python 3.10 or later and Poetry 1.8 or later
- Node.js 22.12 or later and npm
- Docker with the Compose plugin (MySQL 8.0)

## Local setup

From the repository root:

```bash
cp .env.example backend/.env
cp frontend/.env.example frontend/.env
make install
make db-up
make migrate
make seed-reference
```

Replace `JWT_SECRET_KEY` in `backend/.env` with a random secret before enabling
authentication. Real `.env` files are ignored by Git. Backend settings are cached
with `get_settings()` and read `.env` relative to the backend working directory.

Run each application in a separate terminal:

```bash
make dev-backend
make dev-frontend
```

Frontend: <http://localhost:5173>. API liveness: <http://localhost:8000/healthz>.
OpenAPI: <http://localhost:8000/docs>. The health check returns `{"status":"ok"}`
without requiring a running database. Business routes will use `/api/v1`.

Poetry manages backend dependencies and `backend/poetry.lock` records resolved
versions. Alternatively, from `backend/`, `pip install -e '.[dev]'` installs the
same declared dependencies, including development tools.

## Configuration

The commented [environment example](.env.example) contains all MVP settings.

| Variables | Purpose |
| --- | --- |
| `DATABASE_URL`, `TEST_DATABASE_URL` | PyMySQL URLs for separate development/test MySQL databases |
| `JWT_SECRET_KEY`, `JWT_ALGORITHM` | Token signing configuration (HS256) |
| `ACCESS_TOKEN_EXPIRE_MINUTES`, `REFRESH_TOKEN_EXPIRE_DAYS` | Token lifetimes |
| `COOKIE_SECURE` | Require HTTPS for refresh cookies in production |
| `MAX_FAILED_LOGINS`, `LOCKOUT_MINUTES` | Account lockout policy |
| `APP_ENV` | `development`, `test`, or `production`; production disables OpenAPI/docs |
| `APP_TIMEZONE`, `WORKING_WEEKDAYS` | Office timezone and comma-separated weekday numbers (Monday = 0) |
| `HALF_DAY_THRESHOLD_HOURS`, `MAX_GPS_ACCURACY_M` | Attendance/GPS thresholds |
| `MAX_REPORT_RANGE_DAYS` | Query/export cap, at most 366 days |
| `LEAVE_MAX_DAYS_PER_REQUEST`, `LEAVE_BACKDATE_DAYS` | Leave request limits |
| `EMPLOYEE_ID_PREFIX`, `EMPLOYEE_ID_PAD` | Immutable employee ID format |
| `CORS_ORIGINS` | Comma-separated explicit origins; no wildcard or URL paths |
| `VITE_API_BASE_URL` | Frontend API URL (`frontend/.env`) |

Production startup requires a JWT secret of at least 32 characters,
`COOKIE_SECURE=true`, and explicit HTTPS CORS origins. The MySQL connection hook
sets each session's timezone to UTC. Local Compose credentials are development
examples; use separate credentials and secrets for production.

## Checks

```bash
make test-db-up
make check
```

This runs backend Ruff lint/format checks, strict mypy, and pytest; frontend
ESLint, Prettier, strict TypeScript, Vitest/React Testing Library, and a production
build. `make format` applies the configured formatters. Individual check targets
are `make check-backend` and `make check-frontend`.

Tests cover public liveness, environment validation, production docs gating, CORS,
error redaction, migration upgrade/downgrade and model agreement, CHECK/unique/FK
constraints, timestamp defaults and UTC conversion, relationships, and seed
idempotency. Database tests use real MySQL and transaction/savepoint fixtures so
service commits cannot persist fixture data. Migrations are included in strict mypy checks.

It runs on loopback port 3307, uses `hr_app_test`, and stores data in temporary
container memory. The development database uses loopback port 3306 and a named
volume. `docker compose stop` stops services while preserving development data.
The migration round-trip test rebuilds the isolated test schema through Alembic.
`TEST_DATABASE_URL` must name a dedicated database ending in `_test`, with a name
different from the development database. Never point it at a database containing
data you need to retain.

## Migrations and reference data

Run from `backend/`, or use the root `make migrate` and `make seed-reference` targets:

```bash
poetry run alembic upgrade head
poetry run python -m scripts.seed_reference_data
poetry run alembic check
```

The initial migration creates all 15 business tables with InnoDB/utf8mb4,
unsigned identifiers, foreign keys, indexes, and CHECK constraints. Timestamps use
microsecond precision, are stored in UTC, and return as timezone-aware UTC values
from the ORM. Naive timestamp writes are rejected. `updated_at` changes in MySQL
when the row changes, including updates outside the ORM.

The seed is transactional and repeatable: five roles, 22 permissions, 60 grants,
seven leave types, six leave reasons, and the employee ID sequence. It reconciles
seeded role permissions, preserves an advanced sequence counter, and leaves
deactivated leave options inactive. There are no employees or passwords in the seed.

To add a schema change, update models on a feature branch, then generate and review
the migration against your development database:

```bash
poetry run alembic revision --autogenerate -m 'describe schema change'
poetry run alembic upgrade head
poetry run alembic check
```

All schema changes must go through Alembic. For an isolated disposable database,
`poetry run alembic downgrade base` removes the app tables; `upgrade head` recreates
them. The downgrade is destructive and is for disposable data only.

## First admin (Phase 3, upcoming)

Phase 3 will add the bootstrap command. Once implemented, run from `backend/`:

```bash
poetry run python -m scripts.create_admin --first-name Admin --last-name User --role hr
```

The bootstrap password will be prompted securely, never printed. The first login
requires a password change.

## Geolocation and security

Onsite clock actions require HTTPS in production or `localhost` during
development. Browser GPS can be spoofed; server-side accuracy and perimeter
checks plus audited manager/HR corrections are the MVP safeguards. Timestamps
come from the server and are stored in UTC, with office-local presentation.

## Branch workflow

Implement each phase on a retained feature branch. After its tests and acceptance
checks pass, commit the phase and merge into `develop`, then merge `develop` into
`main`. Never implement changes directly on either integration branch.

The existing `backend/scripts/deploy.sh` predates this app and targets another
project. It is not part of the HR application's setup or deployment workflow.
