'use client';

import { useEffect, useMemo } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { AnimatePresence, motion } from 'motion/react';
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
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/form';
import { FormCombobox } from '@/components/form-combobox';
import { LocaleAmountInput } from '@/components/locale-amount-input';
import type { Account } from '@/lib/api/accounts';
import { ANIMATION_DEFAULT } from '@/lib/constants/animations';
import { useFormatters } from '@/lib/i18n/formatters';
import { estimatedCardRate, impliedRate, rateDecimals } from '@/lib/utils/settlement-rate';

interface SettlementFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  cardId: number;
  // Primary currency first, then any other currencies with activity on this card.
  // Length 1 = single-bucket card (picker hidden). Length > 1 = multi-bucket (picker shown).
  bucketCurrencies: string[];
  /*
   * Accounts the payment can be drawn from. Deliberately NOT filtered to the bucket's currency: a card
   * bill can be settled from an account in any currency, and when the two differ the form asks for what
   * actually left that account. Omitted or empty hides the field entirely (cash-less users see no change).
   */
  accounts?: Account[];
  // The card's optional default funding account ("débito automático"), used only as the initial value
  // of "Paid from". It never creates a settlement on its own: a real auto-debit can fail, and Renly
  // must not invent a payment that did not happen.
  defaultAccountId: number | null;
  /*
   * The latest stored USD_ARS_OFICIAL rate and the date it is for, or null when none is stored. Feeds ONLY
   * the estimate shown beside the implied rate. It must be the oficial pair rather than the user's
   * dollar-rate preference — dólar tarjeta is built on oficial even for someone viewing MEP, so reading
   * the preference here would be a quiet correctness bug. The date is rendered with it rather than
   * dropped: a settlement is usually backdated (last month's statement) and the rate feed can be behind,
   * so an undated benchmark would contradict a perfectly correct entry.
   */
  oficialRate: number | null;
  oficialRateDate: string | null;
  onSuccess: () => void;
}

export function SettlementFormDialog({
  open,
  onOpenChange,
  cardId,
  bucketCurrencies,
  accounts,
  defaultAccountId,
  oficialRate,
  oficialRateDate,
  onSuccess,
}: SettlementFormDialogProps) {
  const fmt = useFormatters();
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
      accountAmount: '',
      notes: '',
    },
  });

  const watchedCurrency = useWatch({ control: form.control, name: 'currency' });
  const watchedAmount = useWatch({ control: form.control, name: 'amount' });
  const watchedAccountId = useWatch({ control: form.control, name: 'accountId' });
  const watchedAccountAmount = useWatch({ control: form.control, name: 'accountAmount' });

  // The chosen account, and whether settling this bucket from it converts. `crossCurrency` is what
  // reveals the second amount field and what makes it required — the API refuses either way.
  const selectedAccount = accounts?.find((a) => a.id === watchedAccountId);
  const crossCurrency =
    !!selectedAccount && !!watchedCurrency && selectedAccount.currency !== watchedCurrency;

  /*
   * The rate the two typed amounts imply, beside what today's dólar tarjeta suggests. A read-back, never
   * a prefill: the user's figure stays authoritative because the whole model rests on recording what
   * really left the account. The pair catches a 10× typo in either direction.
   */
  const typedRate = crossCurrency ? impliedRate(watchedAmount, watchedAccountAmount ?? '') : null;
  const estimate = crossCurrency
    ? estimatedCardRate(watchedCurrency, selectedAccount.currency, oficialRate)
    : null;

  // Reset form when dialog opens — re-anchor currency to the card's primary bucket, and pre-fill the
  // funding account from the card's default. The default may now be in ANY currency, so it survives the
  // reset even for a bucket it doesn't match: that combination is legal, and the form simply asks for the
  // second amount instead of clearing the link.
  useEffect(() => {
    if (open) {
      form.reset({
        date: '',
        amount: '',
        currency: defaultCurrency,
        accountId: prefilledAccountId,
        accountAmount: '',
        notes: '',
      });
    }
  }, [open, form, defaultCurrency, prefilledAccountId]);

  /*
   * Drop a typed cash amount whenever the currency it was denominated in changes — not merely when the
   * settlement stops crossing currencies. Keying this on `crossCurrency` alone left the figure in place
   * when the user switched between two DIFFERENT foreign accounts (peso → dollar), so the label and the
   * input's own currency flipped while the typed number stayed: 130,000 entered as pesos would submit as
   * US$130,000, and both amounts are legal for any differing pair so nothing downstream could catch it.
   * Keyed on the account's currency, every such switch clears the field and asks again.
   */
  const fundingCurrency = crossCurrency ? selectedAccount.currency : null;
  useEffect(() => {
    if (form.getValues('accountAmount')) form.setValue('accountAmount', '');
  }, [fundingCurrency, watchedCurrency, form]);

  async function onSubmit(values: SettlementFormValues) {
    /*
     * Required-ness depends on the chosen ACCOUNT's currency, which the zod builder never sees, so it is
     * checked here and surfaced on the field — same place and animation as any validation error, rather
     * than only as a toast after a round-trip.
     */
    if (crossCurrency && !values.accountAmount) {
      form.setError('accountAmount', { message: tCommon('form.errors.required') });
      return;
    }
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

            {/* No currency filter: any account may settle any bucket, because a cross-currency
                settlement records what left the account. buildAccountFieldOptions already treats an
                absent currency as "offer every active account", and shouldClearAccountLink no-ops
                without one, so the mismatch effect correctly stops firing here. */}
            <AccountField
              control={form.control}
              setValue={form.setValue}
              accounts={accounts ?? []}
              currency={undefined}
              label={t('settlements.form.account')}
              name="accountId"
            />

            {/* Height-reveal, like every sibling conditional field (see PaymentMethodFields): the
                negative margin cancels the form's gap-y-4 while collapsed so nothing jumps. */}
            <AnimatePresence initial={false}>
              {crossCurrency && (
                <motion.div
                  key="account-amount"
                  initial={{ opacity: 0, height: 0, overflow: 'hidden' }}
                  animate={{ opacity: 1, height: 'auto', overflow: 'visible' }}
                  exit={{ opacity: 0, height: 0, overflow: 'hidden' }}
                  transition={{ duration: ANIMATION_DEFAULT }}
                  style={{ marginTop: -16 }}
                >
                  <div className="pt-4">
                    <FormField
                      control={form.control}
                      name="accountAmount"
                      render={({ field }) => (
                        <FormItem required>
                          <FormLabel>
                            {t('settlements.form.accountAmount', {
                              currency: selectedAccount.currency,
                            })}
                          </FormLabel>
                          <FormControl>
                            <LocaleAmountInput
                              {...field}
                              value={field.value ?? ''}
                              currency={selectedAccount.currency}
                              placeholder={t('settlements.form.accountAmountPlaceholder')}
                            />
                          </FormControl>
                          {/* FormDescription, never a bare <p> — FormControl already points
                              aria-describedby at its id, so the read-back is announced. */}
                          <FormDescription className="text-paragraph-xs">
                            {t('settlements.form.accountAmountHint', {
                              bucket: watchedCurrency,
                              account: selectedAccount.currency,
                            })}
                            {typedRate !== null && (
                              <span className="block">
                                {t('settlements.form.impliedRate', {
                                  rate: fmt.value(typedRate, {
                                    maxDecimals: rateDecimals(typedRate),
                                  }),
                                  bucket: watchedCurrency,
                                  account: selectedAccount.currency,
                                })}
                                {/* Gated on the DATE as well as the value: a benchmark that can't say
                                    which day it is for would contradict a correct backdated entry with
                                    nothing on screen explaining why. */}
                                {estimate !== null &&
                                  oficialRateDate &&
                                  ` ${t('settlements.form.estimatedRate', {
                                    rate: fmt.value(estimate, {
                                      maxDecimals: rateDecimals(estimate),
                                    }),
                                    date: fmt.date(oficialRateDate),
                                  })}`}
                              </span>
                            )}
                          </FormDescription>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  </div>
                </motion.div>
              )}
            </AnimatePresence>

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
