'use client';

import { useEffect, useMemo } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { useTranslations } from 'next-intl';
import { useForm, useWatch } from 'react-hook-form';
import { toast } from 'sonner';

import {
  Button,
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Textarea,
} from '@repo/ui/components';
import { createSettlement } from '@/app/(protected)/credit-cards/credit-card-actions';
import {
  buildSettlementFormSchema,
  type SettlementFormValues,
} from '@/app/(protected)/credit-cards/settlement-form-schema';
import { AccountField } from '@/components/account-field';
import { DatePickerInput } from '@/components/date-picker-input';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/form';
import { FormCombobox } from '@/components/form-combobox';
import { LocaleAmountInput } from '@/components/locale-amount-input';
import type { Account } from '@/lib/api/accounts';

interface SettlementFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  cardId: number;
  // Primary currency first, then any other currencies with activity on this card.
  // Length 1 = single-bucket card (picker hidden). Length > 1 = multi-bucket (picker shown).
  bucketCurrencies: string[];
  // Accounts the payment can be drawn from. Filtered to the settled bucket's currency by AccountField;
  // omitted or empty hides the field entirely (cash-less users see no change).
  accounts?: Account[];
  onSuccess: () => void;
}

export function SettlementFormDialog({
  open,
  onOpenChange,
  cardId,
  bucketCurrencies,
  accounts,
  onSuccess,
}: SettlementFormDialogProps) {
  const t = useTranslations('creditCards');
  const tCommon = useTranslations('common');

  const schema = useMemo(
    () => buildSettlementFormSchema(tCommon('form.errors.required')),
    [tCommon],
  );

  const defaultCurrency = bucketCurrencies[0] ?? '';
  const showBucketPicker = bucketCurrencies.length > 1;

  const form = useForm<SettlementFormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      date: '',
      amount: '',
      currency: defaultCurrency,
      accountId: undefined,
      notes: '',
    },
  });

  const watchedCurrency = useWatch({ control: form.control, name: 'currency' });

  // Reset form when dialog opens — re-anchor currency to the card's primary bucket.
  useEffect(() => {
    if (open) {
      form.reset({
        date: '',
        amount: '',
        currency: defaultCurrency,
        accountId: undefined,
        notes: '',
      });
    }
  }, [open, form, defaultCurrency]);

  async function onSubmit(values: SettlementFormValues) {
    try {
      await createSettlement(cardId, values);
      toast.success(t('settlements.createSuccess'));
      onSuccess();
      onOpenChange(false);
    } catch {
      toast.error(t('settlements.createError'));
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('settlements.addTitle')}</DialogTitle>
        </DialogHeader>

        <Form {...form}>
          <form
            id="settlement-form"
            className="flex flex-col min-w-0 gap-y-4"
            onSubmit={form.handleSubmit(onSubmit)}
            noValidate
          >
            <div className="flex min-w-0 items-start gap-x-3">
              <FormField
                control={form.control}
                name="date"
                render={({ field }) => (
                  <FormItem required className="flex-1">
                    <FormLabel>{t('settlements.form.date')}</FormLabel>
                    <FormControl>
                      <DatePickerInput
                        value={field.value || undefined}
                        onChange={field.onChange}
                        placeholder={t('settlements.form.datePlaceholder')}
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
                    <FormLabel>{t('settlements.form.amount')}</FormLabel>
                    <FormControl>
                      <LocaleAmountInput
                        {...field}
                        currency={watchedCurrency || undefined}
                        placeholder={t('settlements.form.amountPlaceholder')}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            {showBucketPicker && (
              <FormField
                control={form.control}
                name="currency"
                render={({ field }) => (
                  <FormItem required>
                    <FormLabel>{t('settlements.form.bucket')}</FormLabel>
                    <FormControl>
                      <FormCombobox
                        value={field.value}
                        onValueChange={field.onChange}
                        placeholder={t('settlements.form.bucketPlaceholder')}
                        options={bucketCurrencies.map((cur) => ({ value: cur, label: cur }))}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            )}

            {accounts && accounts.length > 0 && (
              <AccountField
                control={form.control}
                setValue={form.setValue}
                accounts={accounts}
                currency={watchedCurrency || undefined}
                label={t('settlements.form.account')}
              />
            )}

            <FormField
              control={form.control}
              name="notes"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>{t('settlements.form.notes')}</FormLabel>
                  <FormControl>
                    <Textarea
                      {...field}
                      placeholder={t('settlements.form.notesPlaceholder')}
                      rows={2}
                    />
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
          <Button blue type="submit" form="settlement-form" disabled={form.formState.isSubmitting}>
            {form.formState.isSubmitting ? t('form.cta.loading') : t('form.cta.label')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
