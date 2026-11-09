import { beforeEach, describe, expect, it, vi } from 'vitest';

import { getCollections } from '@/lib/api/collections';
import { formatPct } from '@/lib/i18n/format';

/*
 * A collection's target percentage is a Decimal, which the API sends as a string ("30.00"). The mapper
 * once passed that string through under a `number` type, and the table printed it raw — "30.00%" in
 * Spanish too, where the locale writes "30%" and "12,5%". It is a number by the time it leaves the API
 * layer, so the locale formatter can do its job.
 */

vi.mock('server-only', () => ({}));

const fetchMock = vi.hoisted(() => ({ body: [] as unknown[] }));
vi.mock('@/lib/authenticated-fetch', () => ({
  authenticatedFetch: async () => ({ ok: true, json: async () => fetchMock.body }),
}));

beforeEach(() => {
  fetchMock.body = [];
});

describe('getCollections', () => {
  it('turns the Decimal target into a number the locale formatter can write', async () => {
    fetchMock.body = [
      { id: 1, name: 'Core', target_percentage: '12.50', investment_ids: [] },
      { id: 2, name: 'Loose', target_percentage: null, investment_ids: [] },
    ];
    const [core, loose] = await getCollections();
    expect(core?.targetPercentage).toBe(12.5);
    expect(loose?.targetPercentage).toBeNull();
    expect(formatPct(core!.targetPercentage!, 'es')).toBe('12,5');
  });
});
