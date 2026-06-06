# Authentication Flow

How authentication works across the backend (FastAPI) and frontend (Next.js + NextAuth.js).

## Backend auth (FastAPI)

### Register

1. `POST /auth/register` receives `{name, email, password}`.
2. The request schema validates `email` as a real address (`EmailStr`) and normalizes it to lowercase, and enforces a 12-character minimum password — invalid input returns 422.
3. Checks if email already exists — returns 409 if taken. The lookup lowercases the email, so `Foo@x.com` and `foo@x.com` are the same account.
4. Checks the password against the HIBP Pwned Passwords range API (k-anonymity: SHA-1 the password, send only the first 5 hex chars, match the returned suffixes locally). A confirmed breach returns 400; if HIBP is unreachable the check fails open so an external outage never blocks signup.
5. Hashes password with bcrypt (`bcrypt.gensalt()` — default 12 rounds).
6. Creates user via `user_repository.create()`, commits.
7. Generates JWT and returns `{access_token, expires_in}`.

### Login

1. `POST /auth/login` receives `{email, password}`.
2. The request schema validates and lowercases `email` (`EmailStr`), so login is case-insensitive in the address.
3. Looks up user by email. Verifies password with `bcrypt.checkpw()`.
4. Returns 401 if user not found or password mismatch.
5. Generates JWT and returns `{access_token, expires_in}`.

### Logout

1. `POST /auth/logout` (requires auth).
2. Increments `user.session_epoch` by 1 and saves.
3. All existing JWTs for that user become invalid (their `session_epoch` claim no longer matches).

### Me

`GET /auth/me` returns `{uid, email, name, plan}` for the authenticated user.

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
4. Fetches user from DB by ID.
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
- **Verification flow:** extract prefix from the Bearer token → query `api_keys` table by prefix (indexed, O(1)) → bcrypt-verify the full key against matching candidates. This avoids scanning all keys.
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
  → meRequest(access_token)              // GET /auth/me → {uid, email, name, plan}
  → returns User object to NextAuth with accessToken + expiresIn
```

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
