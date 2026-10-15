# Phase 10 acceptance record

Validated on 2026-10-15 using Chrome at 1440 × 1000 and 390 × 844.
Both viewports completed the flows below against the real FastAPI application and
an isolated, temporary MySQL 8 database migrated with Alembic. Each viewport used
a separate browser context and new test accounts. A test-only server clock and
browser geolocation override enabled multiple attendance dates and inside/outside
office checks. No production/development data was modified.

| Scenario | Result at both sizes |
| --- | --- |
| Bootstrap admin → login → forced password change → dashboard | Passed |
| Create two teams, office, manager, two employees; assign manager and link office | Passed |
| New employee login and forced password change | Passed |
| Confirm onsite clock-in, verify GPS, reject duplicate, confirm same-day clock-out | Passed |
| Cancel clock confirmation with Escape | Passed |
| GPS about 498 m outside a 100 m perimeter leaves attendance unchanged | Passed |
| Remote clock-in on another server date | Passed |
| Half-day and two-day leave requests, eligible manager selection, weekend-skipping end date | Passed |
| Selected manager approves one request and rejects the other with decision notes | Passed |
| Manager roster excludes the other team; direct cross-team attendance request returns 403 | Passed |
| Approved leave appears in the employee calendar response and dashboard | Passed |
| HR company attendance; C-level employee/leave visibility | Passed |
| Personal attendance CSV and company attendance/leave CSV downloads | Passed; six files saved, BOM verified |
| HR password reset → next employee login requires password change | Passed |
| Display-name edit; API attempt to change employee ID returns 422 | Passed |
| No page-wide horizontal overflow and no uncaught JavaScript exceptions | Passed |
| Tokens/passwords are absent from localStorage/sessionStorage | Passed |

Additional automated checks cover denied/unavailable/timed-out GPS, insecure
contexts, duplicate-submit prevention, conditional leave validation, cancellation,
self-approval controls, period limits, Unicode password policy, office timezones,
manual attendance corrections, admin validation and last-admin errors, reference
pagination, one-time password handover/cache exclusion, and report filters.

`make check` passed 659 backend tests and 110 frontend tests, Ruff, mypy, ESLint,
Prettier, strict TypeScript, and the Vite production build. Frontend checks were
repeated after the final responsive CSS changes. The existing Starlette TestClient
deprecation warning remains nonblocking.

For a local manual repetition, follow the root README setup/bootstrap instructions
and Section 18 of AGENTS.md using separate HR, manager, employee, and C-level
accounts. Use localhost or HTTPS for geolocation. Physical device GPS behavior and
production hosting/security-header review remain part of deployment validation
and Phase 11 hardening.
