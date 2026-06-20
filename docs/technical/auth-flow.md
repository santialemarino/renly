# Authentication Flow

How authentication works across the backend (FastAPI) and frontend (Next.js + NextAuth.js).

## Backend auth (FastAPI)

### Register (anti-enumeration, AUTH-5)

1. `POST /auth/register` receives `{name, email, password}`.
2. The request schema validates `email` as a real address (`EmailStr`) and normalizes it to lowercase, and enforces a 12-character minimum password — invalid input returns 422.
3. Checks the password against the HIBP Pwned Passwords range API (k-anonymity: SHA-1 the password, send only the first 5 hex chars, match the returned suffixes locally). A confirmed breach returns 400; if HIBP is unreachable the check fails open. This runs **first** and is email-independent, so rejecting a breached password leaks nothing about the address.
4. **Always returns a uniform `202`** with a generic acknowledgement — the response never reveals whether the email already has an account (AUTH-5, completed in M2). Behind that uniform response:
   - **New address:** creates an **unverified** user (`bcrypt.gensalt()`, default 12 rounds), issues an `email_verification` token, and emails a verification link.
   - **Existing address:** creates nothing and emails a "you already have an account" notice (with a login link, no token).
5. Registration does **not** auto-login — the account is unverified and login is gated on verification (see Login). The user clicks the emailed link, then logs in.
6. Runs on the **privileged session** (`DATABASE_ADMIN_URL`): there is no user context yet and the new row's id can't satisfy the `users` RLS policy, so the insert + email lookup bypass RLS (SEC-15).

### Login

1. `POST /auth/login` receives `{email, password}`.
2. The request schema validates and lowercases `email` (`EmailStr`), so login is case-insensitive in the address.
3. Looks up user by email on the **privileged session** (`DATABASE_ADMIN_URL`) — the lookup is pre-auth, so it bypasses the `users` RLS policy (SEC-15). Verifies password with `bcrypt.checkpw()`.
4. Returns 401 if user not found or password mismatch.
5. Returns **403** (`EmailNotVerifiedError`) if the password is correct but `email_verified_at` is null — the email must be verified first (AUTH-1). Accounts created before email verification existed were grandfathered as verified by the `0004` migration, so they are unaffected.
6. Generates JWT and returns `{access_token, expires_in}`.

### Logout

1. `POST /auth/logout` (requires auth).
2. Increments `user.session_epoch` by 1 and saves.
3. All existing JWTs for that user become invalid (their `session_epoch` claim no longer matches).

### Me

`GET /auth/me` returns `{uid, email, name, plan, email_verified}` for the authenticated user.

### Email verification (AUTH-1)

A generic, single-use, time-limited token table (`auth_tokens`) backs verification, reset, and email change. Only the **SHA-256 hash** of the high-entropy raw token (`secrets.token_urlsafe(32)`) is stored — the raw value lives only in the emailed link. `consumed_at` enforces single use; `expires_at` bounds validity (verification/email-change 24h, reset 1h). Issuing a new token of a type invalidates the user's prior unconsumed tokens of that type.

- `POST /auth/verify-email/request` `{email}` — (re)sends a verification link. Uniform `202`; a no-op when the address has no account or is already verified (never reveals account state).
- `POST /auth/verify-email/confirm` `{token}` — consumes the token. One endpoint serves both flows, dispatching on the token type: an `email_verification` token sets `email_verified_at`; an `email_change` token switches `email` to the pending address, sets `email_verified_at`, and bumps `session_epoch`. Returns `{detail, token_type}`. Invalid/expired/used → 400.

These run on the **privileged session** (pre-auth — the user may not be logged in when clicking the link).

### Password reset (AUTH-2)

- `POST /auth/forgot-password` `{email}` — sends a reset link. Uniform `202`; a no-op when the address has no account.
- `POST /auth/reset-password` `{token, password}` — consumes the `password_reset` token, rejects breached passwords (HIBP), sets the new hash, and **bumps `session_epoch`** so every existing session is invalidated. Invalid/expired/used token or breached password → 400.

Both run on the privileged session (pre-auth).

### Account self-service (`/me` router — AUTH-8 / AUTH-6)

Authenticated endpoints; each sensitive action re-verifies the current password (`InvalidCredentialsError` → 401).

- `POST /me/change-password` `{current_password, new_password}` — verifies the current password, rejects breached new passwords, updates the hash, and bumps `session_epoch` (logs out other sessions). The web signs the user out afterward to re-login.
- `POST /me/change-email` `{current_password, new_email}` — verifies the password, then emails a confirmation link to the new address (or a "this email already has an account" notice if it's taken). Uniform `202`. The address only switches when the link is confirmed via `verify-email/confirm`. Runs the availability check on the **privileged session** so it can see every account (RLS would otherwise hide other users' rows).
- `GET /me/export` — returns the user's full data set as a downloadable JSON document (`Content-Disposition: attachment`). Excludes the password hash and api-key hashes/prefixes.
- `DELETE /me` `{password, confirmation}` — verifies the password and a typed confirmation matching the account email, then deletes the user. FK `ON DELETE CASCADE` removes every owned row. The web signs out and returns to login.

`auth_tokens` is under RLS keyed on `user_id` like every other user-owned table; the pre-auth flows operate on the privileged (owner) session, the authenticated email-change request creates its token on the request session where the policy permits the user's own row (SEC-15).

## JWT structure

**Payload fields:**

| Field           | Type | Description                                    |
| --------------- | ---- | ---------------------------------------------- |
| `sub`           | str  | User ID (as string)                            |
| `email`         | str  | User email                                     |
| `session_epoch` | int  | Monotonic counter — incremented on each logout |
| `exp`           | int  | Expiration timestamp (UTC)                     |

**Configuration** (from `app/config.py`, sourced from `.env`):

| Setting              | Default  | Description                                |
| -------------------- | -------- | ------------------------------------------ |
| `JWT_SECRET`         | required | Signing key (must match `NEXTAUTH_SECRET`) |
| `JWT_ALGORITHM`      | `HS256`  | HMAC-SHA256                                |
| `JWT_EXPIRE_MINUTES` | `10080`  | 7 days                                     |

**Signing:** `jose.jwt.encode(payload, secret, algorithm="HS256")`.

## Token validation

The `get_current_user()` dependency in `app/deps/auth.py` runs on every protected endpoint:

1. Extracts Bearer token from `Authorization` header via `HTTPBearer()`.
2. Decodes JWT with `jose.jwt.decode()` using `JWT_SECRET` and `HS256`.
3. Extracts `sub` (user ID) and `session_epoch` from the payload.
4. Sets the request's RLS context from the (trusted) token's user id (`set_session_user`), then fetches the user from the DB by ID — the `users` policy lets the user read its own row.
5. Compares token's `session_epoch` with the user's current `session_epoch` — rejects if they differ (token was issued before a logout).
6. Returns the `User` model instance.

Any failure (expired token, invalid signature, missing fields, epoch mismatch, user not found) raises 401 with `"Invalid or expired token"`.

The `CurrentUser` type alias (`Annotated[User, Depends(get_current_user)]`) is used as a parameter type in router functions.

## API key authentication

For external tools (iOS Shortcuts, automations) that can't go through a browser login flow.

### How it works

1. User generates an API key on the Integrations page (API Keys section) — the raw key is shown once in a dialog with a copy button.
2. External tool stores the raw key and includes it as `Authorization: Bearer <key>` on API requests.
3. The server's dual-auth dependency (`JwtOrApiKeyUser` in `app/deps/api_key_auth.py`) tries JWT first, then falls back to API key verification.

### Key storage and verification

- **Raw key:** generated with `secrets.token_urlsafe(32)` (43 characters).
- **Stored as:** bcrypt hash (`key_hash` column) + first 8 characters unencrypted (`key_prefix` column).
- **Verification flow:** extract prefix from the Bearer token → query `api_keys` table by prefix (indexed, O(1)) → bcrypt-verify the full key against matching candidates. This avoids scanning all keys. The prefix lookup runs on the **privileged session** (no user context yet, so it bypasses the `api_keys` RLS policy); once the user is resolved, the request session's RLS context is set to that user (SEC-15).
- **Last used tracking:** `last_used_at` updated on each successful verification.
- **Revocation:** `DELETE /api-keys/{id}` sets `is_active = false` (soft-delete). Revoked keys fail verification immediately.

### Supported endpoints

The following endpoints accept API key auth (used by the iOS Shortcut). All other endpoints require JWT. The `JwtOrApiKeyUser` dependency is used instead of `CurrentUser` on endpoints that support both.

- `POST /expenses` — create an expense from the shortcut.
- `POST /subscriptions` — create a subscription when the shortcut's "Is this a subscription?" toggle is on.
- `POST /installments` — create an installment plan when the shortcut's "Is this an installment?" toggle is on.
- `GET /settings` — fetch shortcut currencies and user preferences.
- `GET /credit-cards` — list cards for the credit card picker in the shortcut.

---

## Database-level isolation (Row-Level Security)

A second, database-enforced isolation layer (SEC-15) sits under the application's `user_id` filters: even if a code path forgets to scope a query, Postgres itself prevents one user from reading or writing another's rows.

### Two roles

- **Restricted request role** (`DATABASE_URL`, e.g. `renly_app`): `NOBYPASSRLS`, not the table owner. Every HTTP request connects as this role, so all policies apply.
- **Privileged owner role** (`DATABASE_ADMIN_URL`): owns the tables and therefore bypasses RLS. Used only for work with no user context — the scheduler, Alembic migrations, and pre-auth lookups (login, register, API-key verification). RLS is `ENABLE`d, not `FORCE`d, precisely so the owner stays exempt.

### Per-request user context

After authentication resolves the user id, `set_session_user()` (`app/db.py`) stashes it on the SQLAlchemy session. An `after_begin` event listener issues `SET LOCAL app.current_user_id = <id>` at the start of **every** transaction on that session — re-applied per transaction because `SET LOCAL` is cleared on `COMMIT` and pooled connections are reused (a service that commits mid-request and then reads would otherwise lose the context). JWT requests set the context from the trusted token before loading the user; the API-key path resolves the user on the privileged session first, then sets the request session's context.

### Policies

Every user-owned table has `ENABLE ROW LEVEL SECURITY` plus a policy `USING`/`WITH CHECK` that the row's owner equals `app_current_user_id()` — a helper returning `NULLIF(current_setting('app.current_user_id', true), '')::bigint`, which is `NULL` when no context is set, so a context-less connection matches **no rows** (rather than erroring). `users` keys on its own `id`; the hot child tables (`transactions`, `investment_snapshots`, `card_settlements`) carry a denormalized `user_id` so their policy is a direct column check; `investment_group_members` (a pure junction) uses an `EXISTS`-join to the parent investment. The global reference tables (`exchange_rates`, `asset_prices`, `cedear_ratios`) are keyed by pair/ticker, not by user, and are intentionally left without RLS.

---

## Frontend auth (NextAuth.js)

### Configuration (`auth.config.ts`)

- **Provider:** `Credentials` (email + password).
- **Session strategy:** `jwt` (stateless, no DB session on the frontend).
- **Secret:** `NEXTAUTH_SECRET` env var — must match the backend's `JWT_SECRET`.
- **Custom sign-in page:** configured via `pages.signIn`.

### Login flow

```
User submits email + password
  → NextAuth Credentials.authorize()
  → loginRequest(email, password)        // POST /auth/login → {access_token, expires_in}
  → meRequest(access_token)              // GET /auth/me → {uid, email, name, plan, email_verified}
  → returns User object to NextAuth with accessToken + expiresIn
```

Login can also fail with **403** when the email isn't verified yet (`loginRequest` returns null for any non-OK status, so NextAuth surfaces a generic credentials error); the login page links to **Forgot password** and signup users land on a "check your email" screen they can resend from.

### Account-lifecycle pages

- `app/(auth)/forgot-password`, `app/(auth)/reset-password`, `app/(auth)/verify-email` — unauthenticated pages (in `AUTH_ROUTES`) for the reset and verification flows. `verify-email` and `reset-password` read the `?token=` query param; `verify-email` confirms on mount (and does **not** redirect logged-in users, since email-change confirmation happens while authenticated).
- `app/(protected)/account` — the account-settings surface (in the sidebar Settings group): change email, change password, and a danger zone (export data + delete account). Sensitive mutations go through `account-actions.ts` server actions; after a password change or account deletion the client signs out and returns to login (the server bumped `session_epoch` / removed the account).
- Unauthenticated API calls live in `lib/auth-api.ts` (register, login, forgot/reset, verification request/confirm); `registerRequest` now returns no token (uniform `202`) and the signup form shows a "check your email" screen instead of auto-logging in.

### JWT callback

On initial sign-in, stores `uid`, `email`, `name`, `accessToken`, and `accessTokenExpires` (computed as `Date.now() + expiresIn * 1000`) in the NextAuth JWT.

On subsequent requests, checks if `accessTokenExpires` has passed. If expired, sets `error: 'SessionExpired'` on the token to force re-login.

There is no token refresh — when the backend JWT expires, the user must log in again.

### Session callback

Maps JWT fields to the session object exposed to components:

```typescript
session.user = {
  id,
  email,
  name,
  accessToken,
  expiresIn,
  error,
};
```

`expiresIn` is recomputed on each session read as seconds remaining.

### Authorized callback

Runs on every navigation (middleware). Auth pages are always accessible. For all other routes, if the user is not logged in or has a session error, redirects to the login page.

### Logout flow

```
userSignOut()                    // server action in auth.ts
  → auth() to get current session
  → logoutRequest(accessToken)   // POST /auth/logout (bumps session_epoch)
  → signOut({ redirect: false }) // clears NextAuth session
  → client handles redirect
```

## Server-side helpers (`lib/auth.ts`)

- `getSession()` — returns the NextAuth session (for server components/actions).
- `getAccessToken()` — extracts `session.user.accessToken` for API calls.

## Security notes

- Emails are validated (`EmailStr`) and stored lowercase; lookups lowercase their input, so accounts are case-insensitive by email and case-variant duplicates cannot be created.
- Registration requires a 12-character minimum password and rejects passwords found in the HIBP Pwned Passwords corpus (queried via k-anonymity; the breach check fails open on HIBP outage).
- bcrypt uses `gensalt()` which defaults to 12 rounds.
- `JWT_SECRET` and `NEXTAUTH_SECRET` **must be the same value** — the backend signs tokens that NextAuth stores and the backend later validates.
- No refresh token mechanism — expiry forces full re-login.
- `session_epoch` provides immediate token revocation on logout without a blocklist.
- `trustHost: true` is set in NextAuth config (required for non-Vercel deployments).
- **Rate limiting (SEC-1):** all routes share a global default limit, with tighter per-route limits on the credential-accepting auth endpoints (`POST /auth/login`, `POST /auth/register`) to slow brute-force and account-flooding. The limiter keys by authenticated user id when a valid bearer token is present, otherwise by client IP; exceeding a limit returns a generic `429` with a `Retry-After` header. The client IP is the connection peer by default; when deployed behind a reverse proxy set `TRUSTED_PROXY_COUNT` to the proxy hop count so the real client IP is read from `X-Forwarded-For` (otherwise every client collapses onto the proxy address and shares one bucket). In-memory storage for now (single instance) — swap to Redis when scaling out. Configured in `app/rate_limit.py`.
- **Registration never reveals which emails have accounts** (AUTH-5, completed in M2): a uniform `202` for every attempt, with a verification link emailed to a new address and a "you already have an account" notice to an existing one. The same uniform-response treatment covers `verify-email/request`, `forgot-password`, and `change-email`. Account emails go through a swappable `EmailService` port (`EMAIL_PROVIDER`: `console`/`resend`); single-use, time-limited tokens are stored as SHA-256 hashes in `auth_tokens`. Email verification gates login; password reset and password change bump `session_epoch` to invalidate existing sessions.
- **Perimeter (SEC-7/8/9/12):** in `production` (`ENVIRONMENT=production`) the API docs (`/docs`, `/redoc`, `/openapi.json`) are disabled and debug is off; a catch-all handler returns a generic `500` (`{"detail": "Internal server error."}`) with no stack trace. CORS origins are env-driven (`CORS_ORIGINS`). A request body-size limit (`BodySizeLimitMiddleware`, 1 MiB) rejects oversized payloads with `413` — both an oversized declared `Content-Length` and bodies that exceed the cap while streaming (so chunked requests without a `Content-Length` can't bypass it).
