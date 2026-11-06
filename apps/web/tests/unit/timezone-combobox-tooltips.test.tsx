import { createElement, type ReactNode } from 'react';
import { act, render } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { TimezoneCombobox } from '@/app/(protected)/_components/timezone-combobox';
import { formatIanaTimezone, IANA_TIMEZONES } from '@/lib/constants/timezones';

/*
 * The timezone list mounts a truncation tooltip on the HIGHLIGHTED option only — the one a pointer is
 * over or the arrows are on — rather than one per option. One per option meant ~420 Radix tooltips and
 * ResizeObservers on every open, more than half of what opening the list cost.
 *
 * The Radix and cmdk pieces resolve a second React copy under jsdom, so `@repo/ui/components` is
 * replaced by plain elements that always render their children; the mocked `Command` keeps the
 * highlight callback cmdk would call, so the test can move the highlight the way a pointer does.
 */

const command: { onValueChange?: (value: string) => void } = {};

vi.mock('@repo/ui/components', () => {
  const plain = (tag: string) =>
    function Plain({ children, ...props }: Record<string, unknown> & { children?: ReactNode }) {
      const rest = Object.fromEntries(
        Object.entries(props).filter(
          ([key]) =>
            !['asChild', 'variant', 'size', 'onValueChange', 'shouldFilter', 'onSelect'].includes(
              key,
            ),
        ),
      );
      return createElement(tag, rest, children);
    };
  const passthrough = ({ children }: { children?: ReactNode }) => children;
  return {
    Button: plain('button'),
    Command: ({
      children,
      onValueChange,
    }: {
      children?: ReactNode;
      onValueChange?: (value: string) => void;
    }) => {
      command.onValueChange = onValueChange;
      return createElement('div', null, children);
    },
    CommandEmpty: plain('div'),
    CommandInput: plain('input'),
    CommandItem: plain('div'),
    CommandList: plain('div'),
    Popover: plain('div'),
    PopoverContent: plain('div'),
    PopoverTrigger: plain('div'),
    Separator: plain('hr'),
    Tooltip: passthrough,
    TooltipContent: () => null,
    TooltipTrigger: passthrough,
  };
});

function renderList() {
  return render(
    <TimezoneCombobox
      value={null}
      placeholder="Timezone"
      searchPlaceholder="Search timezones..."
      noResults="None"
      onChange={() => {}}
    />,
  );
}

// The option labels that carry a truncation tooltip (the trigger's placeholder is outside the list).
function tooltipped(container: HTMLElement): string[] {
  return [...container.querySelectorAll('[value]:not(input) [data-truncating-tooltip]')].map(
    (el) => el.textContent ?? '',
  );
}

describe('the timezone list', () => {
  it('lists every zone with no tooltip mounted before anything is highlighted', () => {
    const { container } = renderList();
    expect(container.querySelectorAll('[value]:not(input)').length).toBe(IANA_TIMEZONES.length);
    expect(IANA_TIMEZONES.length).toBeGreaterThan(400);
    expect(tooltipped(container)).toEqual([]);
  });

  it('mounts the tooltip on the highlighted option only, and moves it with the highlight', () => {
    const { container } = renderList();
    const [first, second] = [IANA_TIMEZONES[10], IANA_TIMEZONES[200]] as [string, string];
    act(() => command.onValueChange?.(first));
    expect(tooltipped(container)).toEqual([formatIanaTimezone(first)]);
    act(() => command.onValueChange?.(second));
    expect(tooltipped(container)).toEqual([formatIanaTimezone(second)]);
  });
});
