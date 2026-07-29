import { useState } from 'react';
import { render } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { NextIntlClientProvider } from 'next-intl';
import { describe, expect, it, vi } from 'vitest';

import { LocaleAmountInput } from '@/components/locale-amount-input';

// Controlled harness mirroring how react-hook-form drives the input: canonical `.`-decimal
// in state, re-fed as the `value` prop. `onValue` captures every canonical emission.
function Harness({
  locale = 'es',
  currency,
  maxDecimals,
  initialValue = '',
  allowNegative,
  onValue,
}: {
  locale?: string;
  currency?: string;
  maxDecimals?: number;
  initialValue?: string;
  allowNegative?: boolean;
  onValue?: (v: string) => void;
}) {
  const [value, setValue] = useState(initialValue);
  return (
    <NextIntlClientProvider locale={locale} messages={{}} timeZone="UTC">
      <LocaleAmountInput
        value={value}
        onChange={(v) => {
          setValue(v);
          onValue?.(v);
        }}
        currency={currency}
        maxDecimals={maxDecimals}
        allowNegative={allowNegative}
        aria-label="amount"
      />
    </NextIntlClientProvider>
  );
}

function getInput(container: HTMLElement): HTMLInputElement {
  return container.querySelector('input') as HTMLInputElement;
}

describe('LocaleAmountInput — live grouping', () => {
  it('groups the integer part as the user types (es)', async () => {
    const user = userEvent.setup();
    const onValue = vi.fn();
    const { container } = render(<Harness locale="es" onValue={onValue} />);
    const input = getInput(container);
    await user.type(input, '1234567');
    expect(input.value).toBe('1.234.567');
    expect(onValue).toHaveBeenLastCalledWith('1234567');
  });

  it('groups the integer part as the user types (en)', async () => {
    const user = userEvent.setup();
    const { container } = render(<Harness locale="en" />);
    const input = getInput(container);
    await user.type(input, '1234567');
    expect(input.value).toBe('1,234,567');
  });

  it('keeps a grouped integer and locale decimal while typing a decimal (es)', async () => {
    const user = userEvent.setup();
    const onValue = vi.fn();
    const { container } = render(<Harness locale="es" onValue={onValue} />);
    const input = getInput(container);
    await user.type(input, '1234,56');
    expect(input.value).toBe('1.234,56');
    expect(onValue).toHaveBeenLastCalledWith('1234.56');
  });

  it('preserves the caret after the just-typed digit when a separator is inserted', async () => {
    const user = userEvent.setup();
    const { container } = render(<Harness locale="es" />);
    const input = getInput(container);
    await user.type(input, '999');
    // Typing the 4th digit inserts a group separator; caret must stay at the end (after the digit).
    await user.type(input, '9');
    expect(input.value).toBe('9.999');
    expect(input.selectionStart).toBe(5);
  });

  it('preserves the caret when inserting a digit mid-number', async () => {
    const user = userEvent.setup();
    const { container } = render(<Harness locale="es" />);
    const input = getInput(container);
    await user.type(input, '1234'); // → "1.234"
    input.focus();
    input.setSelectionRange(0, 0);
    await user.keyboard('9'); // insert at start → "91.234"
    expect(input.value).toBe('91.234');
    expect(input.selectionStart).toBe(1);
  });
});

describe('LocaleAmountInput — paste', () => {
  it('accepts a grouped string in either notation and regroups it (es)', async () => {
    const user = userEvent.setup();
    const onValue = vi.fn();
    const { container } = render(<Harness locale="es" onValue={onValue} />);
    const input = getInput(container);
    input.focus();
    await user.paste('1.234.567,89');
    expect(input.value).toBe('1.234.567,89');
    expect(onValue).toHaveBeenLastCalledWith('1234567.89');
  });
});

describe('LocaleAmountInput — separator deletion', () => {
  it('backspace onto a group separator removes the preceding digit and regroups', async () => {
    const user = userEvent.setup();
    const onValue = vi.fn();
    const { container } = render(<Harness locale="es" onValue={onValue} />);
    const input = getInput(container);
    await user.type(input, '1234'); // → "1.234"
    input.setSelectionRange(2, 2); // caret just after the group separator
    await user.keyboard('{Backspace}');
    // Deletes the "1" (digit before the separator), not just the separator.
    expect(input.value).toBe('234');
    expect(onValue).toHaveBeenLastCalledWith('234');
  });
});

describe('LocaleAmountInput — integer currency', () => {
  it('blocks the decimal separator for a zero-precision currency (JPY) but still groups', async () => {
    const user = userEvent.setup();
    const { container } = render(<Harness locale="es" currency="JPY" />);
    const input = getInput(container);
    await user.type(input, '1234');
    expect(input.value).toBe('1.234');
    await user.type(input, ','); // blocked for a zero-precision currency
    expect(input.value).toBe('1.234');
    expect(input.value).not.toContain(',');
  });
});

// Fully-controlled harness (value comes from props, not internal state) so a test can push a new
// `value` post-mount — the way form.reset / editing a loaded record feeds the input.
function ControlledHarness({
  value,
  maxDecimals,
  onValue,
}: {
  value: string;
  maxDecimals?: number;
  onValue?: (v: string) => void;
}) {
  return (
    <NextIntlClientProvider locale="en" messages={{}} timeZone="UTC">
      <LocaleAmountInput
        value={value}
        onChange={onValue}
        maxDecimals={maxDecimals}
        aria-label="amount"
      />
    </NextIntlClientProvider>
  );
}

describe('LocaleAmountInput — effects', () => {
  it('truncates to the currency precision when a value with too many decimals is loaded (resync)', () => {
    const onValue = vi.fn();
    const { container, rerender } = render(
      <ControlledHarness value="" maxDecimals={0} onValue={onValue} />,
    );
    const input = getInput(container);
    // A record loads a 2-decimal value into a 0-decimal (JPY-style) field post-mount.
    rerender(<ControlledHarness value="100.50" maxDecimals={0} onValue={onValue} />);
    expect(input.value).toBe('100');
    expect(onValue).toHaveBeenLastCalledWith('100');
  });

  it('re-truncates to the currency precision when the currency tightens', async () => {
    const user = userEvent.setup();
    const { container, rerender } = render(<Harness locale="en" />);
    const input = getInput(container);
    await user.type(input, '1.2345'); // unlimited precision → "1.2345"
    expect(input.value).toBe('1.2345');
    rerender(<Harness locale="en" currency="USD" />); // 2-decimal cap kicks in
    expect(input.value).toBe('1.23');
  });

  it('re-formats the display to the new locale when a complete value switches locale', async () => {
    const { container, rerender } = render(<Harness locale="es" initialValue="1234.5" />);
    const input = getInput(container);
    expect(input.value).toBe('1.234,5');
    rerender(<Harness locale="en" initialValue="1234.5" />);
    expect(input.value).toBe('1,234.5');
  });

  it('does NOT migrate a mid-typing trailing separator on a locale switch', async () => {
    const user = userEvent.setup();
    const { container, rerender } = render(<Harness locale="es" />);
    const input = getInput(container);
    await user.type(input, '1234,'); // mid-typing decimal → "1.234,"
    expect(input.value).toBe('1.234,');
    rerender(<Harness locale="en" />);
    // Guard: the display keeps the trailing separator instead of resyncing mid-typing.
    expect(input.value).toBe('1.234,');
  });
});

describe('LocaleAmountInput — allowNegative', () => {
  it('accepts a leading minus and emits a negative canonical value', async () => {
    const user = userEvent.setup();
    const onValue = vi.fn();
    const { container } = render(<Harness locale="es" allowNegative onValue={onValue} />);
    const input = getInput(container);
    await user.type(input, '-4500,5');
    expect(input.value).toBe('-4.500,5');
    expect(onValue).toHaveBeenLastCalledWith('-4500.5');
  });

  it('is off by default, so amount fields stay non-negative', async () => {
    const user = userEvent.setup();
    const onValue = vi.fn();
    const { container } = render(<Harness locale="es" onValue={onValue} />);
    const input = getInput(container);
    await user.type(input, '-4500');
    expect(input.value).toBe('4.500');
    expect(onValue).toHaveBeenLastCalledWith('4500');
  });

  it('resyncs an externally-set negative value for display', () => {
    const { container } = render(
      <NextIntlClientProvider locale="en" messages={{}} timeZone="UTC">
        <LocaleAmountInput value="-1234.5" allowNegative aria-label="amount" />
      </NextIntlClientProvider>,
    );
    expect(getInput(container).value).toBe('-1,234.5');
  });
});

describe('LocaleAmountInput — accessibility', () => {
  it('renders a text input with inputMode decimal and forwards aria-invalid', () => {
    const { container } = render(
      <NextIntlClientProvider locale="es" messages={{}} timeZone="UTC">
        <LocaleAmountInput value="1234.5" aria-invalid aria-label="amount" />
      </NextIntlClientProvider>,
    );
    const input = getInput(container);
    expect(input).toHaveAttribute('type', 'text');
    expect(input).toHaveAttribute('inputMode', 'decimal');
    expect(input).toHaveAttribute('aria-invalid', 'true');
    expect(input.value).toBe('1.234,5');
  });
});
