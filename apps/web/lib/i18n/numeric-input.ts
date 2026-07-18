import type { KeyboardEvent } from 'react';

import { getLocaleTag } from '@/lib/i18n/locales';

// Returns the locale's decimal separator (e.g. '.' for en-US, ',' for es-AR).
export function getDecimalSeparator(locale?: string): string {
  const parts = new Intl.NumberFormat(getLocaleTag(locale)).formatToParts(1.5);
  return parts.find((p) => p.type === 'decimal')?.value ?? '.';
}

// Returns the locale's thousand-group separator (e.g. ',' for en-US, '.' for es-AR).
function getGroupSeparator(locale?: string): string {
  const parts = new Intl.NumberFormat(getLocaleTag(locale)).formatToParts(1234.5);
  return parts.find((p) => p.type === 'group')?.value ?? ',';
}

// Normalizes a user-typed locale-formatted amount string to canonical `.`-decimal. Strips thousand separators; replaces locale decimal separator with `.`. Used by `LocaleAmountInput` to convert display text to form-state canonical.
export function normalizeAmountFromInput(input: string, locale?: string): string {
  if (!input) return '';
  const group = getGroupSeparator(locale);
  const decimal = getDecimalSeparator(locale);
  return input.split(group).join('').replace(decimal, '.');
}

// Formats a canonical `.`-decimal amount string for display in a locale-aware input field. Replaces `.` with the locale's decimal separator. Does NOT add thousand separators (input fields show raw values).
export function formatAmountForInput(canonical: string, locale?: string): string {
  if (!canonical) return '';
  const decimal = getDecimalSeparator(locale);
  if (decimal === '.') return canonical;
  return canonical.replace('.', decimal);
}

/*
 * Stackable keystroke + paste rules for numeric inputs. Each rule is a small,
 * independent function. Components compose the subset they need via
 * `composeKeyHandlers`. Two consumer components today: `LocaleAmountInput`
 * (decimal mode) and `IntegerInput` (integer mode).
 */

export type KeyRule = (e: KeyboardEvent<HTMLInputElement>) => void;

/*
 * Runs each handler in order on every keystroke. `preventDefault()` is
 * idempotent so calling it from multiple handlers is safe.
 */
export function composeKeyHandlers(...handlers: KeyRule[]): KeyRule {
  return (e) => {
    for (const handler of handlers) handler(e);
  };
}

// Block `-` and `+` so amount/quantity/count inputs stay non-negative.
export function blockSignKeys(e: KeyboardEvent<HTMLInputElement>): void {
  if (e.key === '-' || e.key === '+') {
    e.preventDefault();
  }
}

/*
 * Block `e` and `E` (scientific notation). HTML5 `<input type="number">`
 * accepts them; we never want them in any of our numeric inputs.
 */
export function blockScientificKeys(e: KeyboardEvent<HTMLInputElement>): void {
  if (e.key === 'e' || e.key === 'E') {
    e.preventDefault();
  }
}

/*
 * Decimal-mode rule: block the OTHER locale's decimal separator entirely.
 * en-US user can't type `,`; es-AR user can't type `.`. Closes the
 * mixed-notation parsing bug from the previous LocaleAmountInput.
 */
export function blockWrongLocaleDecimal(locale?: string): KeyRule {
  return (e) => {
    const decimal = getDecimalSeparator(locale);
    const wrong = decimal === '.' ? ',' : '.';
    if (e.key === wrong) {
      e.preventDefault();
    }
  };
}

/*
 * Decimal-mode rule: block typing a second occurrence of the current locale's
 * decimal separator — UNLESS the input's current selection overlaps the
 * existing separator (in which case the keystroke would REPLACE it, not add a
 * second one). Pass the current display value via closure.
 */
export function blockSecondDecimal(locale: string | undefined, currentValue: string): KeyRule {
  return (e) => {
    const decimal = getDecimalSeparator(locale);
    if (e.key !== decimal) return;
    const existingIdx = currentValue.indexOf(decimal);
    if (existingIdx === -1) return;
    const input = e.currentTarget;
    const start = input.selectionStart ?? input.value.length;
    const end = input.selectionEnd ?? input.value.length;
    // Selection [start, end) overlaps the existing separator at existingIdx
    // when start <= existingIdx < end — that range will be replaced by the
    // typed key, so the second-decimal block does not apply.
    if (start <= existingIdx && existingIdx < end) return;
    e.preventDefault();
  };
}

/*
 * Decimal-mode rule: when `maxDecimals === 0` (zero sub-unit currencies
 * like JPY/KRW), block the decimal separator entirely. Otherwise no-op.
 */
export function blockDecimalIfIntegerCurrency(
  locale: string | undefined,
  maxDecimals: number | undefined,
): KeyRule {
  return (e) => {
    if (maxDecimals === 0 && e.key === getDecimalSeparator(locale)) {
      e.preventDefault();
    }
  };
}

// Integer-mode rule: block both `.` and `,` (no decimals allowed).
export function blockAllSeparators(e: KeyboardEvent<HTMLInputElement>): void {
  if (e.key === '.' || e.key === ',') {
    e.preventDefault();
  }
}

/*
 * Truncate the fractional part of a display string to `max` digits.
 * `max = 0` strips the decimal separator entirely. `max = undefined` means
 * no limit (returns the value unchanged). Pure function; called from the
 * onChange path of decimal-mode inputs.
 */
export function limitDecimalsInString(
  value: string,
  decimal: string,
  max: number | undefined,
): string {
  if (max === undefined) return value;
  const idx = value.indexOf(decimal);
  if (idx === -1) return value;
  const integer = value.slice(0, idx);
  if (max === 0) return integer;
  const fraction = value.slice(idx + 1).slice(0, max);
  return `${integer}${decimal}${fraction}`;
}

/*
 * Sanitize any text for decimal-mode inputs — strips whitespace and anything
 * that isn't a digit or the locale's decimal separator. Used as the change
 * handler safety net so non-keystroke paths (IME, autofill, drag-drop,
 * programmatic input) can't leak letters or whitespace into form state.
 */
export function sanitizeDecimalChars(text: string, locale?: string): string {
  const decimal = getDecimalSeparator(locale);
  const allowed = decimal === '.' ? /[^0-9.]/g : /[^0-9,]/g;
  return text.replace(allowed, '');
}

/*
 * Sanitize pasted text for decimal-mode inputs. Strategy: keep only digits
 * and separator chars, then pick the LAST separator as the decimal — every
 * earlier separator becomes thousand-grouping noise and is stripped. Works
 * for both `1,234.56` (en-US) and `1.234,56` (es-AR) regardless of the
 * active locale. The returned string uses the locale's decimal separator
 * so it round-trips through `normalizeAmountFromInput` cleanly.
 */
export function sanitizeDecimalPaste(text: string, locale?: string): string {
  const cleaned = text.replace(/[^0-9.,]/g, '');
  if (!cleaned) return '';

  let lastSepIdx = -1;
  for (let i = cleaned.length - 1; i >= 0; i--) {
    const ch = cleaned[i];
    if (ch === '.' || ch === ',') {
      lastSepIdx = i;
      break;
    }
  }
  if (lastSepIdx === -1) return cleaned;

  const decimal = getDecimalSeparator(locale);
  const integerPart = cleaned.slice(0, lastSepIdx).replace(/[.,]/g, '');
  const fractionPart = cleaned.slice(lastSepIdx + 1).replace(/[.,]/g, '');
  // A bare separator (e.g. pasting just `,`) would yield a lone decimal char
  // whose canonical form is `.` — `Number('.')` is NaN. Drop it instead.
  if (!integerPart && !fractionPart) return '';
  return `${integerPart}${decimal}${fractionPart}`;
}

// Sanitize pasted text for integer-mode inputs. Digit-only output.
export function sanitizeIntegerPaste(text: string): string {
  return text.replace(/[^0-9]/g, '');
}
