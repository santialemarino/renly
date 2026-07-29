'use client';

import { forwardRef, useEffect, useLayoutEffect, useRef, useState } from 'react';
import cc from 'currency-codes';
import { useLocale } from 'next-intl';

import { Input } from '@repo/ui/components';
import {
  blockDecimalIfIntegerCurrency,
  blockScientificKeys,
  blockSecondDecimal,
  blockSignKeys,
  blockSignKeysUnlessLeadingMinus,
  blockWrongLocaleDecimal,
  composeKeyHandlers,
  formatAmountForInput,
  getDecimalSeparator,
  getGroupSeparator,
  limitDecimalsInString,
  mapCaretAfterRegroup,
  normalizeAmountFromInput,
  sanitizeDecimalChars,
  sanitizeDecimalPaste,
} from '@/lib/i18n/numeric-input';

// useLayoutEffect writes the caret before paint; fall back to useEffect on the server (SSR) to avoid React's no-op-layout-effect warning. Chosen once at module load, so it's not a conditional hook.
const useIsomorphicLayoutEffect = typeof document !== 'undefined' ? useLayoutEffect : useEffect;

interface LocaleAmountInputProps {
  value?: string;
  onChange?: (value: string) => void;
  onBlur?: () => void;
  name?: string;
  placeholder?: string;
  disabled?: boolean;
  className?: string;
  // ISO 4217 currency code — when set, max fraction digits follows the currency's sub-unit precision (JPY=0, BHD=3, USD/EUR=2). Ignored when `maxDecimals` is set explicitly.
  currency?: string;
  // Explicit override for max fraction digits — takes priority over `currency`. Use `0` to forbid decimals entirely (rare; consider IntegerInput instead). Omit both this and `currency` to allow unlimited decimals (e.g. fractional share quantities).
  maxDecimals?: number;
  // Opt in to a leading minus, for genuinely SIGNED figures (an account's real balance reads negative when overdrawn). Off by default: amounts, quantities, and counts stay non-negative.
  allowNegative?: boolean;
  'aria-invalid'?: boolean | 'true' | 'false';
}

/*
 * Locale-aware decimal amount input. Stores canonical `.`-decimal in form state;
 * displays in the user's locale format with live thousand-grouping as they type
 * (e.g. "1.234.567,89" for es-AR, "1,234,567.89" for en-US). Replaces
 * `<Input type="number" step="0.01">` for amount and quantity fields — fixes
 * Chrome's silent rejection of `1234,56` for ARS users.
 *
 * Every mutation runs the same pipeline: sanitize the raw input → normalize to
 * canonical → truncate to the currency's precision → re-group for display, then
 * re-place the caret with `mapCaretAfterRegroup` (counting digits, not characters,
 * so the inserted/removed group separators don't drift it). Keystroke rules
 * (composed from `lib/i18n/numeric-input`) block sign/scientific keys, the wrong
 * locale's decimal, a second decimal (selection-aware), and any decimal for
 * zero-precision currencies. Backspace/Delete onto a group separator removes the
 * adjacent digit (deleting the separator alone would just regroup back). Paste uses
 * "last separator wins" so `"1.234,56"` and `"1,234.56"` both yield 1234.56.
 */
const LocaleAmountInput = forwardRef<HTMLInputElement, LocaleAmountInputProps>(
  (
    { value = '', onChange, onBlur, name, currency, maxDecimals, allowNegative = false, ...rest },
    ref,
  ) => {
    const locale = useLocale();
    const decimal = getDecimalSeparator(locale);
    const group = getGroupSeparator(locale);
    const effectiveMaxDecimals =
      maxDecimals !== undefined
        ? maxDecimals
        : currency
          ? (cc.code(currency)?.digits ?? 2)
          : undefined;

    const [displayValue, setDisplayValue] = useState(() => formatAmountForInput(value, locale));
    const prevLocaleRef = useRef(locale);
    const innerRef = useRef<HTMLInputElement | null>(null);
    // Caret index to restore after a regroup re-renders the controlled value (null = no pending move).
    const pendingCaretRef = useRef<number | null>(null);

    // Merge the forwarded ref with the internal one used for caret manipulation.
    function setRefs(node: HTMLInputElement | null) {
      innerRef.current = node;
      if (typeof ref === 'function') ref(node);
      else if (ref) ref.current = node;
    }

    /*
     * Re-sync display when canonical value changes externally (e.g. form.reset).
     * Skip on locale switch when the display ends with EITHER separator — the
     * user is mid-typing a decimal and the locale change shouldn't migrate the
     * trailing separator. Value-only changes still run through the round-trip
     * check below, so form.reset keeps working.
     *
     * Deps are `[value, locale]` only on purpose: `displayValue` is a captured
     * closure value (we read it to decide whether to re-sync) and re-running on
     * every keystroke would create an infinite loop.
     */
    useEffect(() => {
      const localeChanged = prevLocaleRef.current !== locale;
      prevLocaleRef.current = locale;
      if (localeChanged && (displayValue.endsWith('.') || displayValue.endsWith(','))) return;
      // Cap the incoming value to the currency's precision too, so a value loaded with more
      // decimals than allowed (form.reset, editing a record, a field array) is truncated in BOTH
      // the display and form state — mirroring the write path. When it already fits, `capped ===
      // value` and this is behavior-identical to a plain resync. The precision effect below still
      // handles a precision *tightening* while value/locale are unchanged.
      const capped = limitDecimalsInString(value, '.', effectiveMaxDecimals);
      if (normalizeAmountFromInput(displayValue, locale) !== capped) {
        setDisplayValue(formatAmountForInput(capped, locale));
      }
      if (capped !== value) onChange?.(capped);
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [value, locale]);

    /*
     * Re-truncate display when the precision cap tightens (e.g. user typed
     * 123.45 under USD then switched currency to JPY). Independent from the
     * value/locale resync so a precision change can't be masked by a no-op
     * round-trip. Deps are `[effectiveMaxDecimals]` only — `displayValue` /
     * `onChange` capture is intentional to avoid keystroke-driven re-runs.
     */
    useEffect(() => {
      if (effectiveMaxDecimals === undefined) return;
      const limited = limitDecimalsInString(displayValue, decimal, effectiveMaxDecimals);
      if (limited !== displayValue) {
        setDisplayValue(limited);
        onChange?.(normalizeAmountFromInput(limited, locale));
      }
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [effectiveMaxDecimals]);

    // Restore the caret after a regroup commits the new controlled value to the DOM.
    useIsomorphicLayoutEffect(() => {
      const caret = pendingCaretRef.current;
      if (caret === null || innerRef.current === null) return;
      pendingCaretRef.current = null;
      innerRef.current.setSelectionRange(caret, caret);
    });

    /*
     * The one write path: take the raw post-edit string + caret, canonicalize,
     * truncate, re-group for display, push canonical to form state, and queue the
     * caret restore. `rawDisplay`/`rawCaret` are what the browser produced (with
     * stale group separators); `mapCaretAfterRegroup` reconciles them to the
     * freshly grouped string.
     */
    function applyRawWithCaret(rawDisplay: string, rawCaret: number) {
      const sanitized = sanitizeDecimalChars(rawDisplay, locale, allowNegative);
      const canonical = limitDecimalsInString(
        normalizeAmountFromInput(sanitized, locale),
        '.',
        effectiveMaxDecimals,
      );
      const nextDisplay = formatAmountForInput(canonical, locale);
      // Queue the caret only when the display actually changes, so the ref is set iff the
      // re-render (and its layout effect) will consume it — never left dangling for a later render.
      if (nextDisplay !== displayValue) {
        pendingCaretRef.current = mapCaretAfterRegroup(rawDisplay, rawCaret, nextDisplay, decimal);
        setDisplayValue(nextDisplay);
      }
      onChange?.(canonical);
    }

    function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
      const input = e.currentTarget;
      applyRawWithCaret(input.value, input.selectionStart ?? input.value.length);
    }

    function handlePaste(e: React.ClipboardEvent<HTMLInputElement>) {
      e.preventDefault();
      const input = e.currentTarget;
      const start = input.selectionStart ?? input.value.length;
      const end = input.selectionEnd ?? input.value.length;
      const sanitized = sanitizeDecimalPaste(
        e.clipboardData.getData('text/plain'),
        locale,
        allowNegative,
      );
      const rawDisplay = input.value.slice(0, start) + sanitized + input.value.slice(end);
      applyRawWithCaret(rawDisplay, start + sanitized.length);
    }

    const runKeyRules = composeKeyHandlers(
      allowNegative ? blockSignKeysUnlessLeadingMinus(displayValue) : blockSignKeys,
      blockScientificKeys,
      blockWrongLocaleDecimal(locale),
      blockSecondDecimal(locale, displayValue),
      blockDecimalIfIntegerCurrency(locale, effectiveMaxDecimals),
    );

    function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
      runKeyRules(e);
      if (e.defaultPrevented) return;
      // Backspace/Delete onto a group separator removes the adjacent DIGIT — deleting
      // the separator alone would immediately regroup back, trapping the caret.
      const input = e.currentTarget;
      const start = input.selectionStart;
      const end = input.selectionEnd;
      if (start === null || end === null || start !== end) return;
      if (e.key === 'Backspace' && start > 1 && displayValue[start - 1] === group) {
        e.preventDefault();
        applyRawWithCaret(
          displayValue.slice(0, start - 2) + displayValue.slice(start - 1),
          start - 2,
        );
      } else if (e.key === 'Delete' && displayValue[start] === group) {
        e.preventDefault();
        applyRawWithCaret(displayValue.slice(0, start) + displayValue.slice(start + 2), start);
      }
    }

    return (
      <Input
        {...rest}
        ref={setRefs}
        type="text"
        inputMode="decimal"
        name={name}
        value={displayValue}
        onChange={handleChange}
        onBlur={onBlur}
        onKeyDown={handleKeyDown}
        onPaste={handlePaste}
        autoComplete="off"
      />
    );
  },
);

LocaleAmountInput.displayName = 'LocaleAmountInput';

export { LocaleAmountInput };
