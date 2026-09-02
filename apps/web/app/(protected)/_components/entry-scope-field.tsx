'use client';

import { Users } from 'lucide-react';
import { useTranslations } from 'next-intl';

import { Label } from '@repo/ui/components';
import { FormCombobox } from '@/components/form-combobox';
import type { Group } from '@/lib/api/groups';
import type { ExpenseCategory, IncomeCategory } from '@/lib/constants/categories';

// The value the picker carries for "this is mine alone", which is every entry a solo user records.
export const PRIVATE_SCOPE = 'private';

/*
 * What one entry form hands the other when the scope changes, so nothing typed is lost across the
 * swap.
 *
 * Deliberately only the fields the two records genuinely share. A shared expense has no obligation,
 * subscription or installment link; a private one has no participants or split; a shared income row
 * has a destination and a source asset that no private entry has; and their funding is the same
 * question with opposite answers — a private entry cannot touch joint money at all, which is the whole
 * reason this control exists. Carrying any of those across would mean seeding a field the receiving
 * form never asked about.
 *
 * Generic over the category so each list keeps its own enum: an expense category is not an income
 * category, and a handover that typed them as plain strings would let one reach the other's picker,
 * which renders a blank field and submits a value the API refuses with a 422.
 */
export interface EntryHandover<TCategory extends string = string> {
  date?: string;
  amount?: string;
  currency?: string;
  category?: TCategory;
  notes?: string;
}

// Narrows either form's values to what crosses the swap. One function so the two directions cannot
// come to disagree about which fields survive it.
export function toHandover<TCategory extends string>(
  values: EntryHandover<TCategory>,
): EntryHandover<TCategory> {
  return {
    date: values.date,
    amount: values.amount,
    currency: values.currency,
    category: values.category,
    notes: values.notes,
  };
}

// The two lists' handovers, bound to their own category enum. Named here rather than beside each form
// so there is one place that says what crosses the swap and one place that says it per list.
export type ExpenseHandover = EntryHandover<ExpenseCategory>;
export type IncomeHandover = EntryHandover<IncomeCategory>;

interface EntryScopeFieldProps {
  // The groups the user belongs to. The control renders nothing when this is empty, which is X3's
  // rule and every public user's first weeks: a solo user sees zero added friction.
  groups: Group[];
  // The current scope: PRIVATE_SCOPE, or a group id as a string.
  value: string;
  // Fires with the new scope. The caller SWAPS which form is on screen rather than storing this —
  // a private entry and a shared one are different records in different tables, not one record
  // with a flag, so there is no single form that could submit either.
  onValueChange: (value: string) => void;
  /*
   * What sharing this KIND of entry means, in one line under the control.
   *
   * A prop rather than a string of this component's own, because the shape is shared and the words
   * are not: a shared expense becomes your share of a bill, while shared income becomes your share of
   * money the group received and may leave somebody holding the rest. The label above and the two
   * option names ARE the same for both and stay here.
   */
  hint: string;
  disabled?: boolean;
}

/*
 * Who an entry is for: just the person recording it, or a group they belong to.
 *
 * It is a MODE rather than a field, and deliberately not part of either form's schema. The two are
 * separate records in separate tables with separate rules — a private entry cannot touch joint money
 * at all (400 private_entry_from_shared_account), and a shared one has participants, a split method
 * and no owner — so the honest control is one that changes which form you are filling in, carrying
 * across what the two genuinely have in common.
 *
 * This is also the answer to the case that has no other door. A shared account belongs to no user, so
 * it can never appear in a private form's account picker; without this control, somebody whose
 * groceries came out of the joint account — or whose rent arrived in it — would look for that account,
 * not find it, and record the entry against nothing. The API's refusal is a backstop for a request
 * that gets past the UI, not the path anybody should meet.
 *
 * Offered on CREATE only. Turning an existing private entry into a shared one would delete a record of
 * the user's own and write a different one that a whole group can see — a visibility change large
 * enough to be its own act, not a side effect of editing an amount.
 */
export function EntryScopeField({
  groups,
  value,
  onValueChange,
  hint,
  disabled,
}: EntryScopeFieldProps) {
  const tCommon = useTranslations('common');

  if (groups.length === 0) return null;

  return (
    <div className="flex flex-col gap-y-2">
      <Label htmlFor="entry-scope">{tCommon('entryScope.label')}</Label>
      <FormCombobox
        id="entry-scope"
        value={value}
        onValueChange={onValueChange}
        disabled={disabled}
        className="w-full"
        options={[
          { value: PRIVATE_SCOPE, label: tCommon('entryScope.private') },
          ...groups.map((group) => ({
            value: String(group.id),
            label: group.name,
            icon: Users,
            group: tCommon('entryScope.groupsHeading'),
          })),
        ]}
      />
      <p className="text-paragraph-xs text-muted-foreground">{hint}</p>
    </div>
  );
}
