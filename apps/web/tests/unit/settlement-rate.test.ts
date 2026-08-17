import { describe, expect, it } from 'vitest';

import { estimatedCardRate, impliedRate, rateForPair } from '@/lib/utils/settlement-rate';

/*
 * The cross-currency settlement dialog's read-back. These numbers are presentation only — the user's
 * typed amount is always what gets recorded — so the contract that matters is that a half-filled or
 * nonsensical form yields NOTHING rather than Infinity, NaN, or a confidently wrong estimate.
 *
 * The component itself can't be mounted here (the jsdom harness resolves two React copies against a
 * Radix popover), which is why the logic lives in a pure module — same reason as `visiblePages`.
 */

describe('impliedRate', () => {
  it('divides the account leg by the bucket leg', () => {
    // US$100 paid with $130,000 → 1,300 pesos per dollar.
    expect(impliedRate('100', '130000')).toBe(1300);
    expect(impliedRate('100.00', '130000.00')).toBe(1300);
  });

  it('keeps fractional precision rather than rounding', () => {
    expect(impliedRate('3', '4000')).toBeCloseTo(1333.3333, 4);
  });

  it('shows nothing while either side is empty', () => {
    expect(impliedRate('', '130000')).toBeNull();
    expect(impliedRate('100', '')).toBeNull();
    expect(impliedRate('', '')).toBeNull();
  });

  it('shows nothing for a zero or negative amount instead of Infinity', () => {
    // A bare `account / bucket` would return Infinity here and render as "∞ ARS per USD".
    expect(impliedRate('0', '130000')).toBeNull();
    expect(impliedRate('100', '0')).toBeNull();
    expect(impliedRate('-100', '130000')).toBeNull();
  });

  it('shows nothing for a non-numeric entry instead of NaN', () => {
    expect(impliedRate('abc', '130000')).toBeNull();
    expect(impliedRate('100', 'abc')).toBeNull();
  });
});

describe('estimatedCardRate', () => {
  it('applies the perception multiplier to the oficial rate', () => {
    // Default multiplier is 1.30 — the 30% Ganancias perception, the only surcharge left in 2026.
    expect(estimatedCardRate('USD', 'ARS', 1000)).toBeCloseTo(1300, 6);
  });

  it('estimates nothing for a pair the perception does not apply to', () => {
    // The perception is an Argentine tax on foreign-currency card consumption, so it means nothing for
    // a EUR bucket or a BRL account — and a confidently wrong number is worse than none.
    expect(estimatedCardRate('EUR', 'ARS', 1000)).toBeNull();
    expect(estimatedCardRate('USD', 'BRL', 1000)).toBeNull();
    expect(estimatedCardRate('ARS', 'USD', 1000)).toBeNull();
  });

  it('estimates nothing when no oficial rate is stored', () => {
    expect(estimatedCardRate('USD', 'ARS', null)).toBeNull();
    expect(estimatedCardRate('USD', 'ARS', 0)).toBeNull();
    expect(estimatedCardRate('USD', 'ARS', -5)).toBeNull();
  });
});

describe('rateForPair', () => {
  const rates = [
    { pair: 'USD_ARS_OFICIAL', rate: '1000.500000' },
    { pair: 'USD_ARS_MEP', rate: '1450.000000' },
  ];

  it('reads the requested pair as a number', () => {
    expect(rateForPair(rates, 'USD_ARS_OFICIAL')).toBe(1000.5);
  });

  it('never falls back to a different pair', () => {
    // Reading MEP here would be a quiet correctness bug: dólar tarjeta is built on oficial even for a
    // user whose display preference is MEP.
    expect(rateForPair([{ pair: 'USD_ARS_MEP', rate: '1450' }], 'USD_ARS_OFICIAL')).toBeNull();
  });

  it('returns null for a missing or unusable rate', () => {
    expect(rateForPair([], 'USD_ARS_OFICIAL')).toBeNull();
    expect(rateForPair([{ pair: 'USD_ARS_OFICIAL', rate: '0' }], 'USD_ARS_OFICIAL')).toBeNull();
    expect(rateForPair([{ pair: 'USD_ARS_OFICIAL', rate: 'x' }], 'USD_ARS_OFICIAL')).toBeNull();
  });
});
