---
name: commit
description: Commit message format and staging rules for the Renly repo. Use when creating a git commit.
---

# Commit conventions (Renly)

## Format

```
type: imperative description
```

- **Lowercase**, no period at the end
- **Imperative mood:** "add", "fix", "implement", "remove" — not "added", "fixes", "implementing"
- **One line** is the norm; no blank line + body since every PR would contain no more than 4-5 commits

## Types

| Type       | When to use                           |
| ---------- | ------------------------------------- |
| `feat`     | New feature or behaviour              |
| `fix`      | Bug fix                               |
| `enh`      | Enhancement to existing functionality |
| `refactor` | Code change with no behaviour change  |
| `docs`     | README, skill, or doc-only change     |
| `chore`    | Config, tooling, deps, gitignore, CI  |
| `test`     | Adding or fixing tests                |
| `style`    | Formatting only (no logic change)     |

## Scopes (optional)

No scope is used today (history has none). If a commit is clearly isolated to one app, a scope in parens is acceptable but not required: `feat(api): ...`, `fix(web): ...`.

## What NOT to stage

- `.claude/projects/` — local agent memory, gitignored
- Temporary or scratch `.md` files not explicitly requested
- Always stage files **individually by name** — never `git add .` or `git add -A`

## Examples

```
feat: implement investment groups crud
fix: use naive datetime for updated_at on session epoch bump
enh: improve sidebar with logout button and active state
docs: update api readme with check command
chore: add .claude/projects/ to gitignore
refactor: extract snapshot upsert logic into repository
test: add unit tests for period return calculation
```
