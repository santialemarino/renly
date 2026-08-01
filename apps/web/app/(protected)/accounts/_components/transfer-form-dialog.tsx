'use client';

import { useEffect, useMemo, useState } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { useTranslations } from 'next-intl';
import { useForm, useWatch } from 'react-hook-form';
import { toast } from 'sonner';

import {
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@repo/ui/components';
import { createTransfer } from '@/app/(protected)/accounts/account-actions';
import {
  buildTransferFormSchema,
  type TransferFormValues,
} from '@/app/(protected)/accounts/transfer-form-schema';
import { DatePickerInput } from '@/components/date-picker-input';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/form';
import { FormCombobox } from '@/components/form-combobox';
import { LocaleAmountInput } from '@/components/locale-amount-input';
import { StyledHint } from '@/components/styled-hint';
import type { Account } from '@/lib/api/accounts';
import { todayInTimezone } from '@/lib/utils/dates';

interface TransferFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  accounts: Account[];
  // Pre-selected source, when opened from a specific account's row.
  defaultFromAccountId?: number;
  timeZone?: string;
  onSuccess: () => void;
}

export function TransferFormDialog({
  open,
  onOpenChange,
  accounts,
  defaultFromAccountId,
  timeZone,
  onSuccess,
}: TransferFormDialogProps) {
  const t = useTranslations('accounts.transfers');
  const tForm = useTranslations('accounts.form');
  const tCommon = useTranslations('common');

  const schema = useMemo(() => buildTransferFormSchema(tCommon('form.errors.required')), [tCommon]);

  const form = useForm<TransferFormValues>({
    resolver: zodResolver(schema),
    defaultValues: { date: '', fromAmount: '', toAmount: '', notes: '' },
  });

  const [submitError, setSubmitError] = useState<string | null>(null);

  const fromAccountId = useWatch({ control: form.control, name: 'fromAccountId' });
  const toAccountId = useWatch({ control: form.control, name: 'toAccountId' });
  const fromAmount = useWatch({ control: form.control, name: 'fromAmount' });
  const toAmount = useWatch({ control: form.control, name: 'toAmount' });

  const today = todayInTimezone(timeZone);
  // Archiving is a UI filter, so an archived account is not offered as a destination for new money —
  // matching AccountField. Existing transfers that reference one still count in its balance.
  const selectable = useMemo(() => accounts.filter((a) => a.isActive), [accounts]);
  const source = selectable.find((a) => a.id === fromAccountId);
  const destination = selectable.find((a) => a.id === toAccountId);
  /*
   * The credited amount is asked for only when the two accounts differ in currency, because that is
   * the only case where it carries information: the rate the user actually got, which no stored rate
   * can reconstruct. Within one currency it must equal the debited amount, so asking would invite a
   * value the API would reject.
   */
  const crossCurrency = !!source && !!destination && source.currency !== destination.currency;

  useEffect(() => {
    if (open) {
      form.reset({
        fromAccountId: defaultFromAccountId,
        toAccountId: undefined,
        date: today,
        fromAmount: '',
        toAmount: '',
        notes: '',
      });
      setSubmitError(null);
    }
    // `today` changes identity every render but only matters at open.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, form, defaultFromAccountId]);

  // Drop a server-side rejection as soon as any field that could have caused it moves.
  useEffect(() => {
    setSubmitError(null);
  }, [fromAccountId, toAccountId, fromAmount, toAmount]);

  // Leaving one currency clears a credited amount that no longer applies, so a stale figure can't be
  // submitted against a pair that now mirrors instead.
  useEffect(() => {
    if (!crossCurrency) form.setValue('toAmount', '');
  }, [crossCurrency, form]);

  const accountOptions = useMemo(
    () =>
      selectable.map((a) => ({
        value: String(a.id),
        label: `${a.name} · ${a.currency}`,
      })),
    [selectable],
  );

  async function onSubmit(values: TransferFormValues) {
    setSubmitError(null);
    const result = await createTransfer(values);
    if (!result.ok) {
      setSubmitError(result.error || t('form.saveError'));
      return;
    }
    toast.success(t('form.success'));
    onSuccess();
    onOpenChange(false);
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('form.title')}</DialogTitle>
          {/* The semantic description (not a bare <p>) so Radix wires aria-describedby. It carries the
              one thing users mis-model: a transfer is between YOUR OWN accounts. */}
          <DialogDescription className="text-paragraph-sm">
            {t('form.description')}
          </DialogDescription>
          {submitError && <StyledHint variant="warning">{submitError}</StyledHint>}
        </DialogHeader>

        <Form {...form}>
          <form
            id="transfer-form"
            className="flex flex-col min-w-0 gap-y-4"
            onSubmit={form.handleSubmit(onSubmit)}
            noValidate
          >
            <FormField
              control={form.control}
              name="fromAccountId"
              render={({ field }) => (
                <FormItem required>
                  <FormLabel>{t('form.fromAccount.label')}</FormLabel>
                  <FormControl>
                    <FormCombobox
                      value={field.value ? String(field.value) : ''}
                      onValueChange={(value) => field.onChange(Number(value))}
                      options={accountOptions.filter((o) => Number(o.value) !== toAccountId)}
                      placeholder={t('form.fromAccount.placeholder')}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="toAccountId"
              render={({ field }) => (
                <FormItem required>
                  <FormLabel>{t('form.toAccount.label')}</FormLabel>
                  <FormControl>
                    <FormCombobox
                      value={field.value ? String(field.value) : ''}
                      onValueChange={(value) => field.onChange(Number(value))}
                      // The source is excluded rather than shown-and-rejected: a transfer to the same
                      // account moves nothing and the API refuses it.
                      options={accountOptions.filter((o) => Number(o.value) !== fromAccountId)}
                      placeholder={t('form.toAccount.placeholder')}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

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
                      maxDate={today}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="fromAmount"
              render={({ field }) => (
                <FormItem required>
                  <FormLabel>
                    {crossCurrency && source
                      ? t('form.fromAmount.labelWithCurrency', { currency: source.currency })
                      : t('form.fromAmount.label')}
                  </FormLabel>
                  <FormControl>
                    <LocaleAmountInput
                      {...field}
                      currency={source?.currency}
                      placeholder={t('form.fromAmount.placeholder')}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            {crossCurrency && destination && (
              <FormField
                control={form.control}
                name="toAmount"
                render={({ field }) => (
                  <FormItem required>
                    <FormLabel>
                      {t('form.toAmount.labelWithCurrency', { currency: destination.currency })}
                    </FormLabel>
                    <FormControl>
                      <LocaleAmountInput
                        {...field}
                        currency={destination.currency}
                        placeholder={t('form.toAmount.placeholder')}
                      />
                    </FormControl>
                    <span className="text-paragraph-xs text-muted-foreground">
                      {t('form.toAmount.hint')}
                    </span>
                    <FormMessage />
                  </FormItem>
                )}
              />
            )}
          </form>
        </Form>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {tForm('cancel')}
          </Button>
          <Button blue type="submit" form="transfer-form" disabled={form.formState.isSubmitting}>
            {form.formState.isSubmitting ? t('form.saveLoading') : t('form.saveLabel')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
