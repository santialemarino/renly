import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

import { MIN_INTERNAL_API_SECRET_LENGTH } from '@/lib/internal-api-secret';

/*
 * The web server names the visitor in one header and proves it in another, and the API reads both by
 * name. A rename on either side alone would leave every server-side call keyed by the web server
 * again, silently — the API simply sees no header. Both sides are read from source (the web helper is
 * `server-only` and cannot be imported here).
 */

const WEB = join(__dirname, '..', '..');
const webSource = readFileSync(join(WEB, 'lib', 'server-api-fetch.ts'), 'utf8');
const apiSource = readFileSync(join(WEB, '..', 'api', 'app', 'rate_limit.py'), 'utf8');

function constant(source: string, pattern: RegExp): string | undefined {
  return source.match(pattern)?.[1];
}

describe('client-forwarding header names', () => {
  for (const name of ['CLIENT_IP_HEADER', 'INTERNAL_SECRET_HEADER']) {
    it(`${name} is the same on both sides`, () => {
      const web = constant(webSource, new RegExp(`export const ${name} = '([^']+)'`));
      const api = constant(apiSource, new RegExp(`^${name} = "([^"]+)"`, 'm'));
      expect(web).toBeTruthy();
      expect(web).toBe(api);
    });
  }
});

describe('internal secret length', () => {
  it('the web warns below the same minimum the API enforces', () => {
    const apiConfig = readFileSync(join(WEB, '..', 'api', 'app', 'config.py'), 'utf8');
    const api = constant(apiConfig, /^MIN_INTERNAL_API_SECRET_LENGTH = (\d+)$/m);
    expect(api).toBeTruthy();
    expect(MIN_INTERNAL_API_SECRET_LENGTH).toBe(Number(api));
  });
});
