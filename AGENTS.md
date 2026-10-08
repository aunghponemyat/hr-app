# AGENTS.md — HR Management & Attendance Web App (MVP)

> This file is the single source of truth for the coding agent. Read it fully before writing any code.
> Build in the order given in **Section 17 (Implementation Phases)**. After each phase, run the tests and verify the acceptance checks before moving on.

---

## 0. Rules for the Agent

1. **Follow this spec exactly.** If something is ambiguous, use the decision recorded in **Section 19 (Assumptions & Resolved Ambiguities)**. Do not silently invent behavior; if a new decision is needed, add it to that section.
2. **Authorization is enforced in the backend only.** The frontend hides UI for convenience, but every endpoint must enforce RBAC + contextual (scope) checks.
3. **Time and GPS verification are server-side.** Never trust a client-supplied timestamp. Never trust a client-supplied "verified" flag.
4. **Never store or log plaintext passwords or tokens.**
5. **Schema changes go through Alembic migrations.** No manual DDL.
6. **Every endpoint has a Pydantic request/response schema, and at least one happy-path and one authorization-failure test.**
7. Keep the code typed: Python type hints everywhere (`mypy`-clean where practical), strict TypeScript (`"strict": true`) on the frontend.
8. Keep modules small. Business logic lives in `services/`, not in routers.
9. Small, focused commits per phase/feature. (Git repo is already initiated in the root directory)
10. Currently, there are two branches: main and develop. develop is for each implementation phase upon completion. Then, it is merged to main without direct code changes. Any kind of code changes and refactoring must be done via separate feature branches. Do not remove these branches after a specific feature is implemented and integrated into the system.
10. Raise questions and ask for permissions/reviews if necessary.

---

## 1. Product Overview

A web-based HR system for attendance and leave management.

**Roles of scope (seeded):** `employee`, `senior_staff`, `reporting_manager`, `hr`, `c_level`.

**Core capabilities (MVP):**

- Login with **Employee ID + password** (JWT / OAuth2 password flow).
- Clock in / clock out as **onsite** (GPS-verified against office perimeter, 50–100 m) or **remote**.
- Confirmation dialog before each clock action; status message on the dashboard afterward.
- Leave Request section (separate from attendance): leave type, reason, number of days / half-day, calendar date, reporting manager, optional remark.
- Personal attendance dashboard (table + calendar), filters: week / month (default) / year, up to one year.
- Reporting managers see their own dashboard plus their team members' attendance and leave requests, and approve/reject leave.
- HR and C-level see and export everything.
- Profile management (display name, password). Employee ID is immutable.
- HR-only account creation (employee ID + default password), teams, roles, work locations.
- CSV export: employees export own attendance (selectable period up to one year); HR/C-level export all employee attendance and leave.
- First admin is created by an automated Python bootstrap script.

---

## 2. Tech Stack

| Layer | Choice |
|---|---|
| Backend | Python 3.10 or greater, FastAPI, Pydantic v2, pydantic-settings |
| ORM / migrations | SQLAlchemy 2.0 (typed `Mapped[]` style), Alembic |
| DB | MySQL 8.0.16+ (needed for enforced `CHECK` constraints), driver `PyMySQL` |
| Auth | OAuth2 password flow + JWT (`PyJWT`), password hashing with `pwdlib[argon2]` |
| GPS | `geopy` (`geopy.distance.geodesic`) |
| Frontend | React 18 + TypeScript (strict), Vite |
| Frontend libs | React Router, TanStack Query, Axios, react-hook-form + zod, Tailwind CSS, `react-day-picker` (date picking), `date-fns` |
| Tests | Backend: `pytest`, `httpx` TestClient, factory helpers. Frontend: `vitest` + React Testing Library |
| Tooling | `ruff`, `mypy`, ESLint, Prettier, Docker Compose (MySQL for local/dev/test) |

---

## 3. Repository Layout


```
hr-app/
├── AGENTS.md
├── docker-compose.yml              # mysql + (optional) backend/frontend
├── .env.example
├── backend/
│   ├── pyproject.toml
│   ├── alembic.ini
│   ├── alembic/versions/
│   ├── app/
│   │   ├── main.py                 # FastAPI app, CORS, routers, exception handlers
│   │   ├── core/
│   │   │   ├── config.py           # pydantic-settings
│   │   │   ├── security.py         # hashing, JWT create/verify
│   │   │   ├── database.py         # engine, SessionLocal, get_db
│   │   │   └── errors.py           # AppError + handlers (uniform error format)
│   │   ├── models/                 # SQLAlchemy models (one file per table group)
│   │   ├── schemas/                # Pydantic schemas
│   │   ├── deps/
│   │   │   ├── auth.py             # get_current_employee, require_password_changed
│   │   │   └── authz.py            # require_permission(), scope resolution
│   │   ├── services/
│   │   │   ├── auth_service.py
│   │   │   ├── employee_service.py
│   │   │   ├── team_service.py
│   │   │   ├── attendance_service.py
│   │   │   ├── gps_service.py
│   │   │   ├── leave_service.py
│   │   │   ├── report_service.py   # CSV export
│   │   │   └── id_service.py       # employee_id generation
│   │   ├── routers/                # auth, me, attendance, leave, team, admin
│   │   └── utils/time.py           # UTC/local conversions, working-day helpers
│   ├── scripts/
│   │   ├── seed_reference_data.py  # roles, permissions, role_permissions, leave types/reasons
│   │   └── create_admin.py         # first admin bootstrap
│   └── tests/
└── frontend/
    ├── package.json
    ├── vite.config.ts
    └── src/
        ├── api/                    # axios client + typed endpoint functions
        ├── auth/                   # AuthContext, guards, token handling
        ├── components/             # ConfirmDialog, StatusBanner, DataTable, PeriodFilter, AttendanceCalendar...
        ├── hooks/                  # useGeolocation, useAttendance...
        ├── pages/                  # Login, ChangePassword, Dashboard, Leave, Team, Profile, admin/*
        ├── routes.tsx
        └── types/
```
Note: backend and frontend folders are already created inside the project directory with their specific module managers installed.
poetry venv for backend and node_modules for frontend. You can find them respectively. Proceed to next steps if you find some prerequisites fulfilled.

## 4. Environment & Configuration

`.env.example` (backend reads via `pydantic-settings`; never commit real secrets):

```
# Database
DATABASE_URL=mysql+pymysql://hr_user:hr_pass@localhost:3306/hr_app

# Auth
JWT_SECRET_KEY=change-me-long-random
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7
COOKIE_SECURE=false                 # true in production (HTTPS)
MAX_FAILED_LOGINS=5
LOCKOUT_MINUTES=15

# App behavior
APP_TIMEZONE=Asia/Bangkok           # office timezone; attendance_date is computed in this zone
WORKING_WEEKDAYS=0,1,2,3,4          # Mon=0 ... Sun=6
HALF_DAY_THRESHOLD_HOURS=4          # worked < this at clock-out => status half-day
MAX_GPS_ACCURACY_M=100              # reject onsite clock action if reported accuracy is worse
MAX_REPORT_RANGE_DAYS=366
LEAVE_MAX_DAYS_PER_REQUEST=30
LEAVE_BACKDATE_DAYS=7               # how far in the past a leave start date may be
EMPLOYEE_ID_PREFIX=EMP
EMPLOYEE_ID_PAD=4                   # EMP0001

# CORS
CORS_ORIGINS=http://localhost:5173
```
This is how I'd define config.py according to my standards:
```python
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    #other configs...

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
```
So that I can resue them easily by importing in my code logic like:
```python
from config import Settings, get_settings

settings: Settings = get_settings()

secret = settings.jwt_secret_key
```

Frontend `.env`: `VITE_API_BASE_URL=http://localhost:8000/api/v1`

---

## 5. Domain Rules Summary

- **One attendance row per employee per office-local date** (`UNIQUE(employee_id, attendance_date)`).
- Clock in once per day; clock out once per day, only after clock in.
- `attendance_date` = the date of the server clock-in instant in `APP_TIMEZONE`.
- All timestamps (`clock_in`, `clock_out`, `created_at`, ...) are stored in **UTC**; converted to `APP_TIMEZONE` only at the API/UI presentation layer (API returns ISO-8601 with offset).
- **Onsite** requires a GPS fix verified within the work location's `allowed_radius_m` (50–100 m). **Remote** requires no GPS.
- The same verification applies to onsite **clock-out**.
- **Team scope** = teams where the manager has an active `team_managers` row (`removed_at IS NULL`); targets are employees whose current `employees.team_id` is one of those teams.
- **Self-approval is forbidden** for leave.

---

## 6. Database Schema

MySQL, `utf8mb4`, InnoDB. All `created_at/updated_at` default to `CURRENT_TIMESTAMP` (UTC session time zone: set `time_zone='+00:00'` on connect). Use `BIGINT UNSIGNED AUTO_INCREMENT` for surrogate PKs.

### 6.1 Tables provided by the product owner (implement exactly)

**roles**
| column | type | notes |
|---|---|---|
| id | BIGINT PK | |
| name | VARCHAR(50) UNIQUE NOT NULL | |
| description | TEXT NULL | |

**permissions**
| column | type | notes |
|---|---|---|
| id | BIGINT PK | |
| code | VARCHAR(100) UNIQUE NOT NULL | format `resource.action.scope` |
| resource | VARCHAR(50) NOT NULL | |
| action | VARCHAR(50) NOT NULL | |
| scope | VARCHAR(20) NOT NULL | `self` \| `team` \| `any` (CHECK) |
| description | TEXT NULL | |

**role_permissions**: `role_id` FK→roles.id, `permission_id` FK→permissions.id, `PRIMARY KEY (role_id, permission_id)`, `ON DELETE CASCADE`.

**employees**
| column | type | notes |
|---|---|---|
| id | BIGINT PK | |
| employee_id | VARCHAR(20) UNIQUE NOT NULL | immutable business ID, e.g. `EMP0001` |
| password_hash | VARCHAR(255) NOT NULL | argon2 |
| role_id | BIGINT FK→roles.id NOT NULL | |
| team_id | BIGINT FK→teams.id NULL | current team |
| first_name | VARCHAR(100) NOT NULL | |
| last_name | VARCHAR(100) NOT NULL | |
| display_name | VARCHAR(100) NULL | |
| position | VARCHAR(100) NULL | |
| department | VARCHAR(100) NULL | |
| is_active | BOOLEAN DEFAULT TRUE | soft-deactivate; inactive users cannot log in |
| created_at | TIMESTAMP NOT NULL | |
| updated_at | TIMESTAMP NOT NULL | ON UPDATE |

**Additional columns to add to `employees`** (required by the workflow; see Section 19):
| column | type | notes |
|---|---|---|
| must_change_password | BOOLEAN NOT NULL DEFAULT TRUE | true on creation and on HR reset |
| password_changed_at | TIMESTAMP NULL | |
| failed_login_count | INT NOT NULL DEFAULT 0 | |
| locked_until | TIMESTAMP NULL | |
| last_login_at | TIMESTAMP NULL | |

**teams**: `id` PK, `name` VARCHAR(100) NOT NULL (UNIQUE), `description` TEXT NULL.

**team_members**: `team_id` FK, `employee_id` FK→employees.id, `joined_at` TIMESTAMP NOT NULL, `left_at` TIMESTAMP NULL. PK `(team_id, employee_id, joined_at)`. This is the **membership history**; `employees.team_id` is the **current team**. They must be updated together in one transaction (close the old row with `left_at`, open a new row).

**team_managers**: `team_id` FK, `employee_id` FK→employees.id, `assigned_at` TIMESTAMP NOT NULL, `removed_at` TIMESTAMP NULL. PK `(team_id, employee_id, assigned_at)`. A team may have multiple active managers. A manager cannot manage a team when their role lacks `attendance.read.team` or `attendance.read.any`.

**work_locations**
| column | type | notes |
|---|---|---|
| id | BIGINT PK | |
| name | VARCHAR(100) NOT NULL | |
| latitude | DECIMAL(9,6) NOT NULL | CHECK between -90 and 90 |
| longitude | DECIMAL(9,6) NOT NULL | CHECK between -180 and 180 |
| allowed_radius_m | INTEGER NOT NULL | CHECK between 50 and 100, default 100 |

**team_work_locations**: `team_id` FK, `work_location_id` FK, `PRIMARY KEY (team_id, work_location_id)`.

**attendance**
| column | type | notes |
|---|---|---|
| id | BIGINT PK | |
| employee_id | BIGINT FK→employees.id NOT NULL | |
| attendance_date | DATE NOT NULL | office-local date |
| work_mode | ENUM('onsite','remote') NOT NULL | |
| work_location_id | BIGINT FK NULL | matched location for onsite |
| clock_in | TIMESTAMP NULL | UTC |
| clock_out | TIMESTAMP NULL | UTC |
| clock_in_latitude / clock_in_longitude | DECIMAL(9,6) NULL | |
| clock_in_accuracy_m | DECIMAL(8,2) NULL | |
| clock_in_distance_m | DECIMAL(8,2) NULL | |
| clock_in_verified | BOOLEAN NULL | |
| clock_out_latitude / clock_out_longitude | DECIMAL(9,6) NULL | |
| clock_out_accuracy_m | DECIMAL(8,2) NULL | |
| clock_out_distance_m | DECIMAL(8,2) NULL | |
| clock_out_verified | BOOLEAN NULL | |
| status | ENUM('present','absent','half-day') NOT NULL | |
| updated_by | BIGINT FK→employees.id NULL | set when manager/HR edits (audit) |
| created_at / updated_at | TIMESTAMP | |

Indexes: `UNIQUE(employee_id, attendance_date)`, `INDEX(attendance_date)`.

### 6.2 Additional tables (required by the Leave feature and supporting workflows)

**leave_types**: `id`, `code` VARCHAR(30) UNIQUE, `name`, `is_active`.
Seed: `annual`, `sick`, `personal`, `maternity`, `paternity`, `unpaid`, `other`.

**leave_reasons**: `id`, `code` VARCHAR(40) UNIQUE, `name`, `requires_text` BOOLEAN, `is_active`.
Seed: `vacation`, `medical`, `family_emergency`, `personal_errand`, `childcare`, `other` (`requires_text = TRUE` only for `other`).

**leave_requests**
| column | type | notes |
|---|---|---|
| id | BIGINT PK | |
| employee_id | BIGINT FK NOT NULL | requester |
| leave_type_id | BIGINT FK NOT NULL | |
| leave_reason_id | BIGINT FK NOT NULL | |
| reason_text | VARCHAR(500) NULL | required iff reason `requires_text` |
| duration_type | ENUM('half_day','full_days') NOT NULL | |
| half_day_period | ENUM('morning','afternoon') NULL | required iff `half_day` |
| num_days | DECIMAL(4,1) NOT NULL | 0.5 for half-day, else integer 1..`LEAVE_MAX_DAYS_PER_REQUEST` |
| start_date | DATE NOT NULL | chosen from calendar |
| end_date | DATE NOT NULL | computed server-side (see 10.5) |
| reporting_manager_id | BIGINT FK→employees.id NOT NULL | chosen by employee |
| remark | VARCHAR(500) NULL | optional |
| status | ENUM('pending','approved','rejected','cancelled') NOT NULL DEFAULT 'pending' | |
| decided_by | BIGINT FK→employees.id NULL | |
| decided_at | TIMESTAMP NULL | |
| decision_note | VARCHAR(500) NULL | |
| created_at / updated_at | TIMESTAMP | |

Indexes: `(employee_id, start_date)`, `(reporting_manager_id, status)`, `(status)`.

**id_sequences**: `name` VARCHAR(50) PK, `next_value` BIGINT NOT NULL. Row `employee_id` seeded with `1`. Used with `SELECT ... FOR UPDATE` to generate `EMPxxxx` race-free.

**audit_logs** (recommended, small): `id`, `actor_id` FK, `action` VARCHAR(50), `entity` VARCHAR(50), `entity_id` BIGINT, `before_json` JSON NULL, `after_json` JSON NULL, `created_at`. Written on: attendance edits, leave decisions, role/team changes, password resets, employee (de)activation.

### 6.3 Relationship diagram

```
roles 1─* employees *─1 teams
roles *─* permissions (via role_permissions)
teams *─* employees (team_members: history)      teams *─* employees (team_managers)
teams *─* work_locations (team_work_locations)
employees 1─* attendance *─0..1 work_locations
employees 1─* leave_requests *─1 employees (reporting_manager_id)
```

---

## 7. Seed Data (roles & permissions)

Seeded idempotently by `scripts/seed_reference_data.py` (also invoked by `create_admin.py`). Permission `code = resource.action.scope`.

### 7.1 Permissions

| code | resource | action | scope |
|---|---|---|---|
| profile.read.self | profile | read | self |
| profile.update.self | profile | update | self |
| attendance.create.self | attendance | create | self |
| attendance.read.self | attendance | read | self |
| attendance.read.team | attendance | read | team |
| attendance.read.any | attendance | read | any |
| attendance.update.team | attendance | update | team |
| attendance.update.any | attendance | update | any |
| leave.create.self | leave | create | self |
| leave.read.self | leave | read | self |
| leave.read.team | leave | read | team |
| leave.read.any | leave | read | any |
| leave.decide.team | leave | decide | team |
| leave.decide.any | leave | decide | any |
| employee.read.team | employee | read | team |
| employee.read.any | employee | read | any |
| employee.create.any | employee | create | any |
| employee.update.any | employee | update | any |
| team.manage.any | team | manage | any |
| location.manage.any | location | manage | any |
| report.export.self | report | export | self |
| report.export.any | report | export | any |

### 7.2 Role → permission mapping

| Role | Permissions |
|---|---|
| `employee` | profile.read.self, profile.update.self, attendance.create.self, attendance.read.self, leave.create.self, leave.read.self, report.export.self |
| `senior_staff` | same as `employee` (label only in MVP; can be extended later) |
| `reporting_manager` | everything in `employee` + attendance.read.team, attendance.update.team, leave.read.team, leave.decide.team, employee.read.team |
| `hr` | everything in `employee` + **all `*.any` permissions** (attendance.read/update.any, leave.read/decide.any, employee.read/create/update.any, team.manage.any, location.manage.any, report.export.any) |
| `c_level` | identical to `hr` |

HR and C-level are the "admin" roles. The helper `is_admin(employee)` = role has `employee.create.any`.

---

## 8. Authentication

- **Login:** `POST /api/v1/auth/login` using OAuth2 password form (`application/x-www-form-urlencoded`: `username` = **employee_id**, `password`). FastAPI `OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")` is used for the dependency and Swagger UI.
- **Tokens:**
  - **Access token** (JWT, 30 min): claims `sub` (employees.id), `employee_id`, `role`, `pwd_change_required` (bool), `type="access"`, `exp`, `iat`. Returned in the JSON body and **kept in memory** on the frontend (not `localStorage`).
  - **Refresh token** (JWT, 7 days): `type="refresh"`, set as an **httpOnly, SameSite=Strict, Secure (in prod)** cookie scoped to `/api/v1/auth`. `POST /auth/refresh` issues a new access token (and rotates the refresh token). `POST /auth/logout` clears the cookie.
- **Generic failures:** wrong ID or wrong password both return `401 {"code":"INVALID_CREDENTIALS"}`; never reveal which one was wrong. Inactive accounts return the same error.
- **Lockout:** after `MAX_FAILED_LOGINS` consecutive failures, set `locked_until = now + LOCKOUT_MINUTES`; return `429` with code `ACCOUNT_LOCKED` while locked. Reset the counter on success.
- **Forced password change:** when `must_change_password = true`, the access token has `pwd_change_required=true`. The dependency `get_current_employee` still authenticates, but `require_password_changed` (applied to all routers except `/auth/*` and `GET /me`) returns `403 {"code":"PASSWORD_CHANGE_REQUIRED"}`. The frontend redirects to `/change-password`.
- **Change password:** `POST /auth/change-password` `{current_password, new_password}`. Rules: min 8 chars, must differ from current, must include letters and digits (document in the schema validator). On success set `must_change_password=false`, `password_changed_at=now`, and return fresh tokens.
- **Token validation:** verify signature, `exp`, `type`, then reload the employee from DB every request and reject if `is_active = false` (so deactivation takes effect immediately).
- Passwords hashed with **argon2** (`pwdlib`). Support `needs_rehash` on login.

---

## 9. Authorization (RBAC + Contextual Scope)

Implements the diagram from the product owner:

```
Authenticate employee → role → role_permissions → permission exists?
   NO  → 403 Forbidden
   YES → scope?
       self → employee.id == target.id ?
       team → caller actively manages target.team_id ?
       any  → allow
```

### 9.1 Implementation (`deps/authz.py`)

- Load the caller's permission set once per request: `SELECT p.* FROM permissions p JOIN role_permissions rp ... WHERE rp.role_id = :role_id` (cache per request on `request.state`; optional short TTL cache keyed by role_id, invalidated on role changes).
- Provide:

```python
def has_permission(caller, resource: str, action: str) -> set[str]:
    """Return the set of scopes the caller holds for (resource, action), e.g. {'self','team'}."""

def authorize(caller, resource, action, target_employee=None) -> None:
    scopes = scopes_for(caller, resource, action)
    if not scopes: raise Forbidden("PERMISSION_DENIED")
    if "any" in scopes: return
    if target_employee is None:               # e.g. create-own resources
        if "self" in scopes: return
        raise Forbidden("PERMISSION_DENIED")
    if "self" in scopes and caller.id == target_employee.id: return
    if "team" in scopes and manages_team_of(caller, target_employee): return
    raise Forbidden("OUT_OF_SCOPE")

def manages_team_of(caller, target) -> bool:
    # exists team_managers where employee_id = caller.id AND removed_at IS NULL
    #                     AND team_id = target.team_id (target.team_id must not be NULL)
```

- Route usage: `Depends(require_permission("attendance", "read"))` makes sure the caller holds *some* scope for that permission; the handler/service then calls `authorize(...)` with the loaded target for the contextual check.
- **List endpoints** must filter by effective scope, not just check it: `any` → all employees; `team` → employees whose `team_id` is in the caller's managed team IDs (plus the caller); `self` → only the caller. Implement a reusable `scoped_employee_ids_query(caller, resource, action)` helper.
- A scope hierarchy is implied: `any` ⊇ `team` ⊇ `self`. A manager always also has `self` permissions, so they access their own data through the self scope.
- Out-of-scope access to a specific target returns **403** (per the diagram). A non-existent target returns 404 only after the caller is confirmed to hold at least the `team` or `any` scope (avoid leaking existence to self-only users).
- Permission checks must never rely on role **names** in code; only permission codes (the sole exception is the bootstrap script).

---

## 10. Business Logic

### 10.1 Clock in (`POST /attendance/clock-in`)

Request: `{ work_mode: "onsite" | "remote", latitude?: number, longitude?: number, accuracy_m?: number }`

Algorithm (single DB transaction):
1. Caller needs `attendance.create.self`.
2. `now_utc = server time`; `attendance_date = now_utc.astimezone(APP_TIMEZONE).date()`.
3. If an attendance row exists for `(employee, attendance_date)` with `clock_in` set → `409 ALREADY_CLOCKED_IN`.
4. If `work_mode == "onsite"`: run **GPS verification (10.3)**. On failure → reject, **do not** create/modify the attendance row (log a warning with distance and accuracy; no PII beyond employee id).
5. If `work_mode == "remote"`: ignore/clear any coordinates; `clock_in_verified = NULL`.
6. Insert/update the row: `clock_in = now_utc`, `status = 'present'`, plus GPS fields for onsite.
7. Return the attendance record and a human-readable `message`, e.g. `"Clocked in at 09:02 (Onsite – HQ Office)."`.

### 10.2 Clock out (`POST /attendance/clock-out`)

Request shape identical to clock-in (coordinates required only when the day's `work_mode` is `onsite`; the work mode is **taken from the existing row**, not from the request).
1. Find today's row; none or no `clock_in` → `409 NOT_CLOCKED_IN`.
2. `clock_out` already set → `409 ALREADY_CLOCKED_OUT`.
3. Onsite → verify GPS against the same rules (10.3). Failure → reject, leave row unchanged.
4. Set `clock_out = now_utc` (+ GPS fields). Compute worked hours; if `< HALF_DAY_THRESHOLD_HOURS` set `status = 'half-day'`, else keep `'present'`.
5. Return record + message `"Clocked out at 18:05. Worked 9h 03m."`.

Overnight shifts are out of scope; the clock-out must fall on the same `attendance_date`, otherwise see Section 19.

### 10.3 GPS verification (`services/gps_service.py`)

```python
from geopy.distance import geodesic

def verify_onsite(team_locations, lat, lon, accuracy_m) -> GpsResult:
    # 1. Validate: lat in [-90,90], lon in [-180,180], both present -> else 422 GPS_REQUIRED
    # 2. accuracy_m > MAX_GPS_ACCURACY_M -> 422 LOW_GPS_ACCURACY (ask user to retry outdoors / near a window)
    # 3. team_locations empty -> 422 NO_WORK_LOCATION_CONFIGURED
    # 4. For each location: d = geodesic((lat, lon), (loc.latitude, loc.longitude)).meters
    # 5. nearest = min by d; verified = nearest.d <= nearest.allowed_radius_m
    # 6. not verified -> 403 OUTSIDE_WORK_PERIMETER with {distance_m, allowed_radius_m}
    # 7. return GpsResult(location_id, distance_m, verified=True)
```

- Candidate locations = those linked to the employee's **team** via `team_work_locations`. If the employee has no team, fall back to an empty set → `NO_WORK_LOCATION_CONFIGURED`.
- Store: lat, lon, accuracy, distance (rounded to 2 dp), verified flag, matched `work_location_id`.
- **Limitations (document in README, do not over-engineer):** browser GPS can be spoofed. The server stores accuracy/distance for audit; manager/HR can review and edit attendance.

### 10.4 Attendance status rules

| Situation | Stored/derived status |
|---|---|
| Clocked in | `present` (stored) |
| Clocked out with worked time `< HALF_DAY_THRESHOLD_HOURS` | `half-day` (stored) |
| Approved half-day leave for that date | dashboard shows `half-day` + leave info |
| Approved full-day leave covering the date | dashboard shows **`leave`** (derived, not stored in `attendance`) |
| Past **working** day with no row and no approved leave | dashboard shows **`absent`** (derived at read time) |
| Weekend / non-working weekday | `weekend` (derived) |
| Future date | `upcoming` (derived) |
| Manager/HR manual edit | stored status changes to `present`/`absent`/`half-day`, `updated_by` set, audit log written |

The `attendance.status` column keeps the three values required by the spec; `leave`, `weekend`, `upcoming` exist only in the dashboard/calendar response (`display_status`).

### 10.5 Leave requests

**Form fields (all validated server-side):**
- `leave_type_id` (required), `leave_reason_id` (required), `reason_text` (required if reason is `other`; max 500).
- `duration_type`: `half_day` | `full_days`. If `half_day` → `half_day_period` (`morning`/`afternoon`) required, `num_days = 0.5`. If `full_days` → `num_days` integer `1..LEAVE_MAX_DAYS_PER_REQUEST`.
- `start_date` (chosen from the calendar). Must be `>= today - LEAVE_BACKDATE_DAYS`. Must be a working day.
- `reporting_manager_id` (required): must be an **eligible manager** (below).
- `remark` optional (max 500).

**Server computes `end_date`:** walk forward from `start_date`, counting only working weekdays (`WORKING_WEEKDAYS`), until `num_days` working days are covered (half-day → `end_date = start_date`). Public holidays are out of MVP scope.

**Eligible reporting managers** (`GET /leave/options`): active employees with an active `team_managers` row for the requester's `team_id`, excluding the requester. If there is none, fall back to active employees holding `leave.decide.any`. The frontend shows manager **names** (display name, else first + last) in a dropdown; the API submits the id.

**Rules:**
- Overlap check: reject if any existing `pending` or `approved` request of the same employee overlaps `[start_date, end_date]` (two half-days on the same date with different `half_day_period` are allowed).
- `reporting_manager_id != employee.id`.
- Initial `status = 'pending'`.
- **Decision** (`approve` / `reject`, optional `decision_note`): allowed to (a) the selected `reporting_manager_id` **if they still hold `leave.decide.team` and manage the requester's team**, or (b) anyone with `leave.decide.any`. Nobody may decide their own request. Only `pending` requests can be decided → else `409 INVALID_STATE`.
- **Cancel:** the requester may cancel while `pending`, or when `approved` and `start_date` is in the future. Writes audit log.
- Approved leave feeds the dashboard/calendar (10.4). Leave balances/quotas are out of MVP scope.

### 10.6 Dashboards & date ranges

- **Period filter:** `view = week | month | year | custom` with an anchor date or (`from`,`to`). Default: current **month**. The year selector lists years that contain data (e.g. 2025, 2026). The maximum span of any query is `MAX_REPORT_RANGE_DAYS` (366) → else `422 RANGE_TOO_LARGE`. Week starts Monday.
- **History limit:** data older than one year before today is not exposed to employees in the dashboard/export (HR can query any range within the 366-day cap).
- The calendar endpoint returns one entry per date in range with: `date`, `display_status`, `work_mode`, `clock_in`, `clock_out`, `work_location_name`, `leave` (type, half/full, status) if any.
- **Summary** block: counts of present / half-day / leave / absent days and total worked hours for the range.
- **Manager/HR team views:** a list of members with per-member summary for the range, and drill-down into a member's dashboard (same shape as the personal one), all filtered by the caller's scope.

### 10.7 CSV export

- Employee: `GET /attendance/export?from=&to=` (self only; range ≤ 366 days). HR/C-level: `GET /admin/reports/attendance.csv` and `/admin/reports/leave.csv` with optional filters (`from`, `to`, `team_id`, `employee_id`).
- Stream the response (`StreamingResponse`), `Content-Type: text/csv; charset=utf-8`, `Content-Disposition: attachment; filename=attendance_EMP0001_2026-01-01_2026-03-31.csv`. Write a **UTF-8 BOM** so Excel opens it correctly.
- Attendance columns: `employee_id, name, team, date, display_status, work_mode, work_location, clock_in_local, clock_out_local, worked_hours, clock_in_verified, clock_out_verified, clock_in_distance_m, clock_out_distance_m`.
- Leave columns: `employee_id, name, team, leave_type, reason, reason_text, duration, num_days, start_date, end_date, reporting_manager, status, decided_by, decided_at, remark`.
- **CSV injection protection:** prefix any string cell starting with `=`, `+`, `-`, `@`, tab or CR with a single quote `'`.
- Export endpoints are authorized with `report.export.self` / `report.export.any`.

### 10.8 Employee & team administration (HR / C-level)

- **Create employee** (`POST /admin/employees`): inputs `first_name, last_name, display_name?, position?, department?, role_id, team_id?, default_password`. The server generates `employee_id` via `id_service` (`EMPLOYEE_ID_PREFIX` + zero-padded counter, `SELECT ... FOR UPDATE` on `id_sequences`). HR either types the default password or clicks "Generate" (frontend calls `GET /admin/utils/generate-password`; the server returns a random 12-char password shown once). `must_change_password = true`. The response echoes the plaintext default password **once** so HR can hand it over; it is never retrievable later.
- **Reset password** (`POST /admin/employees/{id}/reset-password` with a new default password): sets the hash, `must_change_password = true`, clears lockout. This is how HR "defines the default password at any time".
- **Update employee** (role, team, position, department, names, `is_active`). `employee_id` is immutable (reject if present in the payload). Changing `team_id` closes/opens `team_members` rows atomically. Deactivating never deletes data.
- Prevent HR from removing their own admin role or deactivating themselves if they are the last active admin → `409 LAST_ADMIN`.
- **Teams:** CRUD; assign/remove managers (`team_managers`), add/move members (`team_members` + `employees.team_id`), link work locations (`team_work_locations`). Assigning a manager validates their role permission (Section 6.1).
- **Work locations:** CRUD with `allowed_radius_m` constrained to 50–100 (default 100).
- **Profile (self):** `PATCH /me` accepts only `display_name` (and password via `/auth/change-password`). Ignore/reject `employee_id`, `role_id`, `team_id`, `is_active`.

---

## 11. API Specification

Base path `/api/v1`. JSON unless stated. Paginate lists with `page`, `page_size` (default 25, max 100). Uniform error body:

```json
{ "code": "OUTSIDE_WORK_PERIMETER", "message": "You are 240 m from the office.", "details": { "distance_m": 240, "allowed_radius_m": 100 } }
```

Standard codes: `401` unauthenticated, `403` forbidden / `PASSWORD_CHANGE_REQUIRED`, `404` not found, `409` conflict/state, `422` validation, `429` lockout/rate limit.

| Method & path | Permission | Notes |
|---|---|---|
| POST `/auth/login` | public | form data: username=employee_id |
| POST `/auth/refresh` | refresh cookie | |
| POST `/auth/logout` | auth | |
| POST `/auth/change-password` | auth (allowed while change required) | |
| GET `/me` | profile.read.self | profile + role + permissions list + team + `must_change_password` (allowed while change required) |
| PATCH `/me` | profile.update.self | `display_name` only |
| GET `/attendance/today` | attendance.read.self | today's row + next allowed action (`clock_in`/`clock_out`/`none`) |
| POST `/attendance/clock-in` | attendance.create.self | 10.1 |
| POST `/attendance/clock-out` | attendance.create.self | 10.2 |
| GET `/attendance/calendar` | attendance.read.{self,team,any} | `employee_id?` (default self), `view`, `anchor`/`from`/`to`; scope-checked |
| GET `/attendance` | same | tabular list version, paginated |
| PATCH `/attendance/{id}` | attendance.update.{team,any} | `status`, `clock_in`, `clock_out`, `reason` (required); sets `updated_by`, audit log |
| GET `/attendance/export` | report.export.self | own CSV |
| GET `/team/members` | employee.read.team/any | list in scope with today's status |
| GET `/team/attendance` | attendance.read.team/any | per-member summary for range |
| GET `/leave/options` | leave.create.self | types, reasons, eligible managers |
| POST `/leave-requests` | leave.create.self | 10.5 |
| GET `/leave-requests` | leave.read.self | own requests |
| GET `/leave-requests/team` | leave.read.team/any | filter by `status`, `employee_id` |
| GET `/leave-requests/{id}` | self/team/any contextual | |
| POST `/leave-requests/{id}/cancel` | requester | |
| POST `/leave-requests/{id}/approve` | leave.decide.team/any | `decision_note?` |
| POST `/leave-requests/{id}/reject` | leave.decide.team/any | `decision_note?` |
| GET/POST `/admin/employees`, GET/PATCH `/admin/employees/{id}` | employee.read.any / create.any / update.any | list supports search, team, role, active filters |
| POST `/admin/employees/{id}/reset-password` | employee.update.any | |
| GET `/admin/utils/generate-password` | employee.create.any | |
| GET `/admin/roles` | employee.read.any | roles + permissions (read-only in MVP) |
| CRUD `/admin/teams`, `/admin/teams/{id}/members`, `/admin/teams/{id}/managers`, `/admin/teams/{id}/locations` | team.manage.any | |
| CRUD `/admin/work-locations` | location.manage.any | |
| GET `/admin/reports/attendance.csv`, `/admin/reports/leave.csv` | report.export.any | |
| GET `/healthz` | public | |

OpenAPI docs stay enabled in dev, disabled in production via config.

---

## 12. Bootstrap Script (first admin)

`backend/scripts/create_admin.py` — run once after migrations:

```
python -m scripts.create_admin --first-name Jane --last-name Doe --role hr [--employee-id EMP0001] [--password '...']
```

Behavior:
1. Run `seed_reference_data` (roles, permissions, role_permissions, leave types/reasons, `id_sequences`) idempotently.
2. Abort with a clear message if any employee with an admin role (`hr` or `c_level`) already exists, unless `--force` is passed.
3. Read the password from `--password`, else the env var `ADMIN_INITIAL_PASSWORD`, else prompt with `getpass` (twice). Enforce the same password policy. **Never print the password.**
4. Generate the `employee_id` with `id_service` (or use `--employee-id`), hash the password (argon2), insert the employee with `role_id` = `hr` or `c_level`, `must_change_password = true`, `is_active = true`.
5. Print `Admin created: <employee_id>`. Exit code 0 on success, non-zero on failure.
6. Wire it into the README and optionally a `make bootstrap` target.

The admin then logs in through the UI, is forced to change the password, and gains full access.

---

## 13. Frontend Specification (React + TypeScript + Vite)

### 13.1 Structure & conventions
- Axios instance with base URL from `VITE_API_BASE_URL`, `withCredentials: true` (refresh cookie), request interceptor attaching the in-memory access token, response interceptor that on `401` calls `/auth/refresh` once then retries; if refresh fails → log out and redirect to `/login`.
- TanStack Query for server state; react-hook-form + zod for forms (mirror backend validation).
- Types generated or hand-written in `src/types` matching backend schemas.
- **Route guards:** `<RequireAuth>`, `<RequirePermission code="...">` (reads permission codes from `GET /me`), and a global redirect to `/change-password` when `must_change_password` is true.
- UI is responsive (mobile + laptop). Accessible dialogs (focus trap, Esc to close).

### 13.2 Pages

| Route | Who | Content |
|---|---|---|
| `/login` | public | Employee ID + password. Generic error message. |
| `/change-password` | auth | Forced on first login; also reachable from Profile. |
| `/` (Dashboard) | all | Clock panel (work-mode selector Onsite/Remote, **Clock in / Clock out** buttons), **status banner**, personal attendance table/calendar with `PeriodFilter` (Week / **Month (default)** / Year, year picker), summary cards. |
| `/leave` | all | Leave Request form (left) + "My requests" list with status & cancel (right). |
| `/team` | managers, HR, C-level | Team member list with today's status; select a member → member dashboard (same components); pending leave approvals tab with approve/reject dialog (note field). |
| `/profile` | all | Display name edit, change password, read-only Employee ID, name, role, team, export panel (period picker + "Download CSV"). |
| `/admin/employees` | HR, C-level | Table with search/filters; create/edit drawer; reset password; deactivate. Show the default password once after create/reset with a copy button. |
| `/admin/teams` | HR, C-level | Teams, members, managers, linked work locations. |
| `/admin/locations` | HR, C-level | Work locations with map-coordinate inputs and radius (50–100 m). |
| `/admin/reports` | HR, C-level | Filters + download attendance/leave CSV. |
| `/admin/all-attendance` | HR, C-level | Company-wide attendance list and any employee's dashboard. |

### 13.3 Clock in/out UX (critical)
1. User selects **Onsite** or **Remote**.
2. Clicking **Clock in**/**Clock out** opens a **ConfirmDialog** ("Clock in now as Onsite?"). Only after confirmation does the app proceed.
3. If **Onsite**: call `navigator.geolocation.getCurrentPosition(success, error, { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 })`.
   - Permission denied → show blocking inline instructions to enable location permission in the browser (mobile and laptop), with a "Try again" button. **Do not** send the request without coordinates.
   - Timeout / unavailable → friendly error + retry.
   - Must run in a **secure context** (HTTPS, or `localhost` in dev). Show a clear message otherwise.
   - Use `Permissions API` (`navigator.permissions.query({name:'geolocation'})`) when available to show permission state proactively.
4. Send `{work_mode, latitude, longitude, accuracy_m}` (from `coords.accuracy`). Do **not** send a timestamp.
5. Disable buttons while the request is in flight (prevent double submission).
6. On success, the **StatusBanner** shows the server message (e.g. "Clocked in at 09:02 — Onsite (HQ Office)") and persists for the session/day; on error it shows the server error message (e.g. distance from office) with a retry affordance.
7. Buttons reflect `GET /attendance/today.next_action` (Clock out disabled before clock in; both disabled after clock out with "You're done for today").

### 13.4 Leave form UX
- Fields in order: Leave type (select), Reason (select with defaults + **Other** → reveals required text input), Duration (radio: Half day / Full day(s)); Half day → morning/afternoon toggle; Full days → number selector (1, 2, 3, … up to max), Start date via calendar (`react-day-picker`, weekends (only Sunday) disabled, past limit), computed end date preview (read-only), Reporting manager (select by name), Remark (optional textarea).
- Submit → confirmation toast; list refreshes; errors (e.g. overlap) displayed inline.

### 13.5 Dashboard components
- `PeriodFilter` (Week / Month / Year + prev/next + year picker), default Month, blocks ranges > 1 year.
- `AttendanceTable` (date, status badge, work mode badge Onsite/Remote, clock in, clock out, hours, leave info).
- `AttendanceCalendar` (month grid colored by `display_status`; legend; tooltip with times).
- Times are shown in the office timezone (`APP_TIMEZONE`) returned by the API.

---

## 14. Security Requirements

- Passwords: argon2, policy enforced server-side; never logged; default passwords shown once.
- JWT secret from env; short-lived access token; refresh via httpOnly cookie; CORS restricted to `CORS_ORIGINS`; `allow_credentials=True` only with explicit origins.
- Input validation via Pydantic; all DB access through SQLAlchemy (parameterized); no raw string-built SQL.
- Rate-limit `/auth/login` (per IP + per employee_id; `slowapi` or simple DB/Redis-free in-memory limiter acceptable for MVP) in addition to lockout.
- Security headers (frontend served behind a reverse proxy: HSTS, `X-Content-Type-Options`, `Referrer-Policy`, CSP).
- Geolocation requires HTTPS in production; document the TLS requirement.
- Audit log for sensitive changes (Section 6.2).
- CSV injection mitigation (Section 10.7).
- Do not expose stack traces; unhandled errors return `500 {"code":"INTERNAL_ERROR"}` and are logged with a request id.

---

## 15. Testing Requirements

**Backend (pytest, real MySQL via docker-compose test DB, transactional fixtures):**
- Auth: login success/failure, lockout, refresh rotation, forced password change gating, inactive user rejection.
- Authz matrix: for each role × representative endpoint, expect allowed/denied. Specifically:
  - Employee cannot read another employee's attendance (403).
  - Manager can read only members of **their own** team; another team → 403; list endpoints never include other teams.
  - HR and C-level can read everything.
  - Removing a manager (`removed_at` set) immediately revokes team access.
- Attendance: clock-in/out happy paths; duplicates (409); onsite inside/outside radius; low accuracy; missing coords; no work location; remote without coords; server time used even if a fake client time is sent; status half-day threshold; manager edit writes `updated_by` and audit log.
- GPS unit tests with known coordinates (e.g. points at ~30 m, ~99 m, ~101 m, ~500 m from the office).
- Leave: validation matrix (half-day vs full days, `other` reason text), end_date computation skipping weekends (only Sunday), overlap rejection, ineligible manager rejection, approve/reject/cancel state machine, self-approval forbidden.
- Export: range cap, BOM present, CSV injection escaping, scope enforcement.
- Bootstrap script: idempotency, refuses second admin without `--force`.
- Employee ID generation under concurrent creation (no duplicates).

**Frontend (vitest + RTL):** guards/redirects, ConfirmDialog flow, geolocation denied/timeout handling (mock `navigator.geolocation`), leave form conditional fields, period filter behavior, forced password change redirect.

**Quality gates:** `ruff`, `mypy`, `pytest`, `eslint`, `tsc --noEmit`, `vitest` all pass.

---

## 16. Local Development

```
docker compose up -d mysql
cd backend && pip install -e ".[dev]" && alembic upgrade head
python -m scripts.seed_reference_data
python -m scripts.create_admin --first-name Admin --last-name User --role hr
uvicorn app.main:app --reload
cd ../frontend && npm install && npm run dev
```

Provide `README.md` with these steps, env variables, and a note that **onsite clock-in testing requires HTTPS or `localhost`**. Provide a `scripts/dev_seed_demo.py` (optional) that creates a demo team, work location, manager and employees for manual testing.

---

## 17. Implementation Phases (step-by-step)

Complete each phase fully (code + tests) before starting the next.

**Phase 1 — Project scaffolding**
1. Create the repo layout (Section 3), `docker-compose.yml` with MySQL 8, `.env.example`, backend `pyproject.toml`, frontend Vite + React + TS (strict) + Tailwind.
2. `core/config.py`, `core/database.py` (set session time zone to UTC), `core/errors.py` with uniform error handlers, `/healthz`.
3. Lint/format/type-check configs and CI-style `make check`.
- ✅ Accept: `GET /healthz` works; `ruff`/`mypy`/`eslint`/`tsc` run clean.

**Phase 2 — Database & migrations**
1. Implement all models in Section 6 (including additions) with constraints, indexes, CHECKs.
2. Generate the initial Alembic migration; verify upgrade and downgrade.
3. `seed_reference_data.py` (Section 7) — idempotent.
- ✅ Accept: fresh DB → `alembic upgrade head` → seed twice yields no duplicates; CHECK constraints reject invalid radius/lat/lon.

**Phase 3 — Authentication**
1. `security.py` (argon2, JWT), `auth_service`, `/auth/*` endpoints, `deps/auth.py` (`get_current_employee`, `require_password_changed`).
2. Lockout, rate limiting, refresh cookie flow, change-password.
3. `create_admin.py` (Section 12).
- ✅ Accept: bootstrap → login as admin → forced password change → normal access. Auth tests green.

**Phase 4 — Authorization core**
1. `deps/authz.py`: permission loading, scopes, `authorize`, `manages_team_of`, `scoped_employee_ids_query`, `require_permission`.
2. Test fixtures: factories for employees in two teams, a manager per team, HR, C-level.
3. Authz matrix tests against a few stub endpoints (`/me`, `/team/members`).
- ✅ Accept: matrix tests prove self/team/any behavior and 403s per Section 9.

**Phase 5 — Admin: employees, teams, locations**
1. `id_service`, `employee_service`, `team_service`; admin routers (Section 10.8).
2. Team membership/manager history consistency, last-admin protection, audit logs.
- ✅ Accept: HR creates a team, location, manager, employee; employee appears in the manager's `/team/members`; immutability of `employee_id` enforced.

**Phase 6 — Attendance**
1. `gps_service` with geopy; `attendance_service` (clock in/out, today, edit).
2. Calendar/list/summary read endpoints with scope filtering and range validation (Section 10.6).
- ✅ Accept: all attendance tests in Section 15 pass.

**Phase 7 — Leave**
1. `leave_service`, options endpoint, request CRUD, decisions, cancel; integrate approved leave into the calendar/summary.
- ✅ Accept: all leave tests pass; approved leave shows on the dashboard as `leave`/`half-day`.

**Phase 8 — Reports/export**
1. `report_service` streaming CSV (self and admin) with BOM and injection protection.
- ✅ Accept: exported files open cleanly in Excel; scope and range rules verified.

**Phase 9 — Frontend foundation**
1. API client, auth context (in-memory token + refresh), route guards, layout/navigation filtered by permissions, Login, ChangePassword.
- ✅ Accept: login → forced change → dashboard; menu items match the role.

**Phase 10 — Frontend features**
1. Dashboard: clock panel with ConfirmDialog, geolocation hook, StatusBanner, PeriodFilter, table + calendar, summary.
2. Leave page; Profile page with CSV export panel.
3. Team page (members, member dashboard, leave approvals).
4. Admin pages (employees, teams, locations, reports, all-attendance).
- ✅ Accept: end-to-end manual run-through of all flows in Section 18 succeeds on desktop and a mobile viewport.

**Phase 11 — Hardening & docs**
1. Security headers/CORS review, error handling polish, loading/empty/error UI states, accessibility pass.
2. README, API docs check, final `make check`.

---

## 18. End-to-End Acceptance Scenarios

1. Bootstrap admin → login → change password → create Team A, Team B, a work location (radius 100 m) linked to Team A, a manager for Team A, and two employees (Team A and Team B).
2. New employee logs in with the default password → forced to change it → lands on the dashboard.
3. Employee (Team A) selects **Onsite**, confirms the dialog, allows location **inside** the radius → success banner with time; repeat attempt → "already clocked in". Clocks out → banner with worked hours.
4. Same employee tries onsite from ~500 m away (mock coordinates) → rejected with the distance message; no record is modified.
5. Employee clocks in as **Remote** on another day → no GPS prompt; attendance list shows "Remote".
6. Employee submits a half-day leave and a 2-day leave choosing the Team A manager → manager sees both under pending, approves one, rejects the other → employee sees updated statuses; approved leave appears in the calendar.
7. Manager can see only Team A members and their data; requesting a Team B employee → 403 and never listed.
8. HR and C-level see all employees, all attendance and all leave; HR downloads a company-wide CSV; employee downloads their own CSV for a selected period ≤ 1 year.
9. HR resets an employee's password → employee must change it at the next login.
10. Employee edits their display name; attempts to change Employee ID via API are rejected.

---

## 19. Assumptions & Resolved Ambiguities

1. **"Log in using ID and name"** in the first requirement vs **"ID and password"** later: login uses **Employee ID + password**; the employee's name is displayed after login and pre-filled in all attendance actions (no separate name entry).
2. **"Excel file" vs "CSV"**: exports are **CSV with UTF-8 BOM** (opens in Excel). Native `.xlsx` is out of MVP scope.
3. **Default password:** HR enters (or generates) the default password per account at creation and can set a new one at any time through "reset password". No global plaintext default is stored.
4. **`attendance.status` vs leave/absent/weekend:** the DB keeps `present | absent | half-day`. `absent` for missing days, `leave`, `weekend`, `upcoming` are derived in read responses (Section 10.4). A nightly job to materialize absences is out of MVP scope.
5. **Reporting manager** = an active `team_managers` member of the employee's team. The employee picks one on each leave request; managers of other teams are not selectable.
6. **Manager edits of attendance** are allowed only within their team scope, always with a mandatory reason, and audited.
7. **Overnight shifts**, **public holidays**, **leave balances/quotas**, **multi-office roaming** and **anti-GPS-spoofing beyond accuracy/distance logging** are out of MVP scope.
8. **Roles** are seeded data; the admin UI assigns existing roles but does not create new roles/permissions in the MVP (read-only roles view). Adding a role = migration/seed change.
9. **GPS radius** is configurable per work location within 50–100 m (default 100 m); the nearest linked location decides verification.
10. **Failed GPS verification does not create an attendance row.** Users can retry immediately.
11. **Deactivated employees** keep their history, cannot log in, and are excluded from dropdowns (managers, assignees) but remain in reports.
12. **Data retention view:** employees can view/export up to one year of history per query (range cap 366 days); HR can query any period within the same per-query cap.
13. **Public endpoint testing:** `/healthz` is a public liveness endpoint outside `/api/v1`, has a Pydantic response schema, and has no request body or authorization requirement. Test anonymous and invalid-token access as successful; authorization-failure tests apply to protected endpoints. Public auth routes likewise test credential/token failures rather than RBAC denial.
14. **Working-week configuration:** `WORKING_WEEKDAYS` is authoritative for both leave validation and the date picker. Pending clarification of the Sunday-only wording in Sections 13/15, preserve Section 4's Monday–Friday default; setting `0,1,2,3,4,5` enables Monday–Saturday.
15. **Phase 1 configuration and checks:** retain the existing Poetry environment, with development tools exposed through the `dev` extra. Add `APP_ENV=development|test|production` to control docs availability. `/healthz` checks process liveness without a database query; database-dependent tests begin in Phase 2 and use the isolated MySQL test service.
16. **Phase 2 timestamps:** use `TIMESTAMP(6)` and `CURRENT_TIMESTAMP(6)` so history-table composite keys preserve microseconds. ORM timestamp writes must be timezone-aware and are normalized to UTC; MySQL's naive UTC results are restored to timezone-aware UTC. `updated_at` uses MySQL's explicit `ON UPDATE CURRENT_TIMESTAMP(6)` clause.
17. **Phase 2 structural constraints:** in addition to Section 6's CHECKs, enforce nonnegative login/GPS counters, a positive employee ID sequence, chronological attendance/history/leave dates, consistent half-day/full-day leave duration fields, and no self-selection/self-decision on leave. Config-dependent limits, overlap checks, and permission/scope checks remain service responsibilities in their scheduled phases. Unspecified leave type/reason name lengths are 100 characters; workflow flags are non-null booleans.
18. **Reference seed ownership:** seeded role grants are reconciled to Section 7, including removal of unexpected grants; custom roles are untouched. Repeat seeding never resets an advanced employee ID sequence or reactivates a deactivated leave type/reason. The seed service participates in the caller's transaction; the CLI commits the whole seed atomically.
19. **Isolated MySQL tests:** schema round-trip tests may rebuild only the dedicated test schema through Alembic. The test database name must end in `_test` and differ from the development database name. Per-test transactions use savepoints to preserve rollback even when a service commits. No SQLite substitution or manual DDL is used.

---

## 20. Definition of Done (MVP)

- All phases complete and acceptance scenarios (Section 18) pass manually and via automated tests where feasible.
- Every requirement in Section 1 is implemented; every out-of-scope item is explicitly listed in Section 19, not half-built.
- Quality gates in Section 15 are green; no plaintext secrets in the repo; README allows a new developer to run the stack from scratch in under 15 minutes.
