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
  Input,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Textarea,
} from '@repo/ui/components';
import { CurrencyCombobox } from '@/app/(protected)/_components/currency-combobox';
import {
  createPaymentObligation,
  updatePaymentObligation,
} from '@/app/(protected)/payment-obligations/payment-obligation-actions';
import {
  buildPaymentObligationFormSchema,
  type PaymentObligationFormValues,
} from '@/app/(protected)/payment-obligations/payment-obligation-form-schema';
import { DatePickerInput } from '@/components/date-picker-input';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/form';
import { LocaleAmountInput } from '@/components/locale-amount-input';
import { PaymentMethodFields } from '@/components/payment-method-fields';
import type { CreditCard } from '@/lib/api/credit-cards';
import type { PaymentObligation } from '@/lib/api/payment-obligations';
import { OBLIGATION_RECURRENCES } from '@/lib/constants/recurrences';
import { useEntityFormDialog } from '@/lib/hooks/use-entity-form-dialog';
import { sortExpenseCategoriesByLabel } from '@/lib/utils/categories';

// Form-internal sentinel for "no recurrence" — the API stores NULL, but a Select
// can't bind to undefined cleanly, so we round-trip through an empty string and
// strip it back to undefined in onSubmit.
const NONE_RECURRENCE = 'none';

interface PaymentObligationFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  obligation?: PaymentObligation;
  preferredCurrencies?: string[];
  creditCards?: CreditCard[];
  onSuccess: () => void;
}

export function PaymentObligationFormDialog({
  open,
  onOpenChange,
  obligation,
  preferredCurrencies,
  creditCards,
  onSuccess,
}: PaymentObligationFormDialogProps) {
  const locale = useLocale();
  const t = useTranslations('paymentObligations');
  const tCommon = useTranslations('common');

  const schema = useMemo(
    () => buildPaymentObligationFormSchema(tCommon('form.errors.required')),
    [tCommon],
  );

  const form = useForm<PaymentObligationFormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      name: '',
      amount: '',
      currency: '',
      nextDueDate: '',
      recurrence: undefined,
      category: '',
      expenseCategory: undefined,
      paymentMethod: undefined,
      creditCardId: undefined,
      notes: '',
    },
  });

  const isEdit = !!obligation;
  const watchedCurrency = useWatch({ control: form.control, name: 'currency' });

  const sortedExpenseCategories = sortExpenseCategoriesByLabel((key) => tCommon(key), locale);

  const { submitWithLifecycle } = useEntityFormDialog({
    open,
    onOpenChange,
    form,
    entity: obligation,
    toValues: (o) => ({
      name: o?.name ?? '',
      amount: o?.amount ? String(Number(o.amount)) : '',
      currency: o?.currency ?? '',
      nextDueDate: o?.nextDueDate ?? '',
      recurrence: (o?.recurrence ?? undefined) as PaymentObligationFormValues['recurrence'],
      category: o?.category ?? '',
      expenseCategory: (o?.expenseCategory ??
        undefined) as PaymentObligationFormValues['expenseCategory'],
      paymentMethod: (o?.paymentMethod ??
        undefined) as PaymentObligationFormValues['paymentMethod'],
      creditCardId: o?.creditCardId ?? undefined,
      notes: o?.notes ?? '',
    }),
    onSuccess,
  });

  async function onSubmit(values: PaymentObligationFormValues) {
    await submitWithLifecycle(
      () =>
        isEdit ? updatePaymentObligation(obligation.id, values) : createPaymentObligation(values),
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
            id="payment-obligation-form"
            className="flex flex-col min-w-0 gap-y-4"
            onSubmit={form.handleSubmit(onSubmit)}
            noValidate
          >
            <FormField
              control={form.control}
              name="name"
              render={({ field }) => (
                <FormItem required>
                  <FormLabel>{t('form.name.label')}</FormLabel>
                  <FormControl>
                    <Input {...field} placeholder={t('form.name.placeholder')} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <div className="flex min-w-0 items-start gap-x-3">
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
            </div>

            <div className="flex min-w-0 items-start gap-x-3">
              <FormField
                control={form.control}
                name="nextDueDate"
                render={({ field }) => (
                  <FormItem required className="flex-1">
                    <FormLabel>{t('form.dueDate.label')}</FormLabel>
                    <FormControl>
                      <DatePickerInput
                        value={field.value || undefined}
                        onChange={field.onChange}
                        placeholder={t('form.dueDate.placeholder')}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="recurrence"
                render={({ field }) => (
                  <FormItem className="flex-1">
                    <FormLabel>{t('form.recurrence.label')}</FormLabel>
                    <Select
                      value={field.value ?? NONE_RECURRENCE}
                      onValueChange={(v) =>
                        field.onChange(
                          v === NONE_RECURRENCE
                            ? undefined
                            : (v as PaymentObligationFormValues['recurrence']),
                        )
                      }
                    >
                      <FormControl>
                        <SelectTrigger className="w-full">
                          <SelectValue placeholder={t('form.recurrence.placeholder')} />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem value={NONE_RECURRENCE}>{t('recurrences.oneOff')}</SelectItem>
                        {OBLIGATION_RECURRENCES.map((r) => (
                          <SelectItem key={r} value={r}>
                            {t(`recurrences.${r}`)}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            <div className="flex min-w-0 items-start gap-x-3">
              <FormField
                control={form.control}
                name="category"
                render={({ field }) => (
                  <FormItem className="flex-1">
                    <FormLabel>{t('form.category.label')}</FormLabel>
                    <FormControl>
                      <Input {...field} placeholder={t('form.category.placeholder')} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="expenseCategory"
                render={({ field }) => (
                  <FormItem className="flex-1">
                    <FormLabel>{t('form.expenseCategory.label')}</FormLabel>
                    <Select
                      value={field.value ?? ''}
                      onValueChange={(v) =>
                        field.onChange(v as PaymentObligationFormValues['expenseCategory'])
                      }
                    >
                      <FormControl>
                        <SelectTrigger className="w-full">
                          <SelectValue placeholder={t('form.expenseCategory.placeholder')} />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        {sortedExpenseCategories.map((cat) => (
                          <SelectItem key={cat} value={cat}>
                            {tCommon(`categories.${cat}`)}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            <PaymentMethodFields
              control={form.control}
              setValue={form.setValue}
              creditCards={creditCards}
              preferredCurrencies={preferredCurrencies}
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
          <Button
            blue
            type="submit"
            form="payment-obligation-form"
            disabled={form.formState.isSubmitting}
          >
            {form.formState.isSubmitting ? t('form.cta.loading') : t('form.cta.label')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
