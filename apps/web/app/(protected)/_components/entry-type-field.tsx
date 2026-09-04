'use client';

import { useTranslations } from 'next-intl';

import { Label } from '@repo/ui/components';
import { PillToggleGroup } from '@/components/pill-toggle-group';
import { ENTRY_TYPES, type EntryType } from '@/lib/constants/entries';

interface EntryTypeFieldProps {
  // Which kind of entry the form on screen records. Fixed per form rather than passed as state — an
  // expense form records an expense — so the control only ever has to report the other value.
  value: EntryType;
  // Fires with the kind the user picked. The caller SWAPS which form is on screen rather than storing
  // this: an expense and a piece of income are different records in different tables, so there is no
  // single form that could submit either.
  onValueChange: (value: EntryType) => void;
  disabled?: boolean;
}

/*
 * Which kind of entry is being recorded — an expense or a piece of income.
 *
 * The same place and the same job as `EntryScopeField`, which sits directly beneath it and answers the
 * other half of "which record am I writing" — a labelled control that swaps the form rather than a
 * field in its schema. A toggle rather than that one's dropdown, though: there are exactly two values,
 * and the whole point of the surface this belongs to is speed, so a dropdown would cost two clicks
 * where one will do.
 *
 * Rendered only by the global quick-add. Every other door into these forms opens for one specific kind
 * of entry, which is why the prop that turns it on is optional and unsupplied there.
 */
export function EntryTypeField({ value, onValueChange, disabled }: EntryTypeFieldProps) {
  const tCommon = useTranslations('common');

  return (
    <div className="flex flex-col gap-y-2">
      <Label>{tCommon('entryType.label')}</Label>
      <PillToggleGroup
        ariaLabel={tCommon('entryType.label')}
        items={ENTRY_TYPES.map((type) => ({ value: type, label: tCommon(`entryType.${type}`) }))}
        value={value}
        // Radix types a toggle-group value as `string`; the options ARE `ENTRY_TYPES`, so the cast
        // states that rather than guessing. A runtime narrowing here would be a branch nothing can
        // reach.
        onValueChange={(next) => onValueChange(next as EntryType)}
        disabled={disabled}
      />
    </div>
  );
}
