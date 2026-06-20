# Environment Variables

All environment variables used by the Renly backend and frontend, with defaults and descriptions.

## Backend (`apps/api/.env`)

| Variable              | Required | Default                         | Description                                                                                                                                                                                                                                                    |
| --------------------- | -------- | ------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `DATABASE_URL`        | Yes      | —                               | Async Postgres connection string (`postgresql+asyncpg://user:pass@host:port/db`) for request connections. Must be a **restricted role** (NOBYPASSRLS, not the table owner/superuser) so Row-Level Security applies (SEC-15); the owner is exempt from policies |
| `DATABASE_ADMIN_URL`  | No       | falls back to `DATABASE_URL`    | Privileged connection (table owner) for context-less work: the scheduler, Alembic migrations, and pre-auth lookups (login/register/API-key verification). Bypasses RLS. **Production must set a distinct owner URL** or RLS is effectively disabled            |
| `JWT_SECRET`          | Yes      | —                               | Secret key for signing JWTs; min 32 chars, validated at startup. Must match `NEXTAUTH_SECRET` on the frontend                                                                                                                                                  |
| `JWT_ALGORITHM`       | No       | `HS256`                         | JWT signing algorithm                                                                                                                                                                                                                                          |
| `JWT_EXPIRE_MINUTES`  | No       | `10080`                         | JWT expiration in minutes (default: 7 days)                                                                                                                                                                                                                    |
| `ENVIRONMENT`         | No       | `development`                   | Deployment environment: `development` or `production`. In `production`, `/docs` `/redoc` `/openapi.json` are disabled and debug/tracebacks are off                                                                                                             |
| `CORS_ORIGINS`        | No       | `http://localhost:3000`         | Comma-separated list of allowed CORS origins (e.g. `https://app.renly.com,https://renly.com`)                                                                                                                                                                  |
| `TRUSTED_PROXY_COUNT` | No       | `0`                             | Number of trusted reverse proxies in front of the app, used to read the real client IP from `X-Forwarded-For` for rate limiting. `0` = reached directly. Behind a proxy/LB, set to the hop count or per-IP limits collapse onto the proxy address              |
| `WEB_BASE_URL`        | No       | `http://localhost:3000`         | Public base URL of the web app (no trailing slash). Used to build the links embedded in account emails (verification, password reset)                                                                                                                          |
| `EMAIL_PROVIDER`      | No       | `console`                       | Transactional email provider (SHELL-3): `console` logs the message to the API logs (local dev), `resend` sends via the Resend API. Swappable behind the `EmailService` port                                                                                    |
| `EMAIL_API_KEY`       | No\*     | —                               | Resend API key. **Required when `EMAIL_PROVIDER=resend`** (validated at startup); unused for `console`                                                                                                                                                         |
| `EMAIL_FROM`          | No       | `Renly <onboarding@resend.dev>` | From address for outbound email (e.g. `Renly <noreply@yourdomain.com>`). Must be a verified Resend sender in production                                                                                                                                        |

## Frontend (`apps/web/.env`)

| Variable                                  | Required | Default | Description                                                                                           |
| ----------------------------------------- | -------- | ------- | ----------------------------------------------------------------------------------------------------- |
| `NEXTAUTH_SECRET`                         | Yes      | —       | NextAuth.js signing secret. Must match `JWT_SECRET` on the backend                                    |
| `NEXTAUTH_URL`                            | Yes      | —       | Canonical URL of the web app (e.g. `http://localhost:3000`)                                           |
| `NEXT_PUBLIC_API_URL`                     | Yes      | —       | Base URL for client-side API requests (e.g. `http://localhost:8000`)                                  |
| `NEXT_PUBLIC_FALLBACK_PRIMARY_CURRENCY`   | No       | `ARS`   | Default primary currency when no user settings exist. Also pinned in currency combobox                |
| `NEXT_PUBLIC_FALLBACK_SECONDARY_CURRENCY` | No       | `USD`   | Default secondary currency when no user settings exist. Also pinned in currency combobox              |
| `NEXT_PUBLIC_FALLBACK_DOLLAR_RATE`        | No       | `mep`   | Default dollar rate preference (`oficial`, `mep`, or `blue`)                                          |
| `NEXT_PUBLIC_PREFERRED_CURRENCIES`        | No       | —       | Comma-separated currencies shown in a "Preferred" group in the currency combobox (e.g. `BRL,EUR,GBP`) |
| `NEXT_PUBLIC_PERIOD_PRESET_1`             | No       | `1M`    | First dashboard period preset button                                                                  |
| `NEXT_PUBLIC_PERIOD_PRESET_2`             | No       | `3M`    | Second dashboard period preset button                                                                 |
| `NEXT_PUBLIC_PERIOD_PRESET_3`             | No       | `6M`    | Third dashboard period preset button                                                                  |
| `NEXT_PUBLIC_PERIOD_PRESET_4`             | No       | `YTD`   | Fourth dashboard period preset button                                                                 |
| `NEXT_PUBLIC_MAX_GROUPS`                  | No       | `50`    | Maximum investment groups per user (soft limit)                                                       |
| `NEXT_PUBLIC_GROUP_LIMIT_WARNING_PCT`     | No       | —       | Percentage of max groups at which an approaching-limit warning appears. No warning if omitted         |

**Period preset format:** `NM` = N months, `NY` = N years, `YTD` = year to date. "All" is always appended as the last option. If all four are omitted, only "All" is shown.

## Shared constraints

- `JWT_SECRET` (backend) and `NEXTAUTH_SECRET` (frontend) **must be the same value**. The backend signs JWTs that NextAuth stores in its session, and the backend validates them on every API request.
- `NEXT_PUBLIC_API_URL` must point to the running API server. In Docker, use the service name or host network as appropriate.

## Docker Compose overrides

The `docker-compose.yml` passes these to services via `environment`:

| Variable              | Service         | Default via compose     |
| --------------------- | --------------- | ----------------------- |
| `POSTGRES_USER`       | postgres        | `renly`                 |
| `POSTGRES_PASSWORD`   | postgres        | `renly`                 |
| `POSTGRES_DB`         | postgres        | `renly`                 |
| `DATABASE_URL`        | api             | from `.env`             |
| `DATABASE_ADMIN_URL`  | api             | from `.env`             |
| `JWT_SECRET`          | api             | from `.env`             |
| `JWT_ALGORITHM`       | api             | from `.env`             |
| `JWT_EXPIRE_MINUTES`  | api             | from `.env`             |
| `WEB_BASE_URL`        | api             | from `.env`             |
| `EMAIL_PROVIDER`      | api             | from `.env`             |
| `EMAIL_API_KEY`       | api             | from `.env`             |
| `EMAIL_FROM`          | api             | from `.env`             |
| `NEXT_PUBLIC_API_URL` | web (build arg) | `http://localhost:8000` |
| `NODE_ENV`            | web             | `production`            |
| `PORT`                | web             | `3000`                  |
