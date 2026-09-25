import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';
import { describe, expect, it } from 'vitest';

import { MONEY_DECIMALS, moneyProduct } from '@/lib/money';

/*
 * The web's one money-rounding rule, and the guard that keeps it the only one.
 *
 * The API rounds every money figure HALF-UP through `domain.money.quantize`. The web used to compute a
 * snapshot's value as `(quantity * price).toFixed(2)`, which rounds the BINARY approximation of the
 * product: 1 x 1.005 is 1.00499999… in a float, so it said 1.00 where the API says 1.01. The expected
 * values below are worked by hand, never by calling a second implementation.
 */

const WEB = join(__dirname, '..', '..');
const SOURCE_ROOTS = ['app', 'components', 'lib'].map((dir) => join(WEB, dir));
const RULE_FILE = join(WEB, 'lib', 'money.ts');

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) return sourceFiles(full);
    return /\.tsx?$/.test(entry) ? [full] : [];
  });
}

describe('moneyProduct', () => {
  it.each([
    // [a, b, expected] — each lands exactly on a half at the third decimal.
    ['1', 1.005, '1.01'],
    ['10', '0.2345', '2.35'],
    ['3', 0.335, '1.01'],
    ['1', 2.675, '2.68'],
  ])('rounds %s x %s half-up to %s, where toFixed(2) rounds the float', (a, b, expected) => {
    expect(moneyProduct(a, b)).toBe(expected);
  });

  it('rounds a negative tie away from zero, as ROUND_HALF_UP does', () => {
    expect(moneyProduct('-1', '1.005')).toBe('-1.01');
    expect(moneyProduct('-1', '1.004')).toBe('-1.00');
  });

  it('keeps an ordinary product and pads to two places', () => {
    expect(moneyProduct('10', 200)).toBe('2000.00');
    expect(moneyProduct('4.545455', '1.100000')).toBe('5.00');
    expect(moneyProduct('0.1', '0.2')).toBe('0.02');
  });

  it('keeps the cent a float would lose', () => {
    // Past ~15-16 significant digits a float cannot hold the cent; ARS reaches that magnitude.
    expect(moneyProduct('90000000000000.005', '1')).toBe('90000000000000.01');
  });

  it('reads a number written in exponent notation', () => {
    expect(moneyProduct('1', 1e-7)).toBe('0.00');
    expect(moneyProduct('2', 1.5e21)).toBe('3000000000000000000000.00');
    expect(moneyProduct('1', '5e-3')).toBe('0.01');
  });

  it('has no answer for something that is not a decimal', () => {
    expect(moneyProduct('', '1')).toBeNull();
    expect(moneyProduct('abc', '1')).toBeNull();
    expect(moneyProduct('1', Number.NaN)).toBeNull();
    expect(moneyProduct('1', Number.POSITIVE_INFINITY)).toBeNull();
  });
});

describe('nothing else rounds money', () => {
  // Derived, not listed: every `.toFixed(<money places>)` outside the rule file is a second rule.
  // `.toFixed(6)` on a derived QUANTITY is not money and passes.
  const pattern = new RegExp(`\\.toFixed\\(\\s*(${MONEY_DECIMALS}|MONEY_DECIMALS)\\s*\\)`);

  it('has no toFixed to the money scale outside lib/money.ts', () => {
    const offenders = SOURCE_ROOTS.flatMap(sourceFiles)
      .filter((file) => file !== RULE_FILE)
      .filter((file) => pattern.test(readFileSync(file, 'utf8')))
      .map((file) => relative(WEB, file));
    expect(offenders).toEqual([]);
  });

  it('is actually reading the source tree', () => {
    // Anti-vacuity: the snapshot dialog is certain to exist and to use the rule.
    const files = SOURCE_ROOTS.flatMap(sourceFiles);
    expect(files.length).toBeGreaterThan(100);
    const dialog = files.find((file) => file.endsWith('snapshot-form-dialog.tsx'));
    expect(dialog && readFileSync(dialog, 'utf8')).toContain('moneyProduct(');
  });

  it('rests on a premise that is true', () => {
    // If toFixed ever rounded the decimal the value was written as, the guard above would police
    // nothing and should be deleted.
    expect((1 * 1.005).toFixed(MONEY_DECIMALS)).toBe('1.00');
  });
});
