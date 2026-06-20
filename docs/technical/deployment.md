# Deployment (scaffolding — not activated)

Renly's production topology (INFRA-1/2):

- **Web** (Next.js) → **Vercel**
- **API** (FastAPI) → **Railway** (built from `docker/api.Dockerfile`)
- **Database** (PostgreSQL) → **Supabase**

> **Status: configured and validated, NOT activated.** The config files and the deploy workflow
> exist and are wired correctly, but the workflow has no automatic trigger, so merging deploys
> nothing. Going live is a deliberate switch (set secrets + flip the trigger). There is **no
> staging environment** — local dev and production only.

---

## Config files in this repo

| File                           | Platform | Purpose                                                                              |
| ------------------------------ | -------- | ------------------------------------------------------------------------------------ |
| `railway.json`                 | Railway  | Build the API from `docker/api.Dockerfile`; start on `$PORT`; healthcheck `/health`. |
| `apps/web/vercel.json`         | Vercel   | Next.js framework + monorepo install/build commands.                                 |
| `.github/workflows/deploy.yml` | GitHub   | Manual (`workflow_dispatch`) deploy pipeline; runs CI first, then deploys.           |

The two existing CI workflows (`ci.api.yml`, `ci.web.yml`) already run lint / type-check / build /
tests on every PR and are reused as the gate inside `deploy.yml` (INFRA-2 keeps tests in CI).

---

## Environment variables per platform

These are set in each platform's dashboard at go-live (not committed). See
[`env-vars.md`](./env-vars.md) for the full reference.

**Railway (API):**

- `DATABASE_URL` — restricted `renly_app` role (RLS-subject) for the Supabase DB.
- `DATABASE_ADMIN_URL` — table-owner role (scheduler/migrations/auth-bootstrap; bypasses RLS).
- `JWT_SECRET` — must equal the web app's `NEXTAUTH_SECRET`.
- `ENVIRONMENT=production` — disables `/docs` and tracebacks.
- `CORS_ORIGINS` — the production web origin(s), e.g. `https://app.renly.com`.
- `TRUSTED_PROXY_COUNT` — hop count of proxies in front of the app (Railway sits behind one).
- `SENTRY_DSN` — optional; enables API error tracking.

**Vercel (web):**

- `NEXTAUTH_SECRET` — must equal the API's `JWT_SECRET`.
- `NEXTAUTH_URL` — the production web URL.
- `NEXT_PUBLIC_API_URL` — the Railway API URL (inlined at build time).
- `NEXT_PUBLIC_SENTRY_DSN` — optional; enables web error tracking.
- `SENTRY_AUTH_TOKEN` / `SENTRY_ORG` / `SENTRY_PROJECT` — optional, build-only; set these to upload
  source maps. Without `SENTRY_AUTH_TOKEN` the build neither uploads nor needs them.

---

## Activating at go-live

1. **Secrets** — add the repository secrets referenced in `deploy.yml`:
   - `RAILWAY_TOKEN`
   - `VERCEL_TOKEN`, `VERCEL_ORG_ID`, `VERCEL_PROJECT_ID`
2. **Railway** — create the API service from this repo. Service root directory = repo root (so the
   Docker build context can `COPY apps/api/...`); `railway.json` supplies the builder, start
   command, and healthcheck. Set the API env vars above.
3. **Vercel** — create the web project with **Root Directory = `apps/web`**. Vercel reads
   `apps/web/vercel.json`; the build command builds `@repo/ui` first, then the web app. Set the
   web env vars above.
4. **Supabase** — provision the database, apply `apps/api/database/01_create_tables.sql`, create
   the `renly_app` role, and enable backups (see [`backups.md`](./backups.md)).
5. **Trigger** — run **Actions → Deploy → Run workflow** manually, or add a
   `push: { branches: [main] }` trigger to `deploy.yml` to deploy on every merge to `main`.

---

## Local validation done for this scaffolding

- `railway.json`, `apps/web/vercel.json` parse as valid JSON; `deploy.yml` parses as valid YAML.
- `railway.json` references `docker/api.Dockerfile` (present) and healthcheck `/health` (the API's
  liveness route, rate-limit exempt).
- The API production image (`docker/api.Dockerfile`) builds successfully.
