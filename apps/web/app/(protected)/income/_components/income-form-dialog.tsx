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
import {
  EntryScopeField,
  PRIVATE_SCOPE,
  toHandover,
  type IncomeHandover,
} from '@/app/(protected)/_components/entry-scope-field';
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
import type { Group } from '@/lib/api/groups';
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
  /*
   * X3's scope control, rendered only when supplied AND recording a new entry. Editing never offers
   * it: turning a private entry into a shared one would delete a record of the user's own and write a
   * different one a whole group can see, which is its own act rather than a side effect of an edit.
   */
  scopeGroups?: Group[];
  onScopeChange?: (scope: string, values: IncomeHandover) => void;
  // What a swap from the shared form carried across, seeding this one so nothing typed is lost.
  prefill?: IncomeHandover;
  onSuccess: () => void;
}

export function IncomeFormDialog({
  open,
  onOpenChange,
  income,
  preferredCurrencies,
  supportedCurrencies,
  accounts,
  scopeGroups,
  onScopeChange,
  prefill,
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
    /*
     * A saved entry wins over a handover, and a handover over this form's own empty defaults. The
     * date uses `||` rather than `??` because the shared form always has one — so an untouched date
     * arrives as a real value, while a user who cleared it should get this form's blank.
     */
    toValues: (i) => ({
      date: i?.date ?? prefill?.date ?? '',
      amount: i?.amount ? String(Number(i.amount)) : (prefill?.amount ?? ''),
      currency: i?.currency ?? prefill?.currency ?? '',
      category: (i?.category ?? prefill?.category ?? undefined) as IncomeFormValues['category'],
      notes: i?.notes ?? prefill?.notes ?? '',
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
            {scopeGroups && !isEdit && onScopeChange && (
              <EntryScopeField
                groups={scopeGroups}
                value={PRIVATE_SCOPE}
                hint={tCommon('entryScope.incomeHint')}
                onValueChange={(scope) => onScopeChange(scope, toHandover(form.getValues()))}
                disabled={form.formState.isSubmitting}
              />
            )}

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

            <AccountField
              control={form.control}
              setValue={form.setValue}
              accounts={accounts ?? []}
              currency={watchedCurrency || undefined}
              label={t('form.account.label')}
              name="accountId"
            />

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
