import type { KeyboardEvent } from 'react';
import { describe, expect, it, vi } from 'vitest';

import {
  blockAllSeparators,
  blockDecimalIfIntegerCurrency,
  blockScientificKeys,
  blockSecondDecimal,
  blockSignKeys,
  blockWrongLocaleDecimal,
  composeKeyHandlers,
  formatAmountForInput,
  getDecimalSeparator,
  getGroupSeparator,
  groupIntegerDigits,
  limitDecimalsInString,
  mapCaretAfterRegroup,
  normalizeAmountFromInput,
  sanitizeDecimalChars,
  sanitizeDecimalPaste,
  sanitizeIntegerPaste,
} from '@/lib/i18n/numeric-input';

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

  it('reports the group separator per locale', () => {
    expect(getGroupSeparator('en')).toBe(',');
    expect(getGroupSeparator('es')).toBe('.');
  });
});

describe('normalize / format round-trip', () => {
  it('normalizes a locale-formatted amount to canonical .-decimal', () => {
    // The core es-AR case: "1.234,56" typed → "1234.56" stored.
    expect(normalizeAmountFromInput('1.234,56', 'es')).toBe('1234.56');
    expect(normalizeAmountFromInput('1,234.56', 'en')).toBe('1234.56');
    expect(normalizeAmountFromInput('', 'es')).toBe('');
  });

  it('strips every group separator (not just the first)', () => {
    expect(normalizeAmountFromInput('1.234.567,89', 'es')).toBe('1234567.89');
    expect(normalizeAmountFromInput('1,234,567.89', 'en')).toBe('1234567.89');
  });

  it('formats canonical .-decimal to the locale separator WITH thousand grouping', () => {
    expect(formatAmountForInput('1234.56', 'es')).toBe('1.234,56');
    expect(formatAmountForInput('1234.56', 'en')).toBe('1,234.56');
    expect(formatAmountForInput('1234567.89', 'es')).toBe('1.234.567,89');
    expect(formatAmountForInput('999', 'es')).toBe('999');
    expect(formatAmountForInput('', 'en')).toBe('');
  });

  it('preserves a trailing decimal separator (mid-typing, no fraction yet)', () => {
    expect(formatAmountForInput('1234.', 'es')).toBe('1.234,');
    expect(formatAmountForInput('1234.', 'en')).toBe('1,234.');
  });

  it('round-trips display → canonical → display', () => {
    const canonical = normalizeAmountFromInput('1.234,56', 'es');
    expect(formatAmountForInput(canonical, 'es')).toBe('1.234,56');
  });
});

describe('groupIntegerDigits', () => {
  it('inserts the separator every three digits from the right', () => {
    expect(groupIntegerDigits('1', '.')).toBe('1');
    expect(groupIntegerDigits('999', '.')).toBe('999');
    expect(groupIntegerDigits('1234', '.')).toBe('1.234');
    expect(groupIntegerDigits('1234567', ',')).toBe('1,234,567');
    expect(groupIntegerDigits('', '.')).toBe('');
  });
});

describe('mapCaretAfterRegroup', () => {
  it('keeps the caret after the same digit when a group separator is inserted', () => {
    // "9999" caret at end (4) → regrouped "9.999"; caret lands at the end (5).
    expect(mapCaretAfterRegroup('9999', 4, '9.999', ',')).toBe(5);
  });

  it('keeps the caret after a just-typed trailing decimal separator', () => {
    // es: "1234," (caret 5, after comma) → regrouped "1.234,"; caret stays after the comma (6).
    expect(mapCaretAfterRegroup('1234,', 5, '1.234,', ',')).toBe(6);
  });

  it('maps a mid-number caret by digit count, ignoring separators', () => {
    // Inserted "9" after "2" in "1.2934" (caret 4) → "12.934"; caret after the "9" (index 4).
    expect(mapCaretAfterRegroup('1.2934', 4, '12.934', ',')).toBe(4);
  });

  it('returns 0 when no significant chars precede the caret', () => {
    expect(mapCaretAfterRegroup('1.234', 0, '1.234', ',')).toBe(0);
  });
});

describe('paste sanitizers', () => {
  it('sanitizeDecimalPaste picks the last separator as the decimal (locale-agnostic input)', () => {
    expect(sanitizeDecimalPaste('1,234.56', 'es')).toBe('1234,56');
    expect(sanitizeDecimalPaste('1.234,56', 'es')).toBe('1234,56');
    expect(sanitizeDecimalPaste('1,234.56', 'en')).toBe('1234.56');
    expect(sanitizeDecimalPaste('abc', 'es')).toBe('');
  });

  it('sanitizeDecimalPaste drops a bare separator (would canonicalize to NaN)', () => {
    expect(sanitizeDecimalPaste(',', 'es')).toBe('');
    expect(sanitizeDecimalPaste('.', 'en')).toBe('');
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
    expect(sanitizeDecimalChars('1 2 3.4', 'en')).toBe('123.4');
  });

  it('collapses a multi-decimal string to a single separator (IME/drop/programmatic safety net)', () => {
    // The keystroke path blocks a second decimal; these non-keystroke paths flow through here.
    expect(sanitizeDecimalChars('1.2.3', 'en')).toBe('1.23');
    expect(sanitizeDecimalChars('1,2,3', 'es')).toBe('1,23');
  });
});

describe('composeKeyHandlers', () => {
  it('runs every handler in order on one keystroke', () => {
    const calls: string[] = [];
    composeKeyHandlers(
      () => calls.push('a'),
      () => calls.push('b'),
    )(keyEvent('5'));
    expect(calls).toEqual(['a', 'b']);
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
