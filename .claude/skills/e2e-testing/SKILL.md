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
3. **CI workflow.** Not yet implemented. Future plan documented at the end of this file under "Future: CI integration."

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

Once `pnpm dev` is stable on a port other than 3000 (rare; check before assuming), pass `PLAYWRIGHT_BASE_URL=http://localhost:<port>` when running tests.

**Bootstrap note:** until the first `.spec.ts` is written, `pnpm test:e2e` exits 1 with "No tests found". That is documented Playwright behavior, not a config error. The config is correct — adding the first spec makes the runner exit 0.

## Conventions

### Selectors

Order of preference:

1. `getByTestId('...')` using `data-testid` attributes added explicitly to elements.
2. `getByRole('button', { name: 'Save' })` for semantic elements with clear accessible names.
3. `getByText('...')` only when the text is stable, untranslated, and unambiguous.
4. CSS selectors as last resort.

When adding interactive elements to a new component, add a `data-testid` attribute. Naming convention: kebab-case, scoped to context: `login-email-input`, `investment-create-submit`.

### Auth and storage state

Do not log in via UI in every test. Use a `globalSetup` script that authenticates programmatically once and saves the resulting storage state to `apps/web/tests/e2e/.auth/storage-state.json` (gitignored). Tests load it via `use: { storageState: '...' }`.

Login flow tests are the exception — they exercise the UI auth path.

### Seed data

Tests do not assume preexisting state. Use factory helpers in `apps/web/tests/e2e/helpers/factories.ts` to create the data needed at the start of each test. Clean up in `afterEach` or `afterAll` as appropriate.

### Headless vs headed

Headless by default. Pass `--headed` (or use `pnpm test:e2e:headed`) when visual inspection is needed during development.

### Parallelization

Off by default (`fullyParallel: false` in config). Enabled later when the suite is large enough that runtime matters and all tests are confirmed independent.

### Retries

`retries: 2` in CI, `0` locally. Local failures should be visible immediately, not absorbed.

### Timeouts

Defaults in `playwright.config.ts` are usually sufficient. If a specific test needs a different timeout, set it explicitly on that test with `test.setTimeout(...)`, do not change the global.

## Using playwright-cli during implementation

`playwright-cli` is installed globally on the dev machine. Use it to drive a real browser while implementing features, verify behavior, and capture screenshots for PR documentation.

### Typical agent flow

1. Implement the code change for the feature.
2. Ensure `pnpm dev` is running (ask the user to start it if it is not).
3. Drive the new flow with `playwright-cli`:
   ```bash
   playwright-cli goto http://localhost:3000/<route>
   playwright-cli snapshot                              # see element refs
   playwright-cli click e15                             # interact using refs
   playwright-cli fill e22 "value"
   playwright-cli screenshot --filename=feature-name-state.png
   ```
4. If the flow has issues, iterate on the code, refresh, re-verify.
5. When satisfied, capture the final screenshots needed for the PR (see `pr-format` skill).
6. Decide if a `.spec.ts` is warranted (see "When to write a Playwright test" above). If yes, write it now, then run `pnpm test:e2e` to confirm it passes.

### Session management

`playwright-cli` keeps browser profile in memory by default within a session. Use named sessions when working in parallel:

```bash
playwright-cli -s=renly open http://localhost:3000
playwright-cli -s=renly list
playwright-cli -s=renly close
```

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

## Future: CI integration

Not yet implemented. When the user is ready, the plan is:

**Phase 1: Manual trigger (workflow_dispatch).**

- Create `.github/workflows/ci.web-e2e.yml`.
- Trigger: `on: workflow_dispatch` only — runs only when the user clicks "Run workflow" in the Actions tab.
- Job steps:
  1. Checkout the repo.
  2. Set up Node 20 and pnpm.
  3. Set up Postgres as a service container with the same image used in `pnpm db:init`.
  4. Install dependencies with `pnpm install --frozen-lockfile`.
  5. Run `pnpm db:init` to apply schema.
  6. Start the API in background: `cd apps/api && uv run uvicorn app.main:app --port 8000 &`.
  7. Start the web in background: `cd apps/web && pnpm build && pnpm start &`.
  8. Wait for both to be healthy (curl loop).
  9. Install Playwright browsers: `pnpm --filter web exec playwright install chromium`.
  10. Run tests: `pnpm --filter web test:e2e`.
  11. Upload artifacts (screenshots, videos, traces, HTML report) regardless of outcome.
- Iterate on the workflow until 3-5 consecutive runs are clean.

**Phase 2: Automatic on PRs.**

- Add `pull_request` to the trigger: `on: [workflow_dispatch, pull_request]`.
- Filter by paths so the workflow only runs when `apps/web/**` or `playwright.config.ts` or `tests/e2e/**` changed.
- Add a step that posts a sticky comment on the PR with embedded screenshots and a link to the HTML report. Use `marocchino/sticky-pull-request-comment` or equivalent.
- Continue tuning until stable enough to be a required check.

**Decisions already made for the CI work:**

- Start with `workflow_dispatch` (manual) before going automatic.
- One job, serial execution, chromium only at the start.
- Artifacts always uploaded, even on success — gives the user the screenshots embedded in the PR comment in Phase 2.
- Use the same Postgres image and schema init flow as local `pnpm db:init`. Do not invent a separate CI-only setup.

When picking this work up, read this section in full first, then proceed.

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
