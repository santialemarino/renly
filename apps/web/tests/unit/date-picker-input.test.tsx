import {
  cloneElement,
  createContext,
  forwardRef,
  useContext,
  useState,
  type ComponentProps,
  type ReactElement,
  type ReactNode,
} from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { NextIntlClientProvider } from 'next-intl';
import { describe, expect, it, vi } from 'vitest';

import { DatePickerInput } from '@/components/date-picker-input';
import messages from '../../translations/en.json';

/*
 * Every date field in the app is this one component, and picking a day must close its calendar. Left
 * open, the calendar covered the field below it and swallowed the next click (the reader had to click
 * twice to reach the next field, in every form with a date).
 *
 * Radix cannot mount in this suite (a second React copy), so the popover is a small stand-in that
 * behaves like Radix's does: controlled when given `open`, holding its own state when not. The
 * calendar is a stand-in too, with one day to pick.
 */

const PopoverState = createContext<{ open: boolean; setOpen: (open: boolean) => void }>({
  open: false,
  setOpen: () => {},
});

vi.mock('@repo/ui/components', () => ({
  Button: forwardRef<HTMLButtonElement, ComponentProps<'button'>>(function Button(props, ref) {
    return <button type="button" ref={ref} {...props} />;
  }),
  Popover: function Popover({
    open,
    onOpenChange,
    children,
  }: {
    open?: boolean;
    onOpenChange?: (open: boolean) => void;
    children: ReactNode;
  }) {
    const [own, setOwn] = useState(false);
    const isOpen = open ?? own;
    const setOpen = (next: boolean) => {
      onOpenChange?.(next);
      if (open === undefined) setOwn(next);
    };
    return (
      <PopoverState.Provider value={{ open: isOpen, setOpen }}>{children}</PopoverState.Provider>
    );
  },
  PopoverTrigger: function PopoverTrigger({
    children,
  }: {
    children: ReactElement<{ onClick?: () => void }>;
  }) {
    const { open, setOpen } = useContext(PopoverState);
    return cloneElement(children, { onClick: () => setOpen(!open) });
  },
  PopoverContent: function PopoverContent({ children }: { children: ReactNode }) {
    const { open } = useContext(PopoverState);
    return open ? <div data-testid="calendar-popover">{children}</div> : null;
  },
  Calendar: ({ onSelect }: { onSelect: (date: Date | undefined) => void }) => (
    <>
      <button type="button" onClick={() => onSelect(new Date(2026, 10, 5))}>
        5
      </button>
      <button type="button" onClick={() => onSelect(undefined)}>
        selected day
      </button>
    </>
  ),
}));

function picker(onChange: (value: string) => void) {
  return (
    <NextIntlClientProvider locale="en" messages={messages} timeZone="UTC">
      <DatePickerInput value="2026-11-01" onChange={onChange} data-testid="date" />
    </NextIntlClientProvider>
  );
}

describe('DatePickerInput', () => {
  it('closes once a day is picked', () => {
    const onChange = vi.fn();
    render(picker(onChange));
    fireEvent.click(screen.getByTestId('date'));
    expect(screen.getByTestId('calendar-popover')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '5' }));
    expect(onChange).toHaveBeenCalledWith('2026-11-05');
    expect(screen.queryByTestId('calendar-popover')).not.toBeInTheDocument();
  });

  it('closes, keeping the value, when the chosen day is clicked again', () => {
    const onChange = vi.fn();
    render(picker(onChange));
    fireEvent.click(screen.getByTestId('date'));
    fireEvent.click(screen.getByRole('button', { name: 'selected day' }));
    expect(onChange).not.toHaveBeenCalled();
    expect(screen.queryByTestId('calendar-popover')).not.toBeInTheDocument();
  });
});
