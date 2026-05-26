---
name: pr-format
description: PR title, body, branch name, and label conventions for Renly. Use when creating a pull request.
---

# PR format (Renly)

## Branch name

Format: `{type}/{kebab-case-description}`

Types match commit types: `feat/`, `fix/`, `enh/`, `refactor/`, `docs/`, `chore/`, `test/`

## PR title

Title Case. No ticket prefix. Often starts with an imperative verb (`Implement`, `Add`, `Fix`, `Restructure`) but noun-first is acceptable.

Keep it short enough for the GitHub list view — the body H1 is the detailed version.

Examples:

- `Implement General Dashboard with Net Worth, Evolution Chart & Composition`
- `Fix Credit Card Mixed-Currency Balance & Move Metrics Helpers to Utils`
- `Add Type-Safe Currency Conversion with Rate Caching`

## PR body

```
# [{TYPE}] NO-TICKET {Detailed Title}

## Card Link

N/A

## Summary

{One-paragraph overview.}

{**Bold section headers with file paths** — detailed bullet points per change area.}

{**Translations:** — when i18n keys were added/changed (EN + ES).}

## ⚠️ Migration Required          ← only when DB schema changes exist

{SQL code block with the migration commands.}

## Acceptance Criteria

N/A

## Screenshots & Recordings       ← only when UI changes exist; omit for backend/docs-only PRs

{<img> tags or video URLs.}
```

## Section rules

### TYPE values

Use uppercase in the body header. Must match the branch type:

| Type     | Header       |
| -------- | ------------ |
| feat     | `[FEAT]`     |
| fix      | `[FIX]`      |
| enh      | `[ENH]`      |
| refactor | `[REFACTOR]` |
| docs     | `[DOCS]`     |
| chore    | `[CHORE]`    |
| test     | `[TEST]`     |

Compound types are acceptable in rare cases (e.g., `[DOCS/ENH]`).

### H1 title vs PR title

The H1 in the body is the **detailed** version — it can be longer and more descriptive than the PR title. The PR title is the short version for the GitHub list view.

Example:

- PR title: `Implement Groups Page`
- H1: `# [FEAT] NO-TICKET Groups Page — CRUD, Search, Sorting & Membership Management`

### Card link

Always `N/A`. Renly does not use a ticket tracker.

### Summary

- Lead with a one-paragraph overview of what and why.
- Group changes under **bold headers** that name the affected area with file paths in backticks. Format: `**Description — (file/path.ext):**` or `**Backend — 3 new endpoints under '/dashboard/' (routers/dashboard.py, ...):**`
- Be detailed — close to implementation-plan level. Mention component names, file paths, props, patterns.
- End with cross-cutting sub-sections when applicable:
  - **`Translations:`** — when i18n keys were added or changed (EN + ES).
- Do not include a Docs sub-section. Documentation changes are part of the feature — the code summary already conveys what changed.

**What NOT to include in the summary:**

- **Internal docs / meta-documentation changes.** Don't mention updates to skills, `CLAUDE.md`, `README.md`, memory files, or `.claude/` contents.
- **External platform changes.** Don't describe actions taken on external platforms as changes "we made."

### Migration Required

Include `## ⚠️ Migration Required` **only** when the PR includes database schema changes. Place it between Summary and Acceptance Criteria. Always include the SQL migration commands in a code block.

### Acceptance criteria

Always `N/A`. Renly does not use formal acceptance criteria from tickets.

### Screenshots & Recordings

- **Include** when the PR has UI changes (frontend/web). Use `<img>` tags with `width`/`height`/`alt` attributes. Videos as bare GitHub asset URLs.
- **Omit entirely** for backend-only, docs-only, or API-only PRs. Don't include an empty section.

**Sourcing screenshots and recordings.**

When the PR includes UI changes and the work was verified using `playwright-cli`, prefer screenshots captured during that verification over manual screenshots:

```bash
playwright-cli screenshot --filename=feature-name-state.png
```

Upload the resulting PNGs as GitHub assets by drag-and-dropping them into the PR body editor on github.com (or via `gh pr edit --body-file <file>` with assets pre-uploaded). Paste the resulting asset URLs into `<img>` tags as usual.

For multi-step flows, capture one screenshot per meaningful state (e.g. `login-empty.png`, `login-error.png`, `login-success.png`).

For full-flow video, use:

```bash
playwright-cli video-start feature-name.webm
# ... drive the flow ...
playwright-cli video-stop
```

Upload the resulting webm/mp4 as a GitHub asset. Paste the bare URL in the PR body — GitHub renders it as an embedded video player.

When the work was verified manually (no `playwright-cli` involved), capture screenshots using the OS tool (cmd+shift+4 on macOS) as before. The format of the section in the PR body is identical regardless of how the assets were sourced.

This sub-section is opt-in: it only applies when `playwright-cli` was used. The base rule (when to include the section at all) is unchanged.

## Labels

Apply from the repo's label set. Multiple labels are standard — always include layer labels when applicable.

**Type labels:**

| Type     | Label           |
| -------- | --------------- |
| feat     | `feature`       |
| fix      | `bug fix`       |
| enh      | `enhancement`   |
| refactor | `refactor`      |
| docs     | `documentation` |
| chore    | `chore`         |
| test     | `test`          |
| style    | `style`         |

**Layer labels (monorepo):**

| Layer touched | Label |
| ------------- | ----- |
| `apps/api/`   | `api` |
| `apps/web/`   | `web` |

Apply `api`, `web`, or both depending on which apps the PR touches. These are independent — a PR can have one, both, or neither.

**Other labels:** `integration` (external service), `not-a-bug fix` (styling/UX fixes that aren't bugs).

## Example

**Title:** `Implement iOS Shortcut Integration with Currency Config & Expense Source Tracking`

**Body:**

````
# [FEAT] NO-TICKET iOS Shortcut Integration — Currency Config, Expense Source Tracking & Quick-Add Pipeline

## Card Link

N/A

## Summary

Adds an iOS Shortcuts integration so expenses can be logged from the phone lock screen. The shortcut calls a new API endpoint that validates currency, resolves the source, and creates the expense.

**Backend — new endpoint and models (`routers/expenses.py`, `services/expense_service.py`):**
- `POST /expenses/quick-add` accepts amount, currency, description, source.
- Service resolves currency against user's configured list, falls back to default.
- ...

**Frontend — settings page (`app/[locale]/(app)/settings/shortcuts/page.tsx`):**
- New settings sub-page for managing shortcut configurations.
- ...

**Translations:**
- `shortcuts` namespace: EN + ES keys for settings page, validation errors, success messages.

## ⚠️ Migration Required

Run after merging:

```sql
ALTER TABLE expenses ADD COLUMN source TEXT DEFAULT 'manual';
````

## Acceptance Criteria

N/A

## Screenshots & Recordings

<img src="..." width="1440" height="777" alt="Shortcut settings page" />
```
