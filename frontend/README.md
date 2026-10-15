# HR frontend

React 18, strict TypeScript, Vite, and Tailwind CSS. See the
[root development guide](../README.md) for the API, configuration, and phase status.

```bash
cp .env.example .env
npm ci
npm run dev
```

`npm run lint`, `npm run format:check`, `npm run typecheck`, `npm run test`, and
`npm run build` run the frontend quality gates. The root `make check` runs both
backend and frontend checks.

Phase 9 provides Axios authentication, a session context, TanStack Query,
permission guards/navigation, login, and password change. Phase 10 connects Dashboard, Leave, Profile/export, Team/approvals, and all admin
pages to the backend. Tokens stay in memory; refresh cookies are browser managed.
Use the same hostname for API/frontend to preserve SameSite cookie behavior.

`src/api/client.ts` owns refresh/retry and credential operations;
`src/auth/session.ts` owns session/profile state and cache cleanup. Use `useAuth()`
for the current session and its `http.api` instance, and `useAuthState()` for the
reactive profile/status. AuthProvider supplies the QueryClient. Permissions come
from `/me`; frontend guards do not replace backend authorization.

Production hosts must fall back to `index.html` for application routes. See the
root guide for session failure behavior and manual acceptance steps.
