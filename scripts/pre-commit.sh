#!/usr/bin/env bash
# Pre-commit hook body (called from .husky/pre-commit). Runs lint-staged, then only the checks the
# staged paths can affect:
#   - apps/api/** or docs/public/api-reference.md (the API suite reads it)  -> check:api + test:api
#   - apps/web/**, packages/**, root package.json / pnpm-lock.yaml / pnpm-workspace.yaml / turbo.json /
#     tsconfig*                                                              -> check:web + test:web
#   - docs/**, .claude/**, .agents/**, .github/**, *.md, LICENSE             -> nothing beyond lint-staged
#   - anything else (root config, scripts, .husky, docker, ...)              -> everything
# Whenever any code is staged, the cross-app tests of the side NOT fully run still run: they read the
# other app's source, so a change to one app can break the other's. Each app's suite derives which of
# its tests are cross-app and fails when one is untagged (see the testing skill).
#
# PRE_COMMIT_DRY_RUN=1 prints the plan for the current staged set without running anything.
set -euo pipefail

run() {
  echo "pre-commit: $*"
  [ "${PRE_COMMIT_DRY_RUN:-}" = "1" ] || "$@"
}

api=0
web=0
code=0
while IFS= read -r path; do
  case "$path" in
    apps/api/* | docs/public/api-reference.md) api=1 ;;
    apps/web/* | packages/* | package.json | pnpm-lock.yaml | pnpm-workspace.yaml | turbo.json | tsconfig*) web=1 ;;
    docs/* | .claude/* | .agents/* | .github/* | *.md | LICENSE) ;;
    *) api=1 web=1 ;;
  esac
done < <(git diff --cached --name-only --no-renames)
[ "$api$web" = "00" ] || code=1

run pnpm lint-staged
[ "$api" = "0" ] || run pnpm check:api
[ "$web" = "0" ] || run pnpm check:web
[ "$api" = "0" ] || run pnpm test:api
[ "$web" = "0" ] || run pnpm test:web
if [ "$code" = "1" ]; then
  [ "$api" = "1" ] || run pnpm --filter api run test:cross-app
  [ "$web" = "1" ] || run pnpm --filter web run test:cross-app
fi
