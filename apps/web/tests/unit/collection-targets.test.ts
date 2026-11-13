import { describe, expect, it } from 'vitest';

import { sumCollectionTargets, targetsExceedMax } from '@/lib/collection-targets';

describe('collection targets over 100%', () => {
  const collections = [
    { id: 1, targetPercentage: 60 },
    { id: 2, targetPercentage: 30 },
    { id: 3, targetPercentage: null },
  ];

  it('sums every target and skips a collection without one', () => {
    expect(sumCollectionTargets(collections)).toBe(90);
  });

  it('leaves out the collection being edited, whose new value the form adds', () => {
    expect(sumCollectionTargets(collections, 1)).toBe(30);
  });

  it('warns only past 100%', () => {
    expect(targetsExceedMax(100)).toBe(false);
    expect(targetsExceedMax(100.01)).toBe(true);
    // Three thirds entered to two decimals.
    expect(targetsExceedMax(33.33 + 33.33 + 33.34)).toBe(false);
  });
});
