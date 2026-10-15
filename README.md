# HR Management & Attendance

The MVP follows [AGENTS.md](AGENTS.md) in phase order. Phases 1–8 are complete:
application scaffolding, the MySQL schema, reference seeding, authentication, and
first-admin bootstrap, authorization scope helpers, and employee/team/location
administration, attendance with GPS verification and scoped dashboards, and leave
management with attendance integration, and streamed CSV reports. Frontend authentication begins in Phase 9;
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
last-admin changes. Attendance tests cover remote/onsite actions, geodesic
boundaries, GPS failure rollback, concurrent clock actions, server/local dates,
overnight rejection, half-day thresholds, scoped reads and pagination, date ranges,
derived absence/weekend/future statuses, and audited manual corrections. Leave tests
cover active options and eligible managers, duration/reason/backdate validation,
working-day calculations, overlaps and opposite halves, scoped reads/decisions,
self-decision denial, cancellation, live manager eligibility, audit records,
calendar/table/roster/summary overlays, and concurrent submissions and state changes.
Report tests cover self/admin export permissions, range caps and history limits,
current team/employee filters, inactive employees, exact column order, BOM/Unicode,
CSV quoting and injection escaping, GPS/decision fields, lazy batched generation,
database dependency lifetime, and CSV response documentation.
Database tests use real
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
attendance workflows are available through the Phase 6 endpoints below.

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
on a working day returns null. Calendar absence/weekend/future statuses are derived
by the attendance APIs, with approved leave overlaid by Phase 7.

## Attendance API

All routes require a bearer token and a completed password change. Backend
authorization uses current permission grants and current team scope. Frontend
clock confirmation, geolocation capture, and calendar UI arrive in Phase 10.

| Endpoint | Request/result |
| --- | --- |
| `GET /api/v1/attendance/today` | Own row or null, office-local date, and `next_action`: `clock_in`, `clock_out`, or `none` |
| `POST /api/v1/attendance/clock-in` | `{work_mode,latitude?,longitude?,accuracy_m?}`; attendance record plus confirmation message |
| `POST /api/v1/attendance/clock-out` | Same body; the existing row determines the mode, regardless of the request's selection |
| `GET /api/v1/attendance/calendar` | Calendar entries, summary, available years; optional internal `employee_id`, default self |
| `GET /api/v1/attendance` | Paginated daily rows in effective self/team/any scope; optional internal `employee_id` |
| `GET /api/v1/team/attendance` | Paginated scoped employee identities and per-member range summaries; team/any read permission |
| `PATCH /api/v1/attendance/{id}` | Existing row correction: `status`, `clock_in`, `clock_out`; mandatory `reason`; team/any update permission |

Read periods use `view=week|month|year|custom` and optional `anchor=YYYY-MM-DD`.
Default is the current month. Custom periods use `from` and `to`; supplying both
implies custom view. Week starts Monday. Bounds are inclusive and capped at
`MAX_REPORT_RANGE_DAYS` (default 366). Callers without `attendance.read.any` have
a one-calendar-year lookback. Partially available periods are clipped to that
boundary, and wholly older periods return `422 HISTORY_LIMIT`; requested spans
above the cap return `422 RANGE_TOO_LARGE`. Responses show effective bounds.
Available years reflect visible attendance data, falling back to the current year
when no data exists.

The calendar includes every date. Earlier working days without attendance show
`absent`; non-working days show `weekend`; future dates show `upcoming`. Recorded
attendance takes precedence on a worked weekend. A current working day without
attendance has null status so the ongoing day is not marked absent. Summaries
count present, half-day, absent, and leave days, plus completed worked hours.
Approved leave overrides status on working dates, including future dates. A full
day shows `leave`; one approved half shows `half-day`; opposite approved halves
together show `leave`. `leave` holds the first request by ID, and `leaves` preserves
all approved requests for that date. Weekends between leave dates are excluded.
Times and worked hours remain visible; attendance rows and clock permissions are
unchanged. Pending/rejected/cancelled requests have no display effect. Visible
approved leave also contributes available years. Tables include derived dates and order
by employee ID then date; personal dashboards should pass their own internal ID.
Counts and pagination apply only to authorized employees, including inactive
employees retained for history. Team summaries load attendance for the selected
page of employees together.

Remote clock actions ignore and clear coordinates. Onsite requires latitude,
longitude, and nonnegative GPS accuracy. Accuracy above the configured limit
returns `422 LOW_GPS_ACCURACY`; missing/invalid GPS returns `422 GPS_REQUIRED`;
no linked location returns `422 NO_WORK_LOCATION_CONFIGURED`. The nearest current
team-linked location determines the allowed perimeter. Geodesic distance is checked
before rounding, and an outside fix returns `403 OUTSIDE_WORK_PERIMETER` with
distance/radius details. Verification runs again for clock-out, while the row
retains its clock-in location. GPS evidence is stored with the attendance record;
warnings omit names and coordinates. Failed verification leaves attendance unchanged.

Server time determines clock timestamps and the office-local attendance date.
Client timestamps and verification flags are rejected. Simultaneous actions lock
the employee before attendance; only one clock-in/out succeeds. Duplicates return
409. Clock-out requires today's clock-in; previous-day open rows remain open because
overnight shifts are excluded. Worked time below `HALF_DAY_THRESHOLD_HOURS` results
in `half-day`; an exact-threshold interval remains `present`.

Manual correction requires a nonblank reason up to 500 characters. Offset-aware
times must stay on the attendance date, be no later than server time, and satisfy
clock-out >= clock-in. Clear both times together when clearing clock-in on a
completed record. Changing a time clears that action's GPS evidence; clearing
clock-in also clears the location. Status remains explicitly controlled by the
correction. The response uses office-local timestamps; `updated_by` and a
before/after audit with reason are written in the same transaction. No schema
migration is needed for Phases 6–8.

## Leave API

All endpoints require authentication and a completed password change. Options and
creation use `leave.create.self`; reads use current self/team/any leave scope;
decisions use team/any leave-decision scope. Frontend forms and approval dialogs
arrive in Phase 10.

| Endpoint | Request/result |
| --- | --- |
| `GET /api/v1/leave/options` | Active types/reasons, eligible manager identities, office-local today, weekdays, request/backdate limits |
| `POST /api/v1/leave-requests` | Create a pending request; server computes the end date |
| `GET /api/v1/leave-requests` | Paginated own requests; optional `status` filter |
| `GET /api/v1/leave-requests/team` | Paginated requests in team/any scope; optional `status` and internal `employee_id` filters |
| `GET /api/v1/leave-requests/{id}` | Scoped request detail, including current employee/manager names and decision |
| `POST /api/v1/leave-requests/{id}/approve` | Optional `{decision_note}`; selected current manager or any-scope decider |
| `POST /api/v1/leave-requests/{id}/reject` | Same authorization and optional body as approval |
| `POST /api/v1/leave-requests/{id}/cancel` | Requester only; pending, or approved with a future start date |

Creation fields are `leave_type_id`, `leave_reason_id`, `reason_text?`,
`duration_type`, `half_day_period?`, `num_days`, `start_date`,
`reporting_manager_id`, and `remark?`. Half-day requires morning/afternoon and
exactly 0.5 days; full-day requires an integer from 1 through the configured
maximum, without a half-day period. Text fields are capped at 500 characters.
Reasons with `requires_text` (seeded `other`) require nonblank reason text.
Ordinary reasons may include optional text. Inactive reference options are rejected.

The start date must be a configured working weekday and within the backdate
limit. End dates count working days including the start and skip all non-working
weekdays; `WORKING_WEEKDAYS` controls Saturday/Sunday behavior. Public holidays
and leave balances are outside the MVP. Submitted fields remain immutable;
cancellation and a new submission are the available correction flow.

Eligible managers are active managers of the requester's current team, excluding
the requester, who hold a valid team/any leave-decision grant. If none qualify,
use active any-scope deciders. No team uses the same fallback. Names prefer display
name. Submission revalidates eligibility. A team manager may read in-scope requests
but decide only those selecting them; any-scope deciders can decide another
employee's pending request regardless of selection. Nobody can decide their own
request. Role names and JWT role claims do not grant access.

Pending or approved date overlaps return `409 LEAVE_OVERLAP`, except opposite
halves of the same day. Nonpending decisions and invalid cancellations return
`409 INVALID_STATE`. Approved cancellation is allowed only before the start date;
pending cancellation is allowed even on/past that date. Cancellation keeps prior
decision history and requires requester ownership even for HR/C-level. It does
not require an invented cancellation permission. Rejected/cancelled requests
cannot be cancelled again. Decision/cancellation audit snapshots omit the original
reason and remark; ordinary responses retain them for authorized readers.

Writes lock referenced employees in ascending ID order before request rows.
Overlap checks use locking reads after the requester lock, and concurrent
decisions/cancellations serialize on that requester. Deadlocks/lock timeouts roll
back and return `409 LEAVE_CONFLICT`. Lists filter scope before counts and
pagination, order newest first, and retain request history. Self-only readers get
403 for missing/foreign request IDs; team/any readers may get 404 for missing IDs.

## CSV reports

Exports require authentication and a completed password change. The response is
`text/csv; charset=utf-8` with a UTF-8 BOM for Excel, CRLF records, and a download
filename. All private responses use `Cache-Control: no-store`. Backend checks use
`report.export.self` / `report.export.any`; other read/admin grants are not extra
requirements. Frontend download panels arrive in Phase 10.

| Endpoint | Scope and filters |
| --- | --- |
| `GET /api/v1/attendance/export?from=&to=` | Always the caller's attendance; both dates required, including for HR/C-level |
| `GET /api/v1/admin/reports/attendance.csv` | Any-scope export permission; optional date pair, `team_id`, `employee_id` |
| `GET /api/v1/admin/reports/leave.csv` | Same any-scope permission and optional filters |

Filter IDs are internal numeric IDs. Admin dates default to the current
office-local month when both are omitted; supplying just one date is invalid.
Bounds are inclusive and limited to `MAX_REPORT_RANGE_DAYS` (default 366).
Self-scope exports enforce the same calendar-year lookback and partial-range
clipping as the dashboard. Any-scope holders can export older history within the
same range cap. Filenames show effective bounds, for example
`attendance_EMP0001_2026-01-01_2026-03-31.csv`; admin files use `attendance_all` or
`leave_all`. Filename components are sanitized for safe download headers.

Attendance files contain one row per selected employee/date, including derived
absences, non-working/future days, and approved leave. They use the same display
rules as calendars and order by internal employee ID then date. Team filters use
current membership; inactive employees remain included. Leave files include all
statuses with request intervals overlapping the filter range, preserve original
dates/day counts, and order by request ID. Existing but incompatible filters
produce a header-only file; missing target IDs return a JSON 404 after authorization.
Self export rejects target/team filters and never expands to another employee.

Column order follows [AGENTS.md Section 10.7](AGENTS.md#107-csv-export). Names prefer
display name with first/last fallback; team names are current. Times include the
office offset, missing fields are empty, GPS flags are lowercase true/false, and
worked hours have two decimal places. Half-day duration includes morning/afternoon.
String cells starting with `=`, `+`, `-`, `@`, tab, or carriage return receive a
leading apostrophe; CSV quoting preserves commas, quotes, and embedded newlines.
No passwords, tokens, or extra profile fields are exported.

The server validates permissions/ranges/filters before streaming. It reads
attendance in batches of 25 employees and leave in batches of 100 requests, keeps
the request database session open through generation, and never assembles a whole
report in memory. Typed row models specify the columns and OpenAPI documents the
CSV body as a string. Empty reports retain the BOM and header.

Example download using an access token from login:

```bash
curl --fail --get 'http://localhost:8000/api/v1/attendance/export' \
  --header 'Authorization: Bearer <access-token>' \
  --data-urlencode 'from=2026-01-01' \
  --data-urlencode 'to=2026-03-31' \
  --output attendance.csv
```

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
