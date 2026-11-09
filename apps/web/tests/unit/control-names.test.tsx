import { forwardRef, type ComponentProps, type ReactNode } from 'react';
import { render, screen } from '@testing-library/react';
import { NextIntlClientProvider } from 'next-intl';
import { useForm } from 'react-hook-form';
import { describe, expect, it, vi } from 'vitest';

import { PotShareRows } from '@/app/(protected)/shared/_components/pot-share-rows';
import type { PotOpeningFormValues } from '@/app/(protected)/shared/pot-form-schema';
import { ComboboxMultiSelect } from '@/components/combobox-multi-select';
import { Form } from '@/components/form';
import type { GroupMember } from '@/lib/api/groups';
import en from '../../translations/en.json';
import es from '../../translations/es.json';

/*
 * Two controls a screen reader announced with no useful name: the ✕ on a selected chip (an icon and
 * nothing else), and each owner's percentage field in a pot's opening split (named only by its "0"
 * placeholder, so every row read the same). Both are named in the reader's language.
 */

// A stand-in's props minus the ones only the real component understands.
function without<T extends object>(props: T, key: string): Partial<T> {
  return Object.fromEntries(Object.entries(props).filter(([name]) => name !== key)) as Partial<T>;
}

// Radix cannot mount in this suite (a second React copy): plain stand-ins for what these render.
vi.mock('@repo/ui/components', () => {
  const passthrough = ({ children }: { children?: ReactNode }) => <div>{children}</div>;
  return {
    Button: forwardRef<HTMLButtonElement, ComponentProps<'button'>>(function Button(props, ref) {
      return <button type="button" ref={ref} {...props} />;
    }),
    Command: passthrough,
    CommandEmpty: passthrough,
    CommandGroup: passthrough,
    CommandInput: () => null,
    CommandItem: passthrough,
    CommandList: passthrough,
    Input: forwardRef<HTMLInputElement, ComponentProps<'input'> & { containerClassName?: string }>(
      function Input(props, ref) {
        return <input ref={ref} {...without(props, 'containerClassName')} />;
      },
    ),
    Label: (props: ComponentProps<'label'> & { required?: boolean }) => (
      <label {...without(props, 'required')} />
    ),
    Popover: passthrough,
    PopoverContent: () => null,
    PopoverTrigger: ({ children }: { children: ReactNode }) => children,
  };
});
vi.mock('@/components/truncating-tooltip', () => ({
  TruncatingTooltip: ({ text }: { text: string }) => <span>{text}</span>,
}));

const LOCALES = { en, es } as const;

function seat(id: number, displayName: string): GroupMember {
  return {
    id,
    displayName,
    role: 'member',
    isActive: true,
    isLinked: true,
    isSelf: false,
    hasPendingInvite: false,
    joinedAt: null,
    createdAt: '2026-11-01T00:00:00Z',
    updatedAt: '2026-11-01T00:00:00Z',
  };
}

function Shares() {
  const form = useForm<PotOpeningFormValues>({
    defaultValues: {
      shares: [
        { memberId: 1, percentage: '' },
        { memberId: 2, percentage: '' },
      ],
    } as unknown as PotOpeningFormValues,
  });
  return (
    <Form {...form}>
      <PotShareRows form={form} seats={[seat(1, 'Ana'), seat(2, 'Beto')]} showTotalError={false} />
    </Form>
  );
}

function inLocale(locale: 'en' | 'es', children: ReactNode) {
  return (
    <NextIntlClientProvider locale={locale} messages={LOCALES[locale]} timeZone="UTC">
      {children}
    </NextIntlClientProvider>
  );
}

describe.each(['en', 'es'] as const)('control names (%s)', (locale) => {
  const copy = LOCALES[locale];

  it('names a chip’s remove button after the chip', () => {
    render(
      inLocale(
        locale,
        <ComboboxMultiSelect
          items={[
            { id: 1, label: 'Core' },
            { id: 2, label: 'Growth' },
          ]}
          selectedIds={[1, 2]}
          onToggle={() => {}}
          placeholder="Collections"
          searchPlaceholder="Search"
          emptyMessage="None"
          showChips
        />,
      ),
    );
    const name = copy.common.combobox.remove.replace('{label}', 'Growth');
    expect(screen.getByRole('button', { name })).toBeInTheDocument();
  });

  it('names each owner’s percentage field after the owner', () => {
    render(inLocale(locale, <Shares />));
    for (const owner of ['Ana', 'Beto']) {
      const name = copy.shared.pots.opening.shares.inputLabel.replace('{name}', owner);
      expect(screen.getByRole('textbox', { name })).toBeInTheDocument();
    }
  });
});
