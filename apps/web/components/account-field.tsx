'use client';

import { useEffect } from 'react';
import { useTranslations } from 'next-intl';
import { useWatch, type Control, type FieldValues, type UseFormSetValue } from 'react-hook-form';

import { FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/form';
import { FormCombobox } from '@/components/form-combobox';
import type { Account } from '@/lib/api/accounts';
import {
  buildAccountFieldOptions,
  shouldClearAccountLink,
  type AccountOption,
} from '@/lib/utils/account-field-options';

/*
 * Form-internal sentinel for "no account" — the API stores null, but a combobox can't bind to a
 * nullish value cleanly, so we round-trip through this value and map it back to `null`.
 *
 * Clearing MUST write `null`, never `undefined`: react-hook-form falls back to `defaultValues`
 * whenever a field's value is `undefined`, so an `undefined` write left the trigger displaying the
 * originally-loaded account while form state was actually empty — the field looked unchanged while
 * submitting a cleared link.
 */
const NONE_ACCOUNT = 'none';

// The field this control binds to. `accountId` is the money-link on an expense / income / settlement;
// `defaultAccountId` is the standing default on a credit card or a recurring plan.
export type AccountFieldName = 'accountId' | 'defaultAccountId';

// Minimal form shape this component operates on. Every embedding form schema must declare the field it
// binds as nullable (`z.number().nullable().optional()`) so clearing can round-trip through `null`.
export type AccountFieldFormValues = {
  accountId?: number | null;
  defaultAccountId?: number | null;
};

interface AccountFieldProps<T extends AccountFieldFormValues & FieldValues> {
  control: Control<T>;
  setValue: UseFormSetValue<T>;
  // Accounts to choose from. Only active accounts whose currency matches `currency` are offered —
  // a cash balance stays exact, so a link's currency must match the account's.
  accounts: Account[];
  currency: string | undefined;
  label: string;
  // Defaults to the entry money-link field.
  name?: AccountFieldName;
}

// Optional "paid from / deposited to / drawn from" account selector, shared by the expense, income and
// settlement forms, and by the standing-default field on a credit card or a recurring plan. The option
// and clearing rules live in lib/utils/account-field-options (pure and unit-tested); this component
// owns the localized labels and the react-hook-form wiring.
export function AccountField<T extends AccountFieldFormValues & FieldValues>({
  control: controlProp,
  setValue: setValueProp,
  accounts,
  currency,
  label,
  name = 'accountId',
}: AccountFieldProps<T>) {
  /*
   * Narrow the caller's form typing to the minimal shape. Safe because T extends
   * AccountFieldFormValues and this component only reads/writes the one field it was given.
   * (RHF's Control/SetValue generics are invariant, so a direct assignment won't compile.)
   */
  const control = controlProp as unknown as Control<AccountFieldFormValues>;
  const setValue = setValueProp as unknown as UseFormSetValue<AccountFieldFormValues>;

  const t = useTranslations('common');
  const selectedId = useWatch({ control, name });
  const selected = accounts.find((a) => a.id === selectedId);
  const options = buildAccountFieldOptions(accounts, currency, selectedId);

  // Drop a selection the entry's currency has moved away from (mirrors PaymentMethodFields'
  // clear-card-on-method-change), so a stale mismatched account can never be submitted.
  useEffect(() => {
    if (shouldClearAccountLink(selected, currency)) setValue(name, null);
  }, [selected, currency, setValue, name]);

  // Localizes one option row; the sentinel names the currency when nothing matches, turning a
  // dead-end disabled field into an explanation ("No ARS accounts" rather than a greyed-out "None").
  function optionLabel(option: AccountOption): string {
    if (option.kind === 'none') {
      return option.noMatchingCurrency && currency
        ? t('accountField.noneForCurrency', { currency })
        : t('accountField.none');
    }
    if (option.kind === 'archived') {
      return t('accountField.archived', { name: option.account.name });
    }
    return option.account.name;
  }

  if (options === null) return null;

  return (
    <FormField
      control={control}
      name={name}
      render={({ field }) => (
        <FormItem>
          <FormLabel>{label}</FormLabel>
          <FormControl>
            <FormCombobox
              value={field.value != null ? String(field.value) : NONE_ACCOUNT}
              onValueChange={(v) => field.onChange(v === NONE_ACCOUNT ? null : Number(v))}
              disabled={options.length === 1}
              options={options.map((option) => ({
                value: option.kind === 'none' ? NONE_ACCOUNT : String(option.account.id),
                label: optionLabel(option),
              }))}
            />
          </FormControl>
          <FormMessage />
        </FormItem>
      )}
    />
  );
}
