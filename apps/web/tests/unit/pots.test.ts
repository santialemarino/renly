import { describe, expect, it } from 'vitest';

import { potLabel } from '@/lib/pots';

/*
 * The one rule that stops a NULL pot name reaching a screen. It lives in `lib/` rather than beside the
 * Shared module because three surfaces render it — the module, the notification feed and the
 * dashboard's undivided-pot line — and the notification layer already shipped the failure this
 * prevents: `.format(pot=None)` does not raise, it prints "None".
 */
describe('potLabel', () => {
  it('falls back for the default pot, which A4 leaves unnamed on purpose', () => {
    expect(potLabel({ name: null }, 'Shared money')).toBe('Shared money');
    expect(potLabel({ name: 'Casa' }, 'Shared money')).toBe('Casa');
  });

  it('treats a whitespace-only name as no name', () => {
    // Otherwise a pot renamed to a space renders a blank heading rather than the fallback.
    expect(potLabel({ name: '   ' }, 'Shared money')).toBe('Shared money');
  });
});
