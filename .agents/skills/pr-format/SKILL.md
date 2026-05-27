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
  - **`Env vars:`** — when new environment variables were added or removed (`NEXT_PUBLIC_*` on the web, backend `os.getenv` reads). List each key, its default, and which `.env.example` was updated. Reviewers should not have to grep for new env surface.
- Do not include a Docs sub-section. Documentation changes are part of the feature — the code summary already conveys what changed.

**What NOT to include in the summary:**

- **Internal docs / meta-documentation changes.** Don't mention updates to skills, `CLAUDE.md`, `AGENTS.md`, `README.md`, memory files, `.claude/`, or `.agents/` contents.
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

For multi-step flows, capture one screenshot per meaningful state (e.g. `login-empty.png`, `login-error.png`, `login-success.png`).

For full-flow video, use (commands verified against the bundled CLI):

```bash
playwright-cli -s=<session> video-start /abs/path/to/feature-name.webm
# ... drive the flow ...
playwright-cli -s=<session> video-stop
```

**Hosting assets without committing them to the repo.** The cleanest path inside GitHub depends on whether the agent has a browser session or not:

1. **Drag-and-drop in the PR body editor on github.com** — produces canonical `github.com/user-attachments/assets/<uuid>` URLs that render images inline AND turn `.webm`/`.mp4` into an embedded video player. This is the gold standard, but **agents cannot do this from the CLI** — the upload endpoint requires a browser session cookie and CSRF token. If the user is happy to paste them in themselves (Cmd+V from clipboard or drag-and-drop the file), this is the best option.

2. **GitHub prerelease assets via `gh release` (agent-driven, no browser).** When the agent has to host the files itself, create a public **prerelease** tagged for the PR (e.g. `pr-<num>-screenshots`) and upload the assets there:

   ```bash
   gh release create pr-<num>-screenshots --prerelease \
     --title "PR #<num> — <feature> screenshots" \
     --notes "Screenshots for PR #<num>. Not a version release — assets only." \
     file1.png file2.png feature-name.webm
   ```

   Assets are reachable at the stable URL:

   ```
   https://github.com/<owner>/<repo>/releases/download/<tag>/<filename>
   ```

   Paste those URLs into `<img src="...">` tags. They render inline as images. The video URL will be a download link (not an embedded player — only `user-attachments` URLs render as players).

   Mention the prerelease tag in the Screenshots section so reviewers know where the assets live (e.g. "Hosted as `pr-92-screenshots` prerelease — no commits to the repo.").

   **Note:** `gh release create` creates a real Git tag (e.g. `pr-92-screenshots`). It accumulates one tag per visual PR. Delete after merge with `git tag -d pr-<num>-screenshots && git push --delete origin pr-<num>-screenshots` if you don't want them piling up.

3. **`gh gist create` does NOT accept binary files** (the gh CLI rejects them with `binary file not supported`). Skip this option.

4. **Committing screenshots to the repo** (e.g. `docs/pr-screenshots/<feature>/`) works but pollutes the main history with ~1MB of binaries per visual PR. Avoid unless the user explicitly asks for it.

**Hybrid workflow for visual-heavy PRs.** Path 1 (drag-drop) and path 2 (prerelease) can be combined when you want the inline video player without giving up the agent-driven flow. The agent uploads all PNGs via `gh release` (instant, no user step); the user then Cmd+Vs the `.webm`/`.mp4` directly into the PR body editor on github.com to produce a `user-attachments/assets/<uuid>` URL that renders as an embedded `<video>` player. The two paths coexist in the same PR body.

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
