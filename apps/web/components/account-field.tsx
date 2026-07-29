'use client';

import { useEffect } from 'react';
import { useTranslations } from 'next-intl';
import { useWatch, type Control, type FieldValues, type UseFormSetValue } from 'react-hook-form';

import { FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/form';
import { FormCombobox } from '@/components/form-combobox';
import type { Account } from '@/lib/api/accounts';

// Form-internal sentinel for "no account" — the API stores null, but a combobox can't bind to
// undefined cleanly, so we round-trip through this value and map it back to undefined.
const NONE_ACCOUNT = 'none';

// Minimal form shape this component operates on. Every embedding form schema must declare `accountId`.
export type AccountFieldFormValues = {
  accountId?: number;
};

interface AccountFieldProps<T extends AccountFieldFormValues & FieldValues> {
  control: Control<T>;
  setValue: UseFormSetValue<T>;
  // Accounts to choose from. Only active accounts whose currency matches `currency` are offered —
  // a cash balance stays exact, so a link's currency must match the account's.
  accounts: Account[];
  currency: string | undefined;
  label: string;
}

// Optional "paid from / deposited to / drawn from" account selector, shared by the expense, income,
// and settlement forms. Filters to active accounts in the entry's currency; empty when none match.
// Clears a now-invalid selection when the entry currency changes (mirrors PaymentMethodFields'
// clear-card-on-method-change), so a stale mismatched account can never be submitted.
export function AccountField<T extends AccountFieldFormValues & FieldValues>({
  control: controlProp,
  setValue: setValueProp,
  accounts,
  currency,
  label,
}: AccountFieldProps<T>) {
  /*
   * Narrow the caller's form typing to the minimal shape. Safe because T extends
   * AccountFieldFormValues and this component only reads/writes the accountId field.
   * (RHF's Control/SetValue generics are invariant, so a direct assignment won't compile.)
   */
  const control = controlProp as unknown as Control<AccountFieldFormValues>;
  const setValue = setValueProp as unknown as UseFormSetValue<AccountFieldFormValues>;

  const t = useTranslations('common');
  const selectedId = useWatch({ control, name: 'accountId' });
  const matching = accounts.filter((a) => a.isActive && (!currency || a.currency === currency));
  const selected = accounts.find((a) => a.id === selectedId);

  // Clear only when the selected account is a known active account whose currency no longer matches
  // (e.g. the user changed the currency after picking it). A link to an archived account — absent
  // from the active list — is left untouched so editing an entry never silently drops its link.
  useEffect(() => {
    if (selected && currency && selected.currency !== currency) {
      setValue('accountId', undefined);
    }
  }, [selected, currency, setValue]);

  return (
    <FormField
      control={control}
      name="accountId"
      render={({ field }) => (
        <FormItem>
          <FormLabel>{label}</FormLabel>
          <FormControl>
            <FormCombobox
              value={field.value != null ? String(field.value) : NONE_ACCOUNT}
              onValueChange={(v) => field.onChange(v === NONE_ACCOUNT ? undefined : Number(v))}
              disabled={matching.length === 0}
              placeholder={
                matching.length === 0 && currency
                  ? t('accountField.noneForCurrency', { currency })
                  : t('accountField.placeholder')
              }
              options={[
                { value: NONE_ACCOUNT, label: t('accountField.none') },
                ...matching.map((a) => ({ value: String(a.id), label: a.name })),
              ]}
            />
          </FormControl>
          <FormMessage />
        </FormItem>
      )}
    />
  );
}
