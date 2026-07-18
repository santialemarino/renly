import type { KeyboardEvent } from 'react';

import { getLocaleTag } from '@/lib/i18n/locales';

// Returns the locale's decimal separator (e.g. '.' for en-US, ',' for es-AR).
export function getDecimalSeparator(locale?: string): string {
  const parts = new Intl.NumberFormat(getLocaleTag(locale)).formatToParts(1.5);
  return parts.find((p) => p.type === 'decimal')?.value ?? '.';
}

// Returns the locale's thousand-group separator (e.g. ',' for en-US, '.' for es-AR).
export function getGroupSeparator(locale?: string): string {
  const parts = new Intl.NumberFormat(getLocaleTag(locale)).formatToParts(1234.5);
  return parts.find((p) => p.type === 'group')?.value ?? ',';
}

// Groups a run of integer digits with the given separator, every three from the right (`1234567` → `1,234,567`). Pure string op — input must be digits only (no separators), returned unchanged when 3 digits or fewer.
export function groupIntegerDigits(integer: string, groupSep: string): string {
  if (integer.length <= 3) return integer;
  return integer.replace(/\B(?=(\d{3})+(?!\d))/g, groupSep);
}

/*
 * Maps the caret across a regroup: given where the caret sat in `oldDisplay` and
 * the freshly regrouped `newDisplay`, returns the caret index in `newDisplay` that
 * keeps the same position relative to the user's digits. Counts "significant" chars
 * — digits plus the decimal separator — left of the old caret (ignoring group
 * separators, which are exactly what moves, and any stray char that will be
 * stripped), then places the caret after that many significant chars in the new
 * string. Counting the decimal separator keeps the caret after a just-typed
 * trailing separator (`1234,` → `1.234,`, caret stays after the comma).
 */
export function mapCaretAfterRegroup(
  oldDisplay: string,
  oldCaret: number,
  newDisplay: string,
  decimalSep: string,
): number {
  const isSignificant = (ch: string | undefined) =>
    ch !== undefined && ((ch >= '0' && ch <= '9') || ch === decimalSep);
  let significant = 0;
  for (let i = 0; i < oldCaret && i < oldDisplay.length; i++) {
    if (isSignificant(oldDisplay[i])) significant++;
  }
  if (significant === 0) return 0;
  let seen = 0;
  for (let i = 0; i < newDisplay.length; i++) {
    if (isSignificant(newDisplay[i])) {
      seen++;
      if (seen === significant) return i + 1;
    }
  }
  return newDisplay.length;
}

// Normalizes a user-typed locale-formatted amount string to canonical `.`-decimal. Strips thousand separators; replaces locale decimal separator with `.`. Used by `LocaleAmountInput` to convert display text to form-state canonical.
export function normalizeAmountFromInput(input: string, locale?: string): string {
  if (!input) return '';
  const group = getGroupSeparator(locale);
  const decimal = getDecimalSeparator(locale);
  return input.split(group).join('').replace(decimal, '.');
}

/*
 * Formats a canonical `.`-decimal amount string for display in a locale-aware input
 * field: groups the integer part with the locale's thousand separator and swaps `.`
 * for the locale's decimal separator (e.g. `1234567.89` → `1.234.567,89` es-AR,
 * `1,234,567.89` en-US). A trailing `.` (mid-typing, no fraction yet) is preserved
 * as a trailing decimal separator so the caret can stay past it.
 */
export function formatAmountForInput(canonical: string, locale?: string): string {
  if (!canonical) return '';
  const group = getGroupSeparator(locale);
  const decimal = getDecimalSeparator(locale);
  const dotIdx = canonical.indexOf('.');
  const integer = dotIdx === -1 ? canonical : canonical.slice(0, dotIdx);
  const grouped = groupIntegerDigits(integer, group);
  if (dotIdx === -1) return grouped;
  return `${grouped}${decimal}${canonical.slice(dotIdx + 1)}`;
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
