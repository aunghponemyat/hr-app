# Responsive UI review

Validated on 2026-11-02. This is a presentation update to the existing frontend;
Phase 11 hardening and deployment validation remain separate work.

## Changes

- Shared buttons center their text, keep their intrinsic width in action rows,
  and wrap long labels within available space. Inputs, selects, and ordinary
  buttons share a 44-pixel control height; multiline buttons can grow vertically.
- Card padding, page spacing, filter grids, and heading margins use consistent
  dimensions. Period arrows and the anchor date stay together and align at the
  bottom of the field. Radio/checkbox controls have their own dimensions.
- Data table styles are scoped to their scroll region. Columns remain readable
  and action groups stay together; wide tables scroll locally on narrow screens.
  The leave date picker sizes its seven columns to the available width.
- Navigation becomes a horizontal scrolling row at tablet widths. Phone headers
  wrap names beside sign-out, pagination puts the record count above two aligned
  controls, and drawers fill the viewport width.
- Dialog headers reserve a fixed column for closing. Long titles wrap, tall
  dialogs scroll within the viewport, background scrolling is locked, and nested
  confirmations retain native modal focus containment. Team view buttons now
  consistently indicate the selected view.

## Verification

Browser review used headless Chrome with intercepted API responses and synthetic
employee/team/attendance/leave fixtures. It did not read or modify application
database records, create accounts, or exercise real GPS verification.

| Coverage | Checked |
| --- | --- |
| Viewport widths | 320, 390, 768, 1024, 1440, 1920 pixels |
| Pages | Dashboard, leave, profile, team, employees, teams, locations, reports, all attendance, change password, login |
| Components | Attendance calendar, leave date picker, filters, pagination, table action groups, employee drawer, password reset, team drawer, nested confirmation |
| Stress cases | 100-character unbroken names/titles; 390-pixel viewport height; inline login validation errors |
| Layout assertions | No page-wide overflow, no button text outside its bounds, no date-picker overflow, no dialog outside its viewport or with horizontal overflow |
| Modal behavior | Focus remains inside open dialogs after keyboard navigation; Escape dismisses; background scrolling is locked |
| Runtime | No uncaught JavaScript exceptions or unhandled fixture endpoints |

Frontend validation: all 110 Vitest tests, ESLint, Prettier, strict TypeScript via
the production build, and the Vite build passed. Screenshots were visually reviewed
for desktop/mobile dashboard and leave layouts, employee administration, and
dialogs/drawers. Physical devices and other browser engines were not tested.

To repeat manually, run `make dev-backend` and `make dev-frontend`, sign in with
an existing account, and use browser responsive mode at the widths above. Review
each accessible page, scroll wide tables horizontally, switch attendance between
table/calendar, and open create/edit/confirmation dialogs. Reduce viewport height
to verify dialog scrolling and use Tab/Escape to check focus and dismissal.
