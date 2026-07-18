import tsconfigPaths from 'vite-tsconfig-paths';
import { defineConfig } from 'vitest/config';

// Web unit tests, split into two projects so pure logic stays fast on `node` while
// React component/hook tests get a `jsdom` DOM. `tsconfigPaths` (inherited via
// `extends: true`) wires the `@/*` alias so tests import exactly as app code does.
// E2E stays on Playwright under tests/e2e.
//   - node:  tests/unit/**/*.test.ts  — pure functions (locale/formatting layer, rule kits).
//   - jsdom: tests/unit/**/*.test.tsx — components driven with React Testing Library.
export default defineConfig({
  plugins: [tsconfigPaths()],
  // Use React's automatic JSX runtime so component tests don't need `React` in scope.
  esbuild: { jsx: 'automatic' },
  // Force a single React copy — `@repo/ui` is consumed from source, so without this the
  // component and the test tree can resolve different React instances and hooks throw.
  resolve: { dedupe: ['react', 'react-dom'] },
  test: {
    projects: [
      {
        extends: true,
        test: {
          name: 'node',
          environment: 'node',
          include: ['tests/unit/**/*.test.ts'],
        },
      },
      {
        extends: true,
        test: {
          name: 'jsdom',
          environment: 'jsdom',
          include: ['tests/unit/**/*.test.tsx'],
          setupFiles: ['./tests/setup-jsdom.ts'],
        },
      },
    ],
  },
});
