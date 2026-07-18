import type { KeyboardEvent } from 'react';
import { describe, expect, it, vi } from 'vitest';

import {
  formatAmountForInput,
  getDecimalSeparator,
  normalizeAmountFromInput,
} from '@/lib/utils/locale';
import {
  blockAllSeparators,
  blockDecimalIfIntegerCurrency,
  blockScientificKeys,
  blockSecondDecimal,
  blockSignKeys,
  blockWrongLocaleDecimal,
  limitDecimalsInString,
  sanitizeDecimalChars,
  sanitizeDecimalPaste,
  sanitizeIntegerPaste,
} from '@/lib/utils/numeric-input';

// Minimal fake keystroke event — the rules only read `key`, `currentTarget`, and `preventDefault`.
function keyEvent(
  key: string,
  currentTarget: Partial<HTMLInputElement> = {},
): KeyboardEvent<HTMLInputElement> {
  return {
    key,
    preventDefault: vi.fn(),
    currentTarget,
  } as unknown as KeyboardEvent<HTMLInputElement>;
}

describe('locale separators', () => {
  it('reports the decimal separator per locale', () => {
    expect(getDecimalSeparator('en')).toBe('.');
    expect(getDecimalSeparator('es')).toBe(',');
  });
});

describe('normalize / format round-trip', () => {
  it('normalizes a locale-formatted amount to canonical .-decimal', () => {
    // The core es-AR case: "1.234,56" typed → "1234.56" stored.
    expect(normalizeAmountFromInput('1.234,56', 'es')).toBe('1234.56');
    expect(normalizeAmountFromInput('1,234.56', 'en')).toBe('1234.56');
    expect(normalizeAmountFromInput('', 'es')).toBe('');
  });

  it('formats canonical .-decimal back to the locale separator (no grouping)', () => {
    expect(formatAmountForInput('1234.56', 'es')).toBe('1234,56');
    expect(formatAmountForInput('1234.56', 'en')).toBe('1234.56');
    expect(formatAmountForInput('', 'en')).toBe('');
  });

  it('round-trips display → canonical → display', () => {
    const canonical = normalizeAmountFromInput('1.234,56', 'es');
    expect(formatAmountForInput(canonical, 'es')).toBe('1234,56');
  });
});

describe('paste sanitizers', () => {
  it('sanitizeDecimalPaste picks the last separator as the decimal (locale-agnostic input)', () => {
    expect(sanitizeDecimalPaste('1,234.56', 'es')).toBe('1234,56');
    expect(sanitizeDecimalPaste('1.234,56', 'es')).toBe('1234,56');
    expect(sanitizeDecimalPaste('1,234.56', 'en')).toBe('1234.56');
    expect(sanitizeDecimalPaste('abc', 'es')).toBe('');
  });

  it('sanitizeIntegerPaste strips everything but digits', () => {
    expect(sanitizeIntegerPaste('1,234')).toBe('1234');
    expect(sanitizeIntegerPaste('12.5abc')).toBe('125');
  });
});

describe('sanitizeDecimalChars', () => {
  it('drops letters/whitespace but keeps digits and the locale decimal', () => {
    expect(sanitizeDecimalChars('12a3.4', 'en')).toBe('123.4');
    expect(sanitizeDecimalChars('12a3,4', 'es')).toBe('123,4');
  });
});

describe('limitDecimalsInString', () => {
  it('truncates the fractional part to max digits', () => {
    expect(limitDecimalsInString('1234.5678', '.', 2)).toBe('1234.56');
    expect(limitDecimalsInString('1234.56', '.', 0)).toBe('1234');
    expect(limitDecimalsInString('1234', '.', 2)).toBe('1234');
    expect(limitDecimalsInString('1234.56', '.', undefined)).toBe('1234.56');
  });
});

describe('keystroke rules', () => {
  it('blockSignKeys blocks + and -', () => {
    const minus = keyEvent('-');
    blockSignKeys(minus);
    expect(minus.preventDefault).toHaveBeenCalled();
    const digit = keyEvent('5');
    blockSignKeys(digit);
    expect(digit.preventDefault).not.toHaveBeenCalled();
  });

  it('blockScientificKeys blocks e/E', () => {
    const e = keyEvent('e');
    blockScientificKeys(e);
    expect(e.preventDefault).toHaveBeenCalled();
  });

  it('blockWrongLocaleDecimal blocks the other locale separator', () => {
    const comma = keyEvent(',');
    blockWrongLocaleDecimal('en')(comma);
    expect(comma.preventDefault).toHaveBeenCalled();
    const dot = keyEvent('.');
    blockWrongLocaleDecimal('en')(dot);
    expect(dot.preventDefault).not.toHaveBeenCalled();
  });

  it('blockAllSeparators blocks both . and ,', () => {
    const dot = keyEvent('.');
    blockAllSeparators(dot);
    expect(dot.preventDefault).toHaveBeenCalled();
    const comma = keyEvent(',');
    blockAllSeparators(comma);
    expect(comma.preventDefault).toHaveBeenCalled();
  });

  it('blockDecimalIfIntegerCurrency only blocks the decimal when max is 0', () => {
    const blocked = keyEvent('.');
    blockDecimalIfIntegerCurrency('en', 0)(blocked);
    expect(blocked.preventDefault).toHaveBeenCalled();
    const allowed = keyEvent('.');
    blockDecimalIfIntegerCurrency('en', 2)(allowed);
    expect(allowed.preventDefault).not.toHaveBeenCalled();
  });

  it('blockSecondDecimal blocks a second decimal unless the selection overlaps the first', () => {
    // Caret after the value, existing "." at index 2 → a second "." is blocked.
    const blocked = keyEvent('.', { value: '12.3', selectionStart: 4, selectionEnd: 4 });
    blockSecondDecimal('en', '12.3')(blocked);
    expect(blocked.preventDefault).toHaveBeenCalled();

    // Selection [2,3) overlaps the existing "." → typing replaces it, so it is allowed.
    const allowed = keyEvent('.', { value: '12.3', selectionStart: 2, selectionEnd: 3 });
    blockSecondDecimal('en', '12.3')(allowed);
    expect(allowed.preventDefault).not.toHaveBeenCalled();
  });
});
