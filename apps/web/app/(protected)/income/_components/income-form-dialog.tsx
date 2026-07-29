'use client';

import { useMemo } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { useLocale, useTranslations } from 'next-intl';
import { useForm, useWatch } from 'react-hook-form';

import {
  Button,
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Textarea,
} from '@repo/ui/components';
import { CurrencyCombobox } from '@/app/(protected)/_components/currency-combobox';
import { createIncome, updateIncome } from '@/app/(protected)/income/income-actions';
import {
  buildIncomeFormSchema,
  type IncomeFormValues,
} from '@/app/(protected)/income/income-form-schema';
import { AccountField } from '@/components/account-field';
import { DatePickerInput } from '@/components/date-picker-input';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/form';
import { FormCombobox } from '@/components/form-combobox';
import { LocaleAmountInput } from '@/components/locale-amount-input';
import type { Account } from '@/lib/api/accounts';
import type { IncomeEntry } from '@/lib/api/income';
import { useEntityFormDialog } from '@/lib/hooks/use-entity-form-dialog';
import { sortIncomeCategoriesByLabel } from '@/lib/utils/categories';

interface IncomeFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  income?: IncomeEntry;
  preferredCurrencies?: string[];
  supportedCurrencies?: string[];
  accounts?: Account[];
  onSuccess: () => void;
}

export function IncomeFormDialog({
  open,
  onOpenChange,
  income,
  preferredCurrencies,
  supportedCurrencies,
  accounts,
  onSuccess,
}: IncomeFormDialogProps) {
  const locale = useLocale();
  const t = useTranslations('income');
  const tCommon = useTranslations('common');

  const schema = useMemo(() => buildIncomeFormSchema(tCommon('form.errors.required')), [tCommon]);

  const form = useForm<IncomeFormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      date: '',
      amount: '',
      currency: '',
      category: undefined,
      notes: '',
      accountId: undefined,
    },
  });

  const isEdit = !!income;
  const watchedCurrency = useWatch({ control: form.control, name: 'currency' });

  const sortedCategories = sortIncomeCategoriesByLabel((key) => tCommon(key), locale);

  const { submitWithLifecycle } = useEntityFormDialog({
    open,
    onOpenChange,
    form,
    entity: income,
    toValues: (i) => ({
      date: i?.date ?? '',
      amount: i?.amount ? String(Number(i.amount)) : '',
      currency: i?.currency ?? '',
      category: (i?.category ?? undefined) as IncomeFormValues['category'],
      notes: i?.notes ?? '',
      accountId: i?.accountId ?? undefined,
    }),
    onSuccess,
  });

  async function onSubmit(values: IncomeFormValues) {
    await submitWithLifecycle(
      () => (isEdit ? updateIncome(income.id, values) : createIncome(values)),
      t(isEdit ? 'form.updateSuccess' : 'form.createSuccess'),
      t('form.saveError'),
    );
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{isEdit ? t('form.titleEdit') : t('form.titleCreate')}</DialogTitle>
        </DialogHeader>

        <Form {...form}>
          <form
            id="income-form"
            className="flex flex-col min-w-0 gap-y-4"
            onSubmit={form.handleSubmit(onSubmit)}
            noValidate
          >
            <FormField
              control={form.control}
              name="date"
              render={({ field }) => (
                <FormItem required>
                  <FormLabel>{t('form.date.label')}</FormLabel>
                  <FormControl>
                    <DatePickerInput
                      value={field.value || undefined}
                      onChange={field.onChange}
                      placeholder={t('form.date.placeholder')}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <div className="flex min-w-0 items-start gap-x-3">
              <FormField
                control={form.control}
                name="currency"
                render={({ field }) => (
                  <FormItem required className="flex-1 min-w-0">
                    <FormLabel>{t('form.currency.label')}</FormLabel>
                    <FormControl>
                      <CurrencyCombobox
                        compact
                        value={field.value || null}
                        exclude={[]}
                        preferredCurrencies={preferredCurrencies}
                        codes={supportedCurrencies}
                        placeholder={t('form.currency.placeholder')}
                        searchPlaceholder={t('form.currency.searchPlaceholder')}
                        noResults={t('form.currency.noResults')}
                        onChange={field.onChange}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="amount"
                render={({ field }) => (
                  <FormItem required className="flex-1">
                    <FormLabel>{t('form.amount.label')}</FormLabel>
                    <FormControl>
                      <LocaleAmountInput
                        {...field}
                        currency={watchedCurrency || undefined}
                        placeholder={t('form.amount.placeholder')}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            <FormField
              control={form.control}
              name="category"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>{t('form.category.label')}</FormLabel>
                  <FormControl>
                    <FormCombobox
                      value={field.value ?? ''}
                      onValueChange={field.onChange}
                      placeholder={t('form.category.placeholder')}
                      options={sortedCategories.map((cat) => ({
                        value: cat,
                        label: tCommon(`categories.${cat}`),
                      }))}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            {accounts && accounts.length > 0 && (
              <AccountField
                control={form.control}
                setValue={form.setValue}
                accounts={accounts}
                currency={watchedCurrency || undefined}
                label={t('form.account.label')}
              />
            )}

            <FormField
              control={form.control}
              name="notes"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>{t('form.notes.label')}</FormLabel>
                  <FormControl>
                    <Textarea {...field} placeholder={t('form.notes.placeholder')} rows={2} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
          </form>
        </Form>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t('form.cancel')}
          </Button>
          <Button blue type="submit" form="income-form" disabled={form.formState.isSubmitting}>
            {form.formState.isSubmitting ? t('form.cta.loading') : t('form.cta.label')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
