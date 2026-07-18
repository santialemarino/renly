import '@testing-library/jest-dom/vitest';

import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';

// Unmount anything rendered by React Testing Library after each jsdom test so
// component trees don't leak across tests (vitest globals are off, so register it).
afterEach(() => {
  cleanup();
});
