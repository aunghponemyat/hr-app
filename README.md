# HR Management & Attendance

The MVP follows [AGENTS.md](AGENTS.md) in phase order. Phases 1–5 are complete:
application scaffolding, the MySQL schema, reference seeding, authentication, and
first-admin bootstrap, authorization scope helpers, and employee/team/location
administration. Attendance, leave, and reports follow in Phases 6–8. Frontend authentication begins in Phase 9;
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

Replace `JWT_SECRET_KEY` in `backend/.env` with a random secret of at least 32
characters before signing in. An empty or example secret returns `503 AUTH_NOT_CONFIGURED`.
Real `.env` files are ignored by Git. Backend settings are cached
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
| `LOGIN_RATE_LIMIT_IP`, `LOGIN_RATE_LIMIT_EMPLOYEE`, `LOGIN_RATE_LIMIT_WINDOW_SECONDS` | Sign-in attempts per IP/employee over a sliding window |
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
idempotency, authentication, lockout/rate limiting, password changes, refresh
rotation/replay, bootstrap, concurrent ID allocation, and the authorization matrix
for every seeded role. Scope tests cover cross-team denial, filtered pagination
and counts, manager removal, current team membership, live role/grant changes,
target existence protection, and one permission query per request. Administration tests
cover HR/C-level setup, denial for every admin endpoint, immutable employee IDs,
membership and manager history, password reset revocation, reference-preserving
deletion, filtered lists, audit redaction, and concurrent employee creation and
last-admin changes. Database tests use real
MySQL and transaction/savepoint fixtures so
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

Migration `0001` creates all 15 business tables; `0002` adds hashed refresh sessions.
Tables use InnoDB/utf8mb4, unsigned identifiers, foreign keys, indexes, and CHECK
constraints. Timestamps use
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

## First admin

After migrations, run from `backend/`:

```bash
poetry run python -m scripts.create_admin --first-name Admin --last-name User --role hr
```

The password is prompted securely twice and never printed. It must contain letters
and digits and be 8–1024 characters long. `ADMIN_INITIAL_PASSWORD` or `--password`
can supply it instead; the argument takes precedence. The script seeds reference
data, generates the employee ID under a database lock, and prints only
`Admin created: <employee_id>`.

It refuses a second admin, including when an existing admin is inactive, unless
`--force` is passed. `--role c_level` selects the other admin role. An optional
`--employee-id` override is checked for duplicates and reserves matching generated
IDs so later creation does not collide. Running the script again leaves existing
employee records intact.

## Authentication API

The backend authentication flow is usable through HTTP clients and the development
OpenAPI UI; the React login/change-password pages are scheduled for Phase 9.

| Endpoint | Request | Result |
| --- | --- | --- |
| `POST /api/v1/auth/login` | OAuth2 form: `username` is Employee ID, `password` | Access token, bearer type, expiry, password-change flag; refresh cookie |
| `POST /api/v1/auth/refresh` | Refresh cookie | Fresh access token and rotated refresh cookie |
| `POST /api/v1/auth/change-password` | Bearer token and JSON `{current_password,new_password}` | Fresh tokens; old sessions/tokens revoked |
| `POST /api/v1/auth/logout` | Bearer token | Session revoked and refresh cookie cleared |
| `GET /api/v1/me` | Bearer token | Own profile, current role/permissions/team, password-change flag |
| `PATCH /api/v1/me` | Bearer token and JSON `{display_name}` | Update or clear own display name; other fields rejected |

The first login requires a password change. `/auth/*` and `GET /me` remain
available while it is required; protected business routes use
`require_password_changed` and return `403 PASSWORD_CHANGE_REQUIRED`. New passwords
must also differ from the current password. `GET /me` enforces `profile.read.self`.

Access tokens expire after 30 minutes by default. Refresh tokens expire after seven
days and use an httpOnly, SameSite=Strict cookie scoped to `/api/v1/auth`, with
Secure enabled in production. The database stores SHA-256 hashes of refresh tokens,
never their plaintext. Rotation replaces the hash under a row lock, so simultaneous
reuse accepts the old token at most once. Logout revokes the current session;
password changes revoke all prior sessions and invalidate previous password-state
claims. Every authenticated request reloads the employee and session from MySQL,
so deactivation takes effect immediately.

Five consecutive failed logins lock an account for 15 minutes by default. The
threshold attempt and later attempts during lockout return `429 ACCOUNT_LOCKED`.
An expired lockout starts a new failure count; successful login clears the count.
Separate per-process limits allow 30 attempts per IP and 10 per Employee ID per
60 seconds by default, returning `429 RATE_LIMITED` with `Retry-After`. Employee
keys are case-folded and hashed. This MVP limiter is local to each API process;
the database account lockout persists across restarts.

Auth mutations check browser Origin against configured CORS origins or the API's
own origin; cross-site requests are rejected. Command-line requests without Origin
are supported. Access tokens are intended for client memory, and auth/profile
responses use `Cache-Control: no-store`, as do all private API responses.

## Backend authorization

`app/deps/authz.py` exposes FastAPI dependencies and the scope helpers implemented
in `app/services/authorization_service.py`. A server-created `AuthorizationContext`
holds the authenticated employee, database session, and immutable permission
grants. Permission rows are loaded through `role_permissions` once per role per
request and cached on `request.state`; no permissions are cached across requests.
Authorization uses current database permission codes. Codes must match the stored
resource/action/scope fields; malformed grants are ignored. Role labels and JWT
role claims do not authorize access.

Use `Depends(require_permission(resource, action))` on a protected handler. It
authenticates the caller, enforces forced password change, and checks that at
least one scope is granted. The returned context is passed to service helpers:

- `has_permission` / `scopes_for` return the scopes for the resource/action pair.
- `authorize` checks a loaded target using self identity, active management of its
  current team, or an any-scope grant.
- `resolve_target_employee` combines target lookup with authorization. Self-only
  callers receive `403 OUT_OF_SCOPE` for both existing and missing foreign IDs;
  team/any callers may receive `404 NOT_FOUND` for a missing employee.
- `scoped_employee_ids_query` returns a SQL query for authorized employee IDs.
  Apply it before list pagination, counts, summaries, or exports. Team scope uses
  active `team_managers` rows and current `employees.team_id`, and includes the
  caller; self scope includes only the caller; any scope includes all employees.
- `is_admin` checks `employee.create.any`. It grants no unrelated actions.

`allowed_scopes` can narrow a dependency to team/any or any-only endpoints.
`GET /me` explicitly permits access while a password change is required and uses
this same permission loader. Generic scope queries preserve inactive employees
for history/reporting; dropdown/list services can add their required active filter.

Phase 4's authorization probes exist only under `/api/v1/authz/` in the test
app. Phase 5 provides the production team roster and administration endpoints;
attendance workflows follow in Phase 6.

## Administration API

Sign in as HR or C-level and complete the required password change. Use a bearer
token in the OpenAPI UI or an HTTP client; frontend admin pages arrive in Phase 10.
All administrative endpoints require the corresponding `any` permission in the
backend. Numeric employee references use the internal `id`, while the generated
business `employee_id` (such as `EMP0001`) is immutable and used for login.

| Endpoint | Purpose |
| --- | --- |
| `GET/POST /api/v1/admin/employees` | Search/filter employees or create an account with a default password |
| `GET/PATCH /api/v1/admin/employees/{id}` | Read or update names, role, team, position, department, activation |
| `POST /api/v1/admin/employees/{id}/reset-password` | Supply `{default_password}`; require change and revoke old sessions |
| `GET /api/v1/admin/utils/generate-password` | Generate a random 12-character default password |
| `GET /api/v1/admin/roles` | Read seeded roles and their permission codes |
| `GET/POST /api/v1/admin/teams` | List or create teams |
| `GET/PATCH/DELETE /api/v1/admin/teams/{id}` | Read, update, or delete an unused team |
| `GET/POST /api/v1/admin/teams/{id}/members` | List current members or assign/move an active employee with `{employee_id}` |
| `DELETE /api/v1/admin/teams/{id}/members/{employee_id}` | Clear current membership and close history |
| `GET/POST /api/v1/admin/teams/{id}/managers` | List current managers or assign an eligible active employee with `{employee_id}` |
| `DELETE /api/v1/admin/teams/{id}/managers/{employee_id}` | Close a manager assignment and immediately remove its scope |
| `GET/POST /api/v1/admin/teams/{id}/locations` | List or link locations with `{work_location_id}` |
| `DELETE /api/v1/admin/teams/{id}/locations/{location_id}` | Unlink a location |
| `GET/POST /api/v1/admin/work-locations` | List or create locations (latitude, longitude, radius 50–100 m) |
| `GET/PATCH/DELETE /api/v1/admin/work-locations/{id}` | Read, update, or delete an unreferenced location |
| `GET /api/v1/team/members` | Scoped manager roster, including self; HR/C-level see all employees |

Lists return `{items,total,page,page_size}` with default page size 25 and maximum
100. Employee filters are `search`, `team_id`, `role_id`, and `is_active`.
Search matches literal substrings in employee IDs and names. Administrative lists
retain inactive accounts; inactive employees cannot be assigned as members/managers.

For the setup acceptance flow, create a team and location, link the location,
create employees using IDs from `/admin/roles`, then assign the new reporting
manager through the team's `/managers` endpoint. After login and password change,
that manager can see the team's new employees through `/team/members`.
Creation returns the default password once, alongside the account. Reset returns
it once as `{default_password}`. Subsequent reads and audits omit all passwords
and hashes. Responses must be handled privately and are never cached by the API.

Team moves update current membership and close/open history in one transaction.
Repeated associations are no-ops; missing removals return 404. Deactivating a
manager or changing to a role without team/any attendance read permission closes
their active manager assignments; reactivation requires explicit reassignment.
The final active administrator is protected by `409 LAST_ADMIN`, including under
simultaneous changes. Admin status is defined by `employee.create.any`.
Administrative mutations serialize on the existing ID-sequence row before entity
locks, a deliberate MVP tradeoff that avoids a schema change.

Team deletion returns `409 TEAM_IN_USE` if any membership/manager history, current
member, or location link exists. Location deletion returns `409 LOCATION_IN_USE`
while linked to a team or referenced by attendance. History is preserved.
Successful deletes return a message. Mutations produce secret-free audit records.
Employee and manager timestamps are presented in the configured office timezone.
The roster's `today_status` shows stored attendance or `weekend`; missing attendance
on a working day returns null. Full attendance and leave derivation follow in
Phases 6–7.

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
