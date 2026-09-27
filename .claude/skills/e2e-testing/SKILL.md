---
name: e2e-testing
description: End-to-end browser testing in Renly using Playwright. Use when working on apps/web features, writing E2E tests, or verifying UI behavior with playwright-cli during implementation.
---

# E2E testing (Renly)

End-to-end browser testing with Playwright for `apps/web`. This skill describes how E2E lives in the repo, when to use it, and how to use `playwright-cli` for in-the-loop verification during implementation. For the broader testing context (API unit tests, pytest), see the `testing` skill.

## Architecture

Three layers, independent:

1. **Test library (`@playwright/test`).** Tests live in `apps/web/tests/e2e/`, run with `pnpm test:e2e` from `apps/web/` or via `pnpm --filter web test:e2e` from the repo root. Configured in `apps/web/playwright.config.ts`. This is the deterministic verification contract.
2. **CLI (`@playwright/cli`).** Installed globally on the dev machine. Use during feature implementation to drive a real browser, verify behavior, capture screenshots and videos. Does not produce committed tests by itself; the agent uses it to verify what was built and then writes a corresponding `.spec.ts` if a persistent test is warranted.
3. **CI workflow.** `.github/workflows/ci.web-e2e.yml` runs the whole suite against a production build — on a PR when it touches the floor or carries the `run-e2e` label, every night on `main`, and on demand. See "CI" at the end of this file.

## When to write a Playwright test

Write a `.spec.ts` when:

- A critical user flow needs regression protection (login, transactions, dashboard load).
- A bug was found in a user-facing flow and a test would prevent regression.
- A feature involves multi-step interaction that unit tests cannot cover.

Do not write a `.spec.ts` when:

- The change is backend-only, API-only, or docs-only.
- The change is a tiny visual tweak with no behavioral impact.
- The flow is covered by an existing test (extend instead of duplicating).

## Where tests live

```
apps/web/
├── playwright.config.ts
├── tests/
│   └── e2e/
│       ├── <feature>.spec.ts
│       └── helpers/
│           └── <name>.ts
└── package.json   # scripts: test:e2e, test:e2e:ui, etc.
```

- One file per feature or flow. Kebab-case names: `login.spec.ts`, `create-investment.spec.ts`.
- Helpers (factories, fixtures, auth setup) under `tests/e2e/helpers/`.
- No grouping by type (no `smoke/`, no `regression/`) — use Playwright `@tag` annotations on tests instead when categorization is needed.

## Running tests

**First-time setup (one-off per machine):** browser binaries are not part of `pnpm install`. Run once:

```bash
pnpm --filter web exec playwright install chromium
```

From `apps/web/`:

```bash
pnpm test:e2e             # headless, single browser
pnpm test:e2e:ui          # Playwright UI mode (recommended for development)
pnpm test:e2e:headed      # headless: no, visible browser
pnpm test:e2e:debug       # Playwright Inspector
pnpm test:e2e:report      # open last HTML report
```

Prerequisite: dev server must be running. In another terminal, from the repo root:

```bash
pnpm dev
```

If `pnpm dev` settles on a port other than 3000 (e.g. Next auto-bumps to 3001 when 3000 is busy), pass `PLAYWRIGHT_BASE_URL=http://localhost:<port>` when running tests. An empty `PLAYWRIGHT_BASE_URL=""` falls back to the default.

**While iterating, run only what the change touches**, and read the failure as it happens:

```bash
pnpm test:e2e tests/e2e/a11y-routes.spec.ts --reporter=line -x   # one spec, stop at the first failure
pnpm test:e2e --grep "@a11y" --reporter=line                     # every spec with a tag
pnpm test:e2e --grep "/expenses" --reporter=line                 # tests whose title matches
pnpm test:e2e --last-failed --reporter=line                      # re-run only what failed last time
```

`--reporter=line` prints one line per test and the full error at the failure, instead of the list
reporter's wall; `-x` (`--max-failures=1`) stops the run there. The full suite is not run locally —
CI runs it (see "CI").

**To run the AUTHENTICATED specs, name an account:**

```bash
E2E_EMAIL=you@example.com E2E_PASSWORD=... pnpm test:e2e
```

Without both, the `chromium-authenticated` project does not exist and only the signed-out specs run —
the suite still exits 0. See "Auth and storage state" below.

**They are shell vars, and deliberately NOT in `.env`.** Playwright reads no dotenv file, so a value
placed in `apps/web/.env` looks configured and reaches nothing. They also stay out of `.env.example`
for the same reason the API's four `*_TEST_DATABASE_URL` vars do: they are per-developer test
credentials rather than deploy-time configuration, and one of them is a real password.

**`E2E_API_URL`** joins them. `globalSetup` reads it on every run to check the API is up before any
test starts, and specs use it when they assert something the DOM cannot show — a figure the page
abbreviates, or two endpoints that must agree — or seed data they are not testing. It defaults to `http://localhost:8000`, so it
is optional, and it stays out of both env files for the same reason the two above do. A spec reaching
the API gets its bearer token from `apiToken()` in `tests/e2e/helpers/api.ts` (which also exports
`API_BASE`). That reads the token from the session globalSetup saved, via NextAuth's
`/api/auth/session`, and never calls `POST /auth/login`. The API allows five logins a minute, and
Playwright restarts the worker after every failed test, re-running each `beforeAll`. A spec that logged
in there turned a handful of real failures into a wall of `429`s that hid the regression.

**`CI` env var:** the config respects `CI=true`/`1`/`yes` (case-insensitive truthy) to enable `forbidOnly` + `retries: 2`. Explicit `CI=false` or `CI=0` opts out, even though they are non-empty strings. In CI the config also adds the `github` and `json` reporters (see "CI").

## Conventions

### Selectors

Order of preference:

1. `getByTestId('...')` using `data-testid` attributes added explicitly to elements.
2. `getByRole('button', { name: 'Save' })` for semantic elements with clear accessible names.
3. `getByText('...')` only when the text is stable, untranslated, and unambiguous.
4. CSS selectors as last resort.

**`data-testid` is a forward-going convention.** Most components still carry none. When writing a new
spec, add the testids you need to the components it touches as part of the same PR. Naming convention:
kebab-case, scoped to context: `login-email-input`, `investment-create-submit`. Treat the testid addition
as a normal frontend change (commit it alongside the spec).

Two things about where the attribute goes:

- **A shared primitive takes ONE testid, not one per call site.** `ConfirmDialog`'s confirm button
  carries `confirm-dialog-confirm`, so every destructive confirm in the app is already reachable.
- **A component whose props are an explicit list will not forward it.** `LocaleAmountInput`,
  `RowActionButton` and `StyledHint` all declare their props rather than extending React's, so
  `data-testid` is a type error until the prop is declared — each takes it as `testId` because each
  chooses which element to put it on. Prefer that over keying on an accessible name: those are
  translated, so `getByRole('button', { name: 'Delete' })` passes only in whichever locale the run
  happened to load, and silently matches nothing in the other.
- **A testid can be DERIVED from a prop the primitive already has.** Every `DismissableHint` renders
  `hint-<storageKey>`, so all of the app's contextual nudges are reachable from one definition instead
  of a testid per call site — the currency hint is `hint-currency-hint-dismissed`. Reach for this
  whenever a family of instances is already distinguished by a prop.

### Auth and storage state — how the harness actually works

Two projects over one `testDir`, split by FILE NAME:

- **`chromium`** runs everything that is not `*.auth.spec.ts` — the signed-OUT specs. It carries a
  `testIgnore` on that pattern rather than merely omitting a `testMatch`, because a project without one
  matches every file in `testDir`, so the authenticated specs would otherwise run a second time with no
  session and fail on pages they never reach.
- **`chromium-authenticated`** runs `*.auth.spec.ts` with the storage state below, and **exists only
  when `E2E_EMAIL` and `E2E_PASSWORD` are set**. Unset, the project is absent and the suite still exits
  0 on the logged-out specs — the same env-gating the API's `tests/integration/` suites use, and for the
  same reason: a fresh clone has no seeded account, and a suite that fails there teaches people to
  ignore it. `tests/e2e/helpers/auth.ts` reads both vars, so the config and the setup can never
  disagree about whether to run.

`globalSetup` (`tests/e2e/global-setup.ts`) logs in ONCE and saves the browser state to
`tests/e2e/.auth/storage-state.json` (gitignored — it holds a live session cookie). It **drives the real
login form** rather than posting to NextAuth's credentials callback, which is a deliberate deviation
from the obvious "authenticate programmatically": the callback needs a CSRF token paired with its own
cookie and the session cookie's name depends on whether the origin is secure, so a protocol-level login
is three assumptions about a library's internals, each of which fails by returning 200 and no session.
One scripted form submission per run costs a second and assumes nothing. The login fields therefore
carry testids (`login-email-input`, `login-password-input`, `login-submit`) like any other spec target.

**Verify the session in `globalSetup`, and say what failed.** Rejected credentials never leave `/login`,
so the wait for a URL change times out — catch it and re-throw naming the cause, because a bare
`waitForURL exceeded` names a symptom. Then load a protected route and check it did not bounce back,
which catches the other failure (accepted, then unusable — an unverified account, a stale epoch). Saving
an unauthenticated state instead makes every authenticated spec fail as a redirect to `/login`, N
confusing failures away from the one real cause. Delete any stale state file before starting, so a
failed setup cannot leave the previous run's session for the next one to load.

Login flow tests are the exception to reusing the state — they exercise the UI auth path.

### Seed data

Tests do not assume preexisting state, and an authenticated spec runs against a REAL account with real
history — so it must also never depend on, or leave behind, a row of its own. Factories live in
`apps/web/tests/e2e/helpers/factories.ts` and the pattern is a **marker**: a per-run unique string
written into a free-text field (an expense's notes), with every assertion and every cleanup scoped to
the row carrying it. That is what removes the need for an id, since the marker comes back on the list
page as something a locator can find. The flow a spec is TESTING goes through the UI, create and
cleanup alike. Data it is NOT testing, such as the group and collection a layout sweep needs on screen,
may be seeded and removed through the API (`helpers/api.ts`), which is faster and deterministic, and it
is still marked. Either way, clean up in a `finally` or an `afterAll`, and make the cleanup a no-op when
the row is already gone so it is safe to call unconditionally.
A spec that temporarily changes ACCOUNT STATE rather than adding a row (a setting such as
`onboarding_completed`) reads the value first and restores it in `afterAll` — and a run killed before
`afterAll` can leave it changed, so check that setting on the account before trusting the next run.

**A round trip is ONE test, not two.** Splitting create and delete across tests makes the second depend
on the first having run — which `workers: 1` happens to guarantee today and no spec should rely on.

### Text that must not be cut off

`tests/e2e/helpers/overflow.ts` answers one question for any selector: is any matching element's text cut off? It checks the element's own box (`scrollWidth > clientWidth`, which is also what a `truncate` ellipsis looks like), the box an inline element's text sits in, and every `overflow: hidden` / `clip` ancestor — stopping at a scroll container, since content past a scroller's edge is one scroll away. It measures the laid-out TEXT through a Range, because a clipped element's own box is exactly as wide as the clip. Use `findSettledClipping(page, selector)` (it waits for fonts and animations, and re-measures briefly while a layout converges), and always check `matched` as well as `clipped`: an empty page has nothing clipped. The money sweep is the reference use — `[data-money]` on every money page, at eight widths, in both locales, with the page list derived by a unit test.

### Accessibility (axe)

Every page and every kind of overlay is scanned by axe (`@axe-core/playwright`), zero tolerance, in
both locales. The pieces:

- **The fixture — `tests/e2e/helpers/axe.ts`.** Import `test`/`expect` from it instead of
  `@playwright/test` and the test gets `makeAxeBuilder()`: an `AxeBuilder` preset to the tags
  `wcag2a, wcag2aa, wcag21a, wcag21aa, wcag22aa, best-practice`. `best-practice` is deliberate — it
  holds `page-has-heading-one`, `region` and `landmark-unique`, the class the first audit found. Hand
  the results to `expectNoA11yViolations(page, results, testInfo, name, { wholePage })`: it attaches
  the full result as JSON to the report, then fails on any violation, printing one line per rule with
  every element it fired on. A whole-page scan also checks the preset really ran (`target-size` is
  only in `wcag22aa`, `page-has-heading-one` only in `best-practice`). `openForScan(page, path,
locale)` loads a page in a locale, refuses a redirect (it would scan another page under this name)
  and waits for fonts and animations — a dialog mid-fade has half-contrast text.
- **The route sweep — `a11y-routes.spec.ts` (signed out) and `a11y-routes.auth.spec.ts` (signed
  in).** The route list is DERIVED from `config/routes.ts` in `helpers/a11y-routes.ts`; the dynamic
  routes are reached with ids the signed-in spec seeds through the API. `tests/unit/a11y-sweep-coverage.test.ts`
  walks every `page.tsx` and fails unless its route is swept or skipped there with a reason — so a new
  route in `ROUTES` is swept with no edit, and a new dynamic page fails until it gets an entry.
- **Open states — `a11y-overlays.auth.spec.ts`.** A page scan cannot see an overlay (unmounted until
  opened, and once open Radix hides the rest of the page), so one of each KIND is opened and scanned
  with `include()`: a dialog, a `FormCombobox` popover, a type-to-confirm delete, the nav sheet. The
  phone width is scanned only where the layout differs (the top bar and its sheet). A new overlay kind
  gets a case there; a new instance of an existing kind is covered by its base component.
- **The allow-list — `tests/e2e/helpers/a11y-allowlist.ts`, empty by default.** The ONLY way a
  finding is tolerated: one entry per `rule` + `selector`, with a `reason` and a `revisitBy` date.
  It suppresses that rule on the elements that selector matches — never `disableRules` (a rule
  everywhere) and never `exclude()` (every rule on an element). The selector must be built from
  `[data-testid="…"]` / `[data-slot="…"]`, and `tests/unit/a11y-allowlist.test.ts` fails once the
  date passes or once nothing in the source renders the attribute any more. Fix the defect first; an
  entry is for a finding that genuinely cannot be fixed yet.

All of them carry the `@a11y` tag (`--grep @a11y`), and they run in the normal suite, so
`e2e-required` fails on them wherever the suite runs. **A defect axe reports on every page lives in
a base component — fix it there** (`packages/ui` or `components/`), not at one call site.

### Headless vs headed

Headless by default. Pass `--headed` (or use `pnpm test:e2e:headed`) when visual inspection is needed during development.

### Parallelization

Off by default — `fullyParallel: false` disables intra-file parallelism and `workers: 1` keeps files serial as well, so the suite is fully sequential regardless of environment. Increase `workers` (and consider `fullyParallel: true`) once the suite is large enough that runtime matters and all tests are confirmed independent.

### Retries

`retries: 2` in CI, `0` locally. Local failures should be visible immediately, not absorbed. CI detection respects `CI=false`/`0` as opt-outs (the config reads `process.env.CI` as a string and rejects those values explicitly).

### Timeouts

Defaults in `playwright.config.ts` are usually sufficient. If a specific test needs a different timeout, set it explicitly on that test with `test.setTimeout(...)`, do not change the global.

## Using playwright-cli during implementation

`playwright-cli` is installed globally on the dev machine. Use it to drive a real browser while implementing features, verify behavior, and capture screenshots for PR documentation.

**Verification is mandatory; PR asset upload is a separate, repo-configurable concern.** For any UI change, the agent must drive the new flow with `playwright-cli` regardless of whether the captured screenshots/videos will end up in the PR body. The "paste assets into the PR body" step is governed by the repo's PR asset upload policy (`CLAUDE.md` / `AGENTS.md`) and the `pr-format` skill's Screenshots & Recordings section. Default when no policy is declared: assets are NOT uploaded unless the user explicitly asks per PR.

### Typical agent flow

1. Implement the code change for the feature.
2. Ensure `pnpm dev` is running (ask the user to start it if it is not).
3. Drive the new flow with `playwright-cli`:

   ```bash
   playwright-cli -s=renly open http://localhost:3000/<route>  # first command per session
   playwright-cli -s=renly snapshot                             # see element refs
   playwright-cli -s=renly click e15                            # interact using refs
   playwright-cli -s=renly fill e22 "value"
   playwright-cli -s=renly screenshot --filename=/abs/path/feature-name-state.png
   ```

   **All commands need the `-s=<session>` flag once you've opened a named session** — without it they target the default unnamed session.

   For full-flow video recording (commands verified against the bundled CLI):

   ```bash
   playwright-cli -s=renly video-start /abs/path/feature-name.webm
   # ... drive the flow ...
   playwright-cli -s=renly video-stop
   ```

   Absolute paths are required for both screenshots and video; relative paths can no-op silently depending on the agent's cwd. See the `pr-format` skill for the rules about hosting the assets in the PR body.

4. If the flow has issues, iterate on the code, refresh, re-verify.
5. When satisfied, capture the final screenshots needed for the PR (see `pr-format` skill).
6. Decide if a `.spec.ts` is warranted (see "When to write a Playwright test" above). If yes, write it now, then run that spec (`pnpm test:e2e <file> --reporter=line`) to confirm it passes — three runs in a row before trusting it.

### Session management

`playwright-cli` keeps browser profile in memory by default within a session. Use named sessions (`-s=<name>`) when working in parallel; the session flag scopes per-session commands like `open` / `close`:

```bash
playwright-cli -s=renly open http://localhost:3000
playwright-cli -s=renly close
```

`playwright-cli list` is a global command that prints sessions across the machine; the `-s=` flag is ignored on `list`. Pass `--all` for cross-workspace scope when needed.

### Visual dashboard

To watch agent-driven sessions in real time, the user can run:

```bash
playwright-cli show
```

This is for the user, not the agent. Do not invoke `show` from the agent's command stream.

### Reference

The official `playwright-cli` skill is installed under `~/.claude/skills/playwright-cli/` via `playwright-cli install --skills`. Read it for the full command reference, snapshot mechanics, tracing, video recording, network mocking, storage state operations, and session details.

## Reading playwright-cli command output

After each command, the CLI outputs a snapshot of the current page state with element refs (`e15`, `e23`, etc.). Use those refs in subsequent commands. The full snapshot is also saved to `.playwright-cli/page-<timestamp>.yml` in the working directory. That directory is gitignored.

**Refs are stable across actions within a session.** Once you've snapshotted a page, you can chain `click e15` → `fill e22 "value"` → `click e30` without re-running `snapshot` between them — the refs keep pointing to the same elements. Only re-snapshot when the page itself changes (navigation, dialog open/close, dynamic content load).

## CI

`.github/workflows/ci.web-e2e.yml` runs the whole suite in one job, `e2e-web`. The workflow triggers
on every PR, every night on `main`, and on demand — and decides at JOB level whether `e2e-web` runs.

### When the suite runs

- **The floor, always.** A `changes` job lists the PR's files and sets `floor` when it touches the
  schema or migrations (`apps/api/database/**`, `apps/api/migrations/**`, `apps/api/alembic.ini`), a
  dependency manifest or lockfile (`pnpm-lock.yaml`, any `package.json`, `pnpm-workspace.yaml`,
  `apps/api/pyproject.toml`, `apps/api/uv.lock`, `.nvmrc`), or the harness itself (the workflow,
  `playwright.config.ts`, `tests/e2e/**`, `scripts/db-init.mjs`, `docker-compose.yml`). Those are
  changes whose breakage no per-page browser check would see.
- **Judgment, by label.** Any other PR runs the suite when it carries the `run-e2e` label (adding the
  label starts a run). The label is read live from the PR, not from the run's event, so re-running an
  older run sees the labels the PR has now. The agent that opens the PR decides:
  - **Add `run-e2e`** when the change touches a full user flow (auth, entry forms and the quick-add,
    reconciliation, shared money, the wizards), a shared primitive many pages use, money or
    currency conversion on the API — or anything the agent did NOT verify in the browser itself.
  - **Leave it off** for a contained UI change it verified in the browser, copy or style changes, a
    component used by one page, or API work covered by its own tests.
- **The net.** Every night at 03:17 UTC on `main`. A red night — a failure, or a run that did not
  finish (a timeout reports as cancelled) — opens one issue labelled `e2e-red` (or comments on the
  one already open); the first green night closes it. A manual run dispatched ON `main` with `report`
  ticked updates the issue the same way; on any other branch it never touches it. On top of that, a
  full run at the end of every structured block of work, and for unstructured work the agent asks
  Santi.

**While iterating, run targeted specs locally; the full suite runs in CI through the floor or the
label.**

`e2e-required` is the check to mark REQUIRED (a repository setting, not something the workflow
decides). It reports on every run and fails only when a job it needs failed or was cancelled, so a PR
whose gate skipped `e2e-web` passes. The gate lives in the job rather than in `on.paths` because a
workflow skipped by a path filter leaves a required check pending forever.

### What the job does

One job, serial, Chromium only, built from the same pieces a developer uses:

1. **Database:** `pnpm db:init`, unchanged — compose's Postgres image, `00_roles.sql`,
   `01_create_tables.sql`, an Alembic stamp. No CI-only schema path.
2. **Web:** a PRODUCTION build (`pnpm build:ui`, `pnpm build:web`, then `pnpm --filter web start`), so
   no test's budget is spent compiling a route on first request — the cause of every cold-start
   timeout the specs' comments describe. The API runs under `uvicorn` on the `renly_app` /
   `renly_admin` role split, with `EMAIL_PROVIDER=console` and a JWT / NextAuth secret generated per
   run.
3. **Exchange rates** are seeded before any API starts (it caches what it reads): today's, as the
   fallback a provider outage would otherwise leave missing, and a set three months back that no live
   fetch writes. The startup fetch still runs and simply replaces today's rows.
4. **The harness account** is a throwaway `@example.com` user with a per-run password, registered
   against a short-lived `SIGNUP_MODE=open` API that is stopped before the real one starts — the
   invite-gate spec needs the launch default, `invite`. It is then verified in SQL and given what the
   authenticated specs assume of a lived-in account: two display currencies (ARS + USD); a card owing
   a USD and an ARS charge from three months ago plus a USD one from today; and 30 past-dated expenses
   (so `/expenses` renders its pager, and an expense a spec adds today still lands on page one). The
   card holds BOTH currencies because the conversion-basis spec checks each display currency, and a
   bucket already in the display currency never converts — each pass needs one in the other
   currency, dated where the rate differs from today's. **A new spec that assumes account data adds
   it to this step.**
5. **Readiness** is `/health` on the API and `/api/auth/providers` on the web, both 200. Locally,
   `globalSetup` makes the same check first and fails at once with "start the web and API servers"
   when either is not running (a port that refuses the connection); a server that is up but slow — a
   cold `next dev` compile — gets a warning and the run carries on.
6. **Run:** `pnpm --filter web test:e2e` with `CI=true` (so `forbidOnly` + `retries: 2`), plus two
   reporters the config adds only in CI — `github`, which annotates the PR diff at each failure, and
   `json`, written to `test-results/results.json`.
7. **Require a full run:** a step reads that JSON against the spec files ON DISK and fails the job
   unless every `*.auth.spec.ts` executed a test in `chromium-authenticated`, every other `*.spec.ts`
   executed one in `chromium`, and nothing skipped. Each is a way the suite exits 0 on less than
   itself: unset credentials drop the authenticated project, a `testMatch` that stops matching leaves
   it running nothing, and a missing seed makes the conversion-basis spec skip. So **no spec may skip
   in CI** — a spec that genuinely cannot run there has to be made to run, not skipped.
8. **Artifacts** (14 days, uploaded on every run): the HTML report (`playwright-report`), the API and
   web server logs (`e2e-server-logs`), and `playwright-test-results` — which holds traces, screenshots
   and videos only for tests that FAILED (they are `retain-on-failure`), plus the JSON results. To read
   a failure: download `playwright-report`, then `pnpm --filter web exec playwright show-report <dir>`.
   The per-run secrets are masked in the job LOG only; a failed test's trace records its requests and
   can hold the harness session's bearer token (no spec sends the password — they read the token from
   the saved session). That is harmless — the account and its database are discarded with the runner —
   but it is why the harness account must stay per-run and throwaway.

Browser binaries are cached on the lockfile hash; on a hit only the system dependencies install.

## Glossary

- **Locator.** Playwright object pointing to an element. Lazy: not resolved until used. Auto-waits.
- **Storage state.** Cookies + localStorage + sessionStorage exported to JSON. Enables session reuse without UI login.
- **Trace.** Full recording of a run with DOM snapshots, network, console. Opened with `playwright show-trace trace.zip`.
- **Snapshot (CLI).** Output the CLI returns after every action, with element refs (`e15`, `e23`, ...). Lets the agent target elements without inspecting the DOM directly.
- **Codegen.** `playwright codegen <url>` opens a browser, records actions, emits test code. Useful for bootstrapping a new test.

## Resources

- Playwright docs: https://playwright.dev
- Playwright CLI repo: https://github.com/microsoft/playwright-cli
- Playwright best practices: https://playwright.dev/docs/best-practices
