import '@testing-library/jest-dom/vitest';

import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';

// Unmount anything rendered by React Testing Library after each jsdom test so
// component trees don't leak across tests (vitest globals are off, so register it).
afterEach(() => {
  cleanup();
});

/*
 * jsdom has no layout, so it ships no ResizeObserver; every browser the app supports does. A no-op one
 * lets components that measure themselves (the `Table` watches its own overflow) mount here — nothing
 * ever resizes in jsdom, so an observer that never fires is exactly what a real one would do.
 */
if (typeof globalThis.ResizeObserver === 'undefined') {
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}
