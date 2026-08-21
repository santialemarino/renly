# Authentication Flow

How authentication works across the backend (FastAPI) and frontend (Next.js + NextAuth.js).

## Backend auth (FastAPI)

### Register (anti-enumeration, AUTH-5)

1. `POST /auth/register` receives `{name, email, password, invite_token?, language?}`. `language` is the web's active UI locale (`en` or `es`); it seeds the new user's stored language preference and localizes the verification email. Unsupported values are ignored (coerced to null) so a stray value never 422s signup.
2. The request schema validates `email` as a real address (`EmailStr`) and normalizes it to lowercase, and enforces a 12-character minimum password — invalid input returns 422.
3. **Invite gate (`SIGNUP_MODE`):** in `invite` mode (default), a valid, unconsumed, unexpired invite whose email matches the registering address is **required** — otherwise `403` (`InvalidInviteError`). It is validated first (the access gate), and consumed on success. In `open` mode the gate is skipped. The invite check only inspects the invite token + its bound email, so it never reveals whether the address already has an account — the uniform-`202` property below is preserved. See **Invite-only access gate** below.
4. Checks the password against the HIBP Pwned Passwords range API (k-anonymity: SHA-1 the password, send only the first 5 hex chars, match the returned suffixes locally). A confirmed breach returns 400; if HIBP is unreachable the check fails open. This runs **before the existing-email branch** and is email-independent, so rejecting a breached password leaks nothing about the address.
5. **Always returns a uniform `202`** with a generic acknowledgement — the response never reveals whether the email already has an account (AUTH-5, completed in M2). Behind that uniform response:
   - **New address:** creates an **unverified** user (`bcrypt.gensalt()`, default 12 rounds), issues an `email_verification` token, and emails a verification link.
   - **Existing address:** creates nothing and emails a "you already have an account" notice (with a login link, no token).
   - (In invite mode, the matched invite is consumed in **both** branches, so the outcome shape is identical regardless of whether the address was already registered.)
6. Registration does **not** auto-login — the account is unverified and login is gated on verification (see Login). The user clicks the emailed link, then logs in.
7. Runs on the **privileged session** (`DATABASE_ADMIN_URL`): there is no user context yet and the new row's id can't satisfy the `users` RLS policy, so the insert + email lookup bypass RLS (SEC-15).

### Login

1. `POST /auth/login` receives `{email, password}`.
2. The request schema validates and lowercases `email` (`EmailStr`), so login is case-insensitive in the address.
3. Looks up user by email on the **privileged session** (`DATABASE_ADMIN_URL`) — the lookup is pre-auth, so it bypasses the `users` RLS policy (SEC-15). Verifies password with `bcrypt.checkpw()`.
4. Returns 401 if user not found or password mismatch.
5. Returns **403** (`EmailNotVerifiedError`) if the password is correct but `email_verified_at` is null — the email must be verified first (AUTH-1). Accounts created before email verification existed were grandfathered as verified by the `0004` migration, so they are unaffected.
6. Generates a short-lived access token (JWT) **and** issues a refresh token (AUTH-7), returning `{access_token, expires_in, refresh_token, refresh_expires_in}`. `remember_me: true` in the body gives the refresh token the long window; otherwise it gets the short one (see Refresh below).

### Password hashing & timing

- **bcrypt off the event loop.** `verify_password` / `hash_password` (and the API-key `verify_api_key` / `create_key` hashes) run their ~250 ms cost-12 bcrypt work via `asyncio.to_thread`, so a login burst never serializes the single-worker event loop.
- **Login timing equalization (AUTH-5).** When the email has no account, login still runs one dummy `verify_password` against a fixed `DUMMY_PASSWORD_HASH`, so "unknown email" costs the same bcrypt time as "wrong password" — no response-time enumeration oracle. Registration is equalized the complementary way (hash before the duplicate-email check).
- **Fire-and-forget sends.** `request_verification_email` and `request_password_reset` schedule the provider send as a background task rather than awaiting it, so the uniform `202` answers in constant time whether or not an email is actually sent. (Register and email-change both send on every branch, so their awaited sends are already uniform.)

### Invite-only access gate (admin invites)

The access control between "my friends" and the public for the invited beta. `SIGNUP_MODE` (default `invite`) decides whether registration is gated; only `invite` is used at launch (the public-open flip + a CAPTCHA are a later milestone).

- **Admin = `users.is_admin`** — a plain boolean (NOT NULL default false), not a role system. Any number of users can be admins (flag each row). The `AdminUser` dependency (`app/deps/auth.py`) is `CurrentUser` + an `is_admin` check → `403` otherwise.
- **`invites` table** — one invite per email (`email` unique, lowercased), following the `auth_tokens` pattern: only the **SHA-256 hash** of the raw token (`secrets.token_urlsafe(32)`) is stored, single-use (`consumed_at`), time-limited (`expires_at`, 7 days). `status` is `pending` / `accepted` / `revoked`; an expired link is a pending invite past `expires_at` (derived, shown to admins as "expired", not stored). `invited_by` references the admin. Under RLS keyed on `invited_by` as defense-in-depth — every invite flow runs on the **privileged session** (admin reads span all invites; the register/signup-context lookups are pre-auth), so the real gate is `is_admin` at the endpoint.
- **Admin endpoints** (`/admin`, all `AdminUser`-gated, privileged session):
  - `POST /admin/invites` `{email}` — creates (or re-arms an existing invite for that email), stores the token hash, emails the signup link. `409` if the email already has an account.
  - `GET /admin/invites` — lists every invite with its effective status, sent (created) and accepted (consumed) timestamps.
  - `POST /admin/invites/{id}/resend` — rotates the token, restarts the window, re-sends the link. `404` unknown, `409` if already accepted.
  - `POST /admin/invites/{id}/revoke` — sets `revoked` so the link stops working. `404` unknown, `409` if already accepted.
- **Accept flow** — the emailed link is `{WEB_BASE_URL}/signup?invite=<raw_token>`. `GET /auth/signup-context?invite=<token>` (pre-auth, privileged session) returns `{signup_mode, invited_email}`: in invite mode a valid token resolves the bound email (so the signup form locks to it), an invalid/missing token returns `invited_email: null` (the web shows an invite-only screen — **no open form**, preserving the AUTH-5 anti-enumeration property). `POST /auth/register` then re-validates the token + email match server-side and consumes it.
- **Account-deletion cleanup** — deleting an account also removes the invite that created it (matched by email), so a deleted account leaves no orphaned `accepted` invite in the admin list. The invite is FK'd to the inviting admin (not the invitee), so it's unreachable from the user's own RLS-scoped session and is cleared on the **privileged session** — ordered before the account delete so a partial failure can't strand the orphan. Changing an account's email does **not** touch the invite: the freed old address can simply be re-invited (which re-arms the row).
- **First-admin bootstrap** — with invite mode on and no admin/invite yet, nobody can self-register, so the **first admin is set directly** in the database (a one-off, run with the privileged/owner role):

  ```sql
  UPDATE users SET is_admin = true WHERE email = 'you@example.com';
  ```

  Add more admins by flagging more rows the same way. After that, admins invite everyone else from `/admin`.

### Refresh / session continuity (AUTH-7)

The access token is short-lived (`JWT_EXPIRE_MINUTES`, default 30 min); a **rotating refresh token** keeps the session alive without re-login. `POST /auth/refresh` `{refresh_token}` returns a fresh `{access_token, expires_in, refresh_token, refresh_expires_in}`.

- **Storage:** refresh tokens live in their own `refresh_tokens` table, mirroring `auth_tokens` — only the **SHA-256 hash** of the high-entropy raw token (`secrets.token_urlsafe(32)`) is stored. Each row carries a `family_id` (one login's rotation lineage), the `session_epoch` it was minted under, `remember_me`, `expires_at`, and `consumed_at`/`revoked_at`.
- **Rotation + reuse-detection:** refresh is single-use. A valid token is marked `consumed_at` and its successor minted in the same family. Re-presenting an already-consumed token within a short grace window (30 s) is treated as a benign replay and returns a fresh rotation (this absorbs NextAuth's App-Router races, where middleware refreshes for the response while the same request's RSC tree still holds the pre-rotation cookie); **beyond** the grace window it is treated as theft and the **whole family is revoked**.
- **Revocation tied to `session_epoch`:** a refresh only succeeds when the token's `session_epoch` still matches the user's. Any epoch bump (logout, password reset, password/email change) therefore invalidates every outstanding refresh token, exactly like it invalidates access tokens.
- **Lifetimes:** `remember_me` selects the (sliding) window — `REFRESH_TOKEN_REMEMBER_DAYS` (30 d) for a remembered login, `REFRESH_TOKEN_DEFAULT_HOURS` (2 h) otherwise. The default window is kept tight so an unchecked login on a shared computer doesn't linger long after the visit. When the refresh token itself expires, the user logs in again.
- **Session:** `/auth/refresh` is pre-auth (it carries a refresh token, not an access token), so it runs on the **privileged session** like login. Returns **401** when the token is unknown, expired, revoked, reused, or epoch-stale. A `delete_expired_by_user` purge runs on every login **and on each rotation**, so even a long-lived "remember me" session that never logs in again stays bounded; a global periodic purge that also reaps tokens for users who stop refreshing entirely is a follow-up (INFRA-10).

### Logout

1. `POST /auth/logout` (requires auth).
2. Increments `user.session_epoch` by 1 and saves.
3. All existing JWTs for that user become invalid (their `session_epoch` claim no longer matches), and so do all outstanding refresh tokens (their `session_epoch` no longer matches on the next `/auth/refresh`).

### Me

`GET /auth/me` returns `{uid, email, name, plan, email_verified, is_admin}` for the authenticated user. `is_admin` is carried into the NextAuth session (set at login) so the web can render admin-only UI (the sidebar "Invite people" group) without an extra call — a promotion takes effect on next login.

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

`auth_tokens` (and `refresh_tokens`, AUTH-7) are under RLS keyed on `user_id` like every other user-owned table; in practice every flow that touches them runs on the privileged (owner) session and bypasses RLS — the pre-auth flows have no user context (login issues a refresh token before any request-session context exists; `/auth/refresh` carries a refresh token, not an access token), and the authenticated email-change request uses the privileged session so its target-address availability check can see other accounts. The per-user policies are defense-in-depth (SEC-15).

### Transactional email localization

Transactional emails are the one place the backend produces user-facing prose (there is no frontend renderer for them), so — unlike every other API response, which stays locale-agnostic — they are localized to the recipient's language. The builders in `app/services/email_templates.py` carry a plain Python `en`/`es` catalog (subject + body per template, no new dependency) and take a `locale`; an unknown locale falls back to English per string. Locale resolution per flow:

- **Signup verification** uses the `language` the web passes to `/auth/register` (also seeded onto the new user's settings for later emails).
- **Existing-user flows** (resend verification, password reset, email-change confirmation) read the user's stored `user_settings.settings->>'language'` via `settings_service.get_user_language`.
- **Anti-enumeration sends** (account-exists, email-change-taken) use the **default** locale — they must not reveal the target account's stored language.
- **Invites** use the inviting admin's stored language.
- The **feedback notification** (admin-facing) is localized to each admin's stored language, with the category label translated; admin languages are batch-loaded (one query) to avoid an N+1.

## JWT structure

**Payload fields:**

| Field           | Type | Description                                    |
| --------------- | ---- | ---------------------------------------------- |
| `sub`           | str  | User ID (as string)                            |
| `email`         | str  | User email                                     |
| `session_epoch` | int  | Monotonic counter — incremented on each logout |
| `exp`           | int  | Expiration timestamp (UTC)                     |

**Configuration** (from `app/config.py`, sourced from `.env`):

| Setting                       | Default  | Description                                         |
| ----------------------------- | -------- | --------------------------------------------------- |
| `JWT_SECRET`                  | required | Signing key (must match `NEXTAUTH_SECRET`)          |
| `JWT_ALGORITHM`               | `HS256`  | HMAC-SHA256                                         |
| `JWT_EXPIRE_MINUTES`          | `30`     | Access token lifetime (short; refreshed via AUTH-7) |
| `REFRESH_TOKEN_REMEMBER_DAYS` | `30`     | Refresh token lifetime for a "remember me" login    |
| `REFRESH_TOKEN_DEFAULT_HOURS` | `2`      | Refresh token lifetime for an ordinary login        |

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

Every user-owned table has `ENABLE ROW LEVEL SECURITY` plus a policy `USING`/`WITH CHECK` that the row's owner equals `app_current_user_id()` — a helper returning `NULLIF(current_setting('app.current_user_id', true), '')::bigint`, which is `NULL` when no context is set, so a context-less connection matches **no rows** (rather than erroring). `users` keys on its own `id`; the hot child tables (`transactions`, `investment_snapshots`, `card_settlements`) carry a denormalized `user_id` so their policy is a direct column check; `investment_collection_members` (a pure junction) uses an `EXISTS`-join to the parent investment. The global reference tables (`exchange_rates`, `asset_prices`, `cedear_ratios`) are keyed by pair/ticker, not by user, and are intentionally left without RLS.

---

## Frontend auth (NextAuth.js)

### Configuration (`auth.config.ts`)

- **Provider:** `Credentials` (email + password).
- **Session strategy:** `jwt` (stateless, no DB session on the frontend).
- **Secret:** `NEXTAUTH_SECRET` env var — must match the backend's `JWT_SECRET`.
- **Custom sign-in page:** configured via `pages.signIn`.

### Login flow

```
User submits email + password (+ "Remember me")
  → NextAuth Credentials.authorize()
  → loginRequest(email, password, rememberMe)  // POST /auth/login → {access_token, expires_in, refresh_token, refresh_expires_in}
  → meRequest(access_token)                     // GET /auth/me → {uid, email, name, plan, email_verified}
  → returns User object to NextAuth with accessToken + expiresIn + refreshToken + refreshExpiresIn
```

The login form has a **Remember me** checkbox (in the row beside "Forgot your password?"); its value is passed through `signIn` → `authorize` → `loginRequest` so the backend sizes the refresh-token window.

Login can also fail with **403** when the email isn't verified yet (`loginRequest` returns null for any non-OK status, so NextAuth surfaces a generic credentials error); the login page links to **Forgot password** and signup users land on a "check your email" screen they can resend from.

### Account-lifecycle pages

- `app/(auth)/forgot-password`, `app/(auth)/reset-password`, `app/(auth)/verify-email` — unauthenticated pages (in `AUTH_ROUTES`) for the reset and verification flows. `verify-email` and `reset-password` read the `?token=` query param; `verify-email` confirms on mount (and does **not** redirect logged-in users, since email-change confirmation happens while authenticated).
- `app/(protected)/account` — the account-settings surface (in the sidebar Settings group): change email, change password, and a danger zone (export data + delete account). Sensitive mutations go through `account-actions.ts` server actions; after a password change or account deletion the client signs out and returns to login (the server bumped `session_epoch` / removed the account).
- Unauthenticated API calls live in `lib/auth-api.ts` (register, login, forgot/reset, verification request/confirm); `registerRequest` now returns no token (uniform `202`) and the signup form shows a "check your email" screen instead of auto-logging in.

### JWT callback

On initial sign-in, stores `uid`, `email`, `name`, `accessToken`, `accessTokenExpires` (computed as `Date.now() + expiresIn * 1000`), `refreshToken`, and `refreshTokenExpires` in the NextAuth JWT. The refresh token stays **inside the encrypted NextAuth JWT and is never exposed to the session** (the client only ever sees the access token).

On subsequent requests, if the access token is still valid (with a 60 s skew) the token is returned unchanged. Otherwise the callback **silently renews** it via `refreshRequest(refreshToken)` → `POST /auth/refresh`, storing the new access token + the rotated refresh token. The renewal runs on every navigation through the NextAuth middleware (`proxy.ts`). Only when there is no usable refresh token, or the backend rejects it (expired / revoked / reused / epoch-stale → 401), does the callback set `error: 'SessionExpired'`, which the authorized callback turns into a redirect to login.

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

Runs on every navigation (the `proxy.ts` middleware) as the **optimistic** edge check — `app/(protected)/layout.tsx`'s `getSession()` is the authoritative guard. Auth pages (`AUTH_ROUTES`) and public pages (`PUBLIC_ROUTES` — the marketing landing + legal pages) are always accessible. A logged-out (or session-errored) visitor is redirected to login **only on a `PROTECTED_ROUTES` match**; any other (unknown) path falls through so Next renders the 404 (`not-found.tsx`) instead of bouncing a mistyped URL to login. `PROTECTED_ROUTES` (`config/routes.ts`) is the computed complement `ROUTES − AUTH_ROUTES − PUBLIC_ROUTES`, so a new route added to `ROUTES` is protected by default. Because the layout guard is authoritative, a protected route missing from `PROTECTED_ROUTES` still can't leak — it just isn't short-circuited at the edge.

The public pages render in **any** auth state — only the auth forms (`/login`, `/signup`) redirect logged-in users away. The marketing landing and `PublicHeader` read the session server-side to swap their CTAs to a single "Go to Dashboard" link for logged-in visitors (and hide the signup-conversion block); the global 404 (`not-found.tsx`) does the same, adding a "Go to Dashboard" CTA alongside "Go to Homepage" when authenticated.

**Invite-only mode (frontend):** `/admin` is a protected route, so logged-out users hit `/login` like any protected route; a logged-in **non-admin** who reaches it gets a real `404` — the page calls `notFound()` when `GET /admin/invites` returns `403`, hiding the page's existence rather than showing a `403`. Admins reach it from an **Administration → Invite people** group in the sidebar (between Investor and Settings), rendered only when `session.user.isAdmin` is true. Both the sidebar item **and the `/admin` page itself** are gated to `invite` mode — in `open` mode there's no one to invite, so the item hides and the page is a real `404` for everyone. The page's resend/create also carries a client-side 30s cooldown per invite (mirroring the auth resend cooldown), on top of the server `INVITE_LIMIT`. `/signup` reads `getSignupContext()` server-side: with a valid invite token it renders the form with the email **locked** to the invited address; without one (in invite mode) it renders an **invite-only notice with no form** (so an uninvited visitor can't submit an email — preserving anti-enumeration). The landing, `PublicHeader`, and closing CTA read the signup mode and label their signup CTA **"Request access"** in invite mode (it routes to the invite-only screen) instead of implying open registration.

### Logout flow

```
userSignOut()                    // server action in auth.ts
  → auth() to get current session
  → logoutRequest(accessToken)   // POST /auth/logout (bumps session_epoch)
  → signOut({ redirect: false }) // clears NextAuth session
  → cookies().delete('NEXT_LOCALE') // drop the locale cookie so the next logged-out visitor gets
                                    // their own browser language (re-applied on login from settings)
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
- **Refresh tokens (AUTH-7):** a short access token is paired with a rotating, single-use refresh token (stored as a SHA-256 hash in `refresh_tokens`). Rotation + reuse-detection means a stolen-and-replayed token (outside a 30 s grace window) revokes the whole family; the access token is only useful for `JWT_EXPIRE_MINUTES`. The refresh token is held only inside the encrypted NextAuth JWT, never exposed to the client session. See **Refresh / session continuity** above.
- `session_epoch` provides immediate token revocation on logout without a blocklist — it invalidates outstanding **access and refresh** tokens alike (a refresh only succeeds while its minted-at epoch matches the user's).
- `trustHost: true` is set in NextAuth config (required for non-Vercel deployments).
- **Rate limiting (SEC-1):** all routes share a global default limit, with tighter per-route limits on the credential-accepting auth endpoints (`POST /auth/login`, `POST /auth/register`) to slow brute-force and account-flooding. The limiter keys by authenticated user id when a valid bearer token is present, otherwise by client IP; exceeding a limit returns a generic `429` with a `Retry-After` header. The client IP is the connection peer by default; when deployed behind a reverse proxy set `TRUSTED_PROXY_COUNT` to the proxy hop count so the real client IP is read from `X-Forwarded-For` (otherwise every client collapses onto the proxy address and shares one bucket). In-memory storage for now (single instance) — swap to Redis when scaling out. Configured in `app/rate_limit.py`.
- **Registration never reveals which emails have accounts** (AUTH-5, completed in M2): a uniform `202` for every attempt, with a verification link emailed to a new address and a "you already have an account" notice to an existing one. The same uniform-response treatment covers `verify-email/request`, `forgot-password`, and `change-email`. Account emails go through a swappable `EmailService` port (`EMAIL_PROVIDER`: `console`/`resend`); single-use, time-limited tokens are stored as SHA-256 hashes in `auth_tokens`. Email verification gates login; password reset and password change bump `session_epoch` to invalidate existing sessions.
- **Perimeter (SEC-7/8/9/12):** in `production` (`ENVIRONMENT=production`) the API docs (`/docs`, `/redoc`, `/openapi.json`) are disabled and debug is off; a catch-all handler returns a generic `500` (`{"detail": "Internal server error."}`) with no stack trace. CORS origins are env-driven (`CORS_ORIGINS`). A request body-size limit (`BodySizeLimitMiddleware`, 1 MiB) rejects oversized payloads with `413` — both an oversized declared `Content-Length` and bodies that exceed the cap while streaming (so chunked requests without a `Content-Length` can't bypass it).
