import { useState } from 'react';
import { render } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { IntegerInput } from '@/components/integer-input';

// Controlled harness mirroring react-hook-form: the digit-only string is held in state and re-fed
// as `value`. IntegerInput has no locale dependency, so no NextIntlClientProvider is needed.
function Harness({ onValue }: { onValue?: (v: string) => void }) {
  const [value, setValue] = useState('');
  return (
    <IntegerInput
      value={value}
      onChange={(v) => {
        setValue(v);
        onValue?.(v);
      }}
      aria-label="quantity"
    />
  );
}

function getInput(container: HTMLElement): HTMLInputElement {
  return container.querySelector('input') as HTMLInputElement;
}

describe('IntegerInput', () => {
  it('keeps only digits as the user types (strips stray letters)', async () => {
    const user = userEvent.setup();
    const { container } = render(<Harness />);
    const input = getInput(container);
    await user.type(input, '12a3');
    expect(input.value).toBe('123');
  });

  it('blocks decimal separators and sign/scientific keys', async () => {
    const user = userEvent.setup();
    const { container } = render(<Harness />);
    const input = getInput(container);
    await user.type(input, '1.2,3-4+5e6');
    expect(input.value).toBe('123456');
  });

  it('splices a digit-only paste into the current selection', async () => {
    const user = userEvent.setup();
    const onValue = vi.fn();
    const { container } = render(<Harness onValue={onValue} />);
    const input = getInput(container);
    input.focus();
    await user.paste('1,2.3abc');
    expect(input.value).toBe('123');
    expect(onValue).toHaveBeenLastCalledWith('123');
  });

  it('renders a text input with inputMode numeric', () => {
    const { container } = render(<Harness />);
    const input = getInput(container);
    expect(input).toHaveAttribute('type', 'text');
    expect(input).toHaveAttribute('inputMode', 'numeric');
  });
});
