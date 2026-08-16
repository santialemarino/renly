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
  // The card's optional default funding account ("débito automático"), used only as the initial value
  // of "Paid from". It never creates a settlement on its own: a real auto-debit can fail, and Renly
  // must not invent a payment that did not happen.
  defaultAccountId: number | null;
  onSuccess: () => void;
}

export function SettlementFormDialog({
  open,
  onOpenChange,
  cardId,
  bucketCurrencies,
  accounts,
  defaultAccountId,
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

  /*
   * Only pre-fill a default the picker would actually offer. Seeding it unconditionally moved real
   * money invisibly in two cases: an ARCHIVED default would arrive pre-selected on a brand-new
   * settlement (the spare-an-archived-link rule exists for entries being EDITED, not for creating one),
   * and if the accounts fetch failed the page's `.catch(() => [])` left AccountField with nothing to
   * render — so the field vanished while form state still held the id and the save still posted it.
   */
  const prefilledAccountId =
    accounts?.some((a) => a.id === defaultAccountId && a.isActive) === true
      ? defaultAccountId
      : null;

  const form = useForm<SettlementFormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      date: '',
      amount: '',
      currency: defaultCurrency,
      accountId: prefilledAccountId,
      notes: '',
    },
  });

  const watchedCurrency = useWatch({ control: form.control, name: 'currency' });

  // Reset form when dialog opens — re-anchor currency to the card's primary bucket, and pre-fill the
  // funding account from the card's default. The default is restricted to the card's own currency, so
  // it matches the primary bucket the form opens on; switching to another bucket's currency clears it
  // through AccountField's own mismatch effect rather than submitting a link the API would refuse.
  useEffect(() => {
    if (open) {
      form.reset({
        date: '',
        amount: '',
        currency: defaultCurrency,
        accountId: prefilledAccountId,
        notes: '',
      });
    }
  }, [open, form, defaultCurrency, prefilledAccountId]);

  async function onSubmit(values: SettlementFormValues) {
    try {
      const result = await createSettlement(cardId, values);
      // The action returns a refusal as DATA (the Server Action boundary strips a thrown error's
      // message), so its localized reason renders instead of the generic save error.
      if (!result.ok) {
        toast.error(result.conflictDetail || t('settlements.createError'));
        return;
      }
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

            <AccountField
              control={form.control}
              setValue={form.setValue}
              accounts={accounts ?? []}
              currency={watchedCurrency || undefined}
              label={t('settlements.form.account')}
              name="accountId"
            />

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
