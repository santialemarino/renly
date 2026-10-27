import { describe, expect, it } from 'vitest';

import { clientIpFromForwardedFor } from '@/lib/utils/client-ip';

/*
 * The client IP this server forwards to the API, read from its own request. Counting from the right
 * is what makes it spoof-resistant: every trusted proxy appends what it saw, so a client can only add
 * entries to the LEFT of them. And with no trusted proxy there is no answer at all, because Next keeps
 * a client-sent `X-Forwarded-For` as it is rather than appending the peer to it.
 */

describe('clientIpFromForwardedFor', () => {
  it('reads the address one trusted proxy appended', () => {
    expect(clientIpFromForwardedFor('203.0.113.7', 1)).toBe('203.0.113.7');
  });

  it('ignores entries the client prepended', () => {
    expect(clientIpFromForwardedFor('9.9.9.9, 8.8.8.8, 203.0.113.7', 1)).toBe('203.0.113.7');
  });

  it('counts each trusted proxy in from the right', () => {
    expect(clientIpFromForwardedFor('9.9.9.9, 203.0.113.7, 10.0.0.2', 2)).toBe('203.0.113.7');
  });

  it('takes the leftmost entry when the chain is shorter than the proxy count', () => {
    // The API's rule for the same case, so the two never disagree on a misconfigured count.
    expect(clientIpFromForwardedFor('203.0.113.7', 3)).toBe('203.0.113.7');
  });

  it('skips empty entries and surrounding spaces', () => {
    expect(clientIpFromForwardedFor(' , 9.9.9.9 ,203.0.113.7 , ', 1)).toBe('203.0.113.7');
  });

  it('has no answer without a trusted proxy', () => {
    expect(clientIpFromForwardedFor('203.0.113.7', 0)).toBeNull();
  });

  it('has no answer for a count that is not a positive integer', () => {
    for (const count of [-1, 1.5, Number.NaN]) {
      expect(clientIpFromForwardedFor('203.0.113.7', count)).toBeNull();
    }
  });

  it('has no answer without the header', () => {
    expect(clientIpFromForwardedFor(null, 1)).toBeNull();
    expect(clientIpFromForwardedFor(' , ', 1)).toBeNull();
  });
});
