'use client';

import { useTranslations } from 'next-intl';
import type { Control, FieldPath, FieldValues } from 'react-hook-form';

import { FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/form';
import { FormCombobox } from '@/components/form-combobox';
import type { Account } from '@/lib/api/accounts';

// Form-internal sentinel for "no account" — the API stores null, but a combobox can't bind to
// undefined cleanly, so we round-trip through this value and map it back to undefined.
const NONE_ACCOUNT = 'none';

interface AccountFieldProps<T extends FieldValues> {
  control: Control<T>;
  name: FieldPath<T>;
  // Accounts to choose from. Only active accounts whose currency matches `currency` are offered —
  // a cash balance stays exact, so a link's currency must match the account's.
  accounts: Account[];
  currency: string | undefined;
  label: string;
}

// Optional "paid from / deposited to / drawn from" account selector, shared by the expense, income,
// and settlement forms. Filters to active accounts in the entry's currency; empty when none match.
export function AccountField<T extends FieldValues>({
  control,
  name,
  accounts,
  currency,
  label,
}: AccountFieldProps<T>) {
  const t = useTranslations('common');
  const matching = accounts.filter((a) => a.isActive && (!currency || a.currency === currency));

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
