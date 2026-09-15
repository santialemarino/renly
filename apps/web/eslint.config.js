import { nextJsConfig } from '@repo/eslint-config/next-js';

/*
 * Playwright's own output, which is gitignored but was not LINT-ignored — and the two are separate
 * lists. A failing e2e run writes the trace viewer's vendored bundle into `playwright-report/`, and
 * the next `pnpm lint` reports ~3700 warnings from minified third-party JS: with `--max-warnings 0`
 * that fails the lint script and therefore the pre-commit hook, for a directory nobody edits and
 * nothing ships. The failure looks like a code problem and is an artifact of having run the tests.
 */
const PLAYWRIGHT_OUTPUT = ['playwright-report/**', 'test-results/**'];

/** @type {import("eslint").Linter.Config[]} */
export default [...nextJsConfig, { ignores: PLAYWRIGHT_OUTPUT }];
