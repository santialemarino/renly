import tsconfigPaths from 'vite-tsconfig-paths';
import { defineConfig } from 'vitest/config';

// Web unit tests (pure functions — the locale/formatting layer). E2E stays on Playwright
// under tests/e2e; this config only picks up tests/unit/**/*.test.ts. `tsconfigPaths` wires
// the `@/*` alias from tsconfig so tests import exactly as app code does.
export default defineConfig({
  plugins: [tsconfigPaths()],
  test: {
    environment: 'node',
    include: ['tests/unit/**/*.test.ts'],
  },
});
