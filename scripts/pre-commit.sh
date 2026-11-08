#!/usr/bin/env bash
# Pre-commit hook body (called from .husky/pre-commit). Quick feedback on what the staged change can
# break; the full suites run in CI, whose `ci-api`, `ci-web` and `e2e-required` checks a merge to main
# requires. In order:
#   - lint-staged, always;
#   - the type checks of the side(s) staged: check:api (the app imports), check:web (typegen + tsc);
#   - the tests RELATED to the staged files: `vitest related` on the web side (the test files that import
#     a staged file, directly or not), and scripts/api-related-tests.py on the API side (the same
#     question, answered from the import graph);
#   - both apps' cross-app tests whenever any code is staged: they read the other app's source by path,
#     which no import graph sees.
# Which side a path belongs to:
#   - apps/api/** or docs/public/api-reference.md (the API suite reads it)  -> api
#   - apps/web/**, packages/**, pnpm-lock.yaml / pnpm-workspace.yaml / turbo.json / tsconfig*  -> web
#   - docs/**, .claude/**, .agents/**, .github/**, *.md, LICENSE             -> nothing beyond lint-staged
#   - anything else (root package.json — it holds both apps' scripts and the lint-staged config —,
#     root config, scripts, .husky, docker, ...)                           -> both, with their FULL suites
# A side's full suite also runs when a staged path is one its tests cannot be related to by imports: on
# the API anything but a Python module of app/ or tests/ (schema, migrations, pyproject, uv.lock, the API
# reference, a deleted file); on the web the lockfile and workspace files, tsconfig*, a package.json, the
# Vitest config and the test setup. What `related` cannot see is a test that reads source by PATH (the
# structural guards that derive a population from the tree); CI runs every test on every PR.
#
# PRE_COMMIT_DRY_RUN=1 prints the plan for the current staged set without running anything, then FAILS
# so a dry run left exported can never let a commit through unchecked.
set -euo pipefail

root="$(git rev-parse --show-toplevel)"

run() {
  echo "pre-commit: $*"
  [ "${PRE_COMMIT_DRY_RUN:-}" = "1" ] || "$@"
}

api=0
web=0
api_full=0
web_full=0
api_files=()
web_files=()
while IFS= read -r path; do
  case "$path" in
    apps/api/*)
      api=1
      api_files+=("$path")
      ;;
    docs/public/api-reference.md) api=1 api_full=1 ;;
    apps/web/package.json | apps/web/vitest.config.* | apps/web/tests/setup* | apps/web/tsconfig* | packages/*/package.json | packages/*/tsconfig*)
      web=1 web_full=1
      ;;
    apps/web/* | packages/*)
      web=1
      web_files+=("$root/$path")
      ;;
    pnpm-lock.yaml | pnpm-workspace.yaml | turbo.json | tsconfig*) web=1 web_full=1 ;;
    docs/* | .claude/* | .agents/* | .github/* | *.md | LICENSE) ;;
    *) api=1 web=1 api_full=1 web_full=1 ;;
  esac
done < <(git diff --cached --name-only --no-renames)

run pnpm lint-staged
[ "$api" = "0" ] || run pnpm check:api
[ "$web" = "0" ] || run pnpm check:web

if [ "$api" = "1" ]; then
  related=""
  if [ "$api_full" = "0" ]; then
    related="$(python3 "$root/scripts/api-related-tests.py" "${api_files[@]}")"
    [ "$related" != "ALL" ] || api_full=1
  fi
  if [ "$api_full" = "1" ]; then
    run pnpm test:api
  elif [ -n "$related" ]; then
    # Four workers once the set is big enough to repay starting them (measured: the unit suite takes
    # ~60s serially, ~30s on four workers; eight were slower on an 8 GB laptop).
    parallel=()
    [ "$(wc -l <<< "$related")" -le 20 ] || parallel=(-n 4 --dist loadfile)
    # One test file per line, none with a space in its name.
    # shellcheck disable=SC2086
    (cd "$root/apps/api" && run uv run pytest -q ${parallel[@]+"${parallel[@]}"} $related)
  else
    echo "pre-commit: no API test imports the staged files"
  fi
fi

if [ "$web" = "1" ]; then
  if [ "$web_full" = "1" ]; then
    run pnpm test:web
  else
    run pnpm --filter web exec vitest related --run --passWithNoTests "${web_files[@]}"
  fi
fi

if [ "$api$web" != "00" ]; then
  run pnpm --filter api run test:cross-app
  run pnpm --filter web run test:cross-app
fi

if [ "${PRE_COMMIT_DRY_RUN:-}" = "1" ]; then
  echo "pre-commit: dry run — nothing was checked, so the commit is refused"
  exit 1
fi
