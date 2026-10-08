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

The current application shell is the Phase 1 deliverable. Login, route guards,
and API integration begin in Phase 9; product pages follow in Phase 10.
