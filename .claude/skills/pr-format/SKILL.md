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

A PR body is a **summary, not a report**: a reviewer should know in about 30 seconds what changed and
where to look. The shape is fixed — the H1, the Card line, a short Summary, and nothing else unless a
rule below adds it.

```
# [{TYPE}] NO-TICKET {Detailed Title}

## Card Link

N/A

## Summary

{At most three short paragraphs, one idea each.}

## ⚠️ Migration Required          ← only when the PR changes the DB schema
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

- **At most three short paragraphs, one idea per paragraph:** what changed and why first, then the
  parts a reviewer should look at, naming the files or areas in backticks. Prose, not a bullet list per
  file.
- **Cross-cutting surface goes inline, in a sentence:** a new environment variable (its name, its
  default, and which `.env.example` gained it), new translation keys when the copy is the point, a
  label the reviewer should know about. Never its own `Env vars:` / `Translations:` sub-section.
- **Verification is one clause, if it matters** ("verified on a production build at 390 and 1280"),
  never a section.

**What NOT to include:**

- **The path taken** — alternatives considered, earlier attempts, review rounds, findings and their
  fixes. The commits and the diff carry that.
- **Measurement dumps** — if the reviewer needs one number, put that number in a sentence.
- **Internal docs / meta-documentation changes** — don't mention updates to skills, `CLAUDE.md`,
  `AGENTS.md`, memory files, `.claude/` or `.agents/` contents, unless that IS the PR.
- **External platform changes.** Don't describe actions taken on external platforms as changes "we made."
- **Sections the shape does not have:** no `## Testing`, no `## Acceptance Criteria`, no
  `## Open items`, no "why X over Y" section — unless the user asks for one on this PR.

### Migration Required

`## ⚠️ Migration Required` is the one section the shape adds, and only when the PR changes the database
schema (a new migration under `apps/api/migrations/versions/`). It is a **before-merge prerequisite**,
not a description of the change: name the migration, the command a deployed environment runs
(`pnpm db:migrate`), and anything that must happen first (a role from `apps/api/database/00_roles.sql`
created by a superuser, an order relative to a deploy).

Any OTHER external prerequisite a merger must act on — an env var to set in a deployed environment, a
conflicting sibling PR — goes in a `## Before merge` section in the same place. Never for anything the
diff already says.

### Screenshots & Recordings

**Omitted by default.** Whether to include this section is governed by the repo's PR asset upload policy. Check the repo's `CLAUDE.md` / `AGENTS.md` for a "PR asset upload policy" section. Default behavior when no policy is declared: **OFF — omit the section unless the user explicitly asks for assets on the current PR.** Verification of UI changes via `playwright-cli` (see the `e2e-testing` skill) is **always required** regardless of the upload policy — only the "paste the captured assets into the PR body" step is toggled.

**When the section is included** (policy opts in, OR the user explicitly asks for assets on this PR):

- Include only when the PR has UI changes (frontend/web). Use `<img>` tags with `width`/`height`/`alt` attributes. Videos as bare GitHub asset URLs.
- Omit for backend-only, docs-only, or API-only PRs even when the policy is opt-in. Don't include an empty section.

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

**`run-e2e`:** add it when the change needs the full Playwright suite in CI and does not already touch the e2e floor. The `e2e-testing` skill ("CI" → "When the suite runs") has the rubric for when it does.

## Example

**Title:** `Skip Non-Finite yfinance Closes and Auto-Snapshot Prices`

**Body:**

```
# [FIX] NO-TICKET Skip Non-Finite yfinance Closes and Auto-Snapshot Prices

## Card Link

N/A

## Summary

Yahoo serves the day still trading as a row with a NaN close. `fetch_yfinance` only checked for `None`, so the NaN reached `asset_prices`, where the price endpoints then fail response validation. The provider now keeps finite closes only.

As a second line, `generate_auto_snapshots` skips an investment whose latest price is not finite, with a warning, which covers rows written before this fix. Both are pinned by unit tests.
```
