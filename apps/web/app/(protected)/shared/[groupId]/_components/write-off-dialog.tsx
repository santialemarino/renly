'use client';

import { useMemo, useRef } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { useTranslations } from 'next-intl';
import { useForm } from 'react-hook-form';

import {
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Input,
} from '@repo/ui/components';
import { recordWriteOff } from '@/app/(protected)/shared/settlement-actions';
import {
  buildWriteOffFormSchema,
  type WriteOffFormValues,
} from '@/app/(protected)/shared/settlement-form-schema';
import { DatePickerInput } from '@/components/date-picker-input';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/form';
import { LocaleAmountInput } from '@/components/locale-amount-input';
import { StyledHint } from '@/components/styled-hint';
import type { GroupSettleSuggestion } from '@/lib/api/group-settlements';
import { useEntityFormDialog } from '@/lib/hooks/use-entity-form-dialog';
import { useFormatters } from '@/lib/i18n/formatters';
import { todayInTimezone } from '@/lib/utils/dates';

interface WriteOffDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  groupId: number;
  // The suggested payment being given up on. May go null while the close animation plays — the last
  // non-null value is retained so the body does not blank out mid-exit.
  suggestion?: GroupSettleSuggestion;
  currency: string;
  timeZone?: string;
  onSuccess: () => void;
}

/*
 * Giving up on a debt.
 *
 * It clears the same bucket a payment would and moves no money at all, which is why it names no
 * account and carries no cash leg — and why removing the receivable is what drops net worth by the
 * loss, with no expense booked. A balance-level write-off spans many expenses and has no item,
 * category or date of its own to inherit; inventing all three would put spending in a month it never
 * happened in.
 *
 * Only ever opened by the creditor — the person the payment would have gone to — because giving up a
 * claim is theirs to give up. The API refuses anyone else outright.
 *
 * The amount stays editable: forgiving part of what someone owes is a real thing to do, and what is
 * left simply stays outstanding.
 */
export function WriteOffDialog({
  open,
  onOpenChange,
  groupId,
  suggestion,
  currency,
  timeZone,
  onSuccess,
}: WriteOffDialogProps) {
  const fmt = useFormatters();
  const t = useTranslations('shared');
  const tCommon = useTranslations('common');

  const lastSuggestion = useRef(suggestion);
  if (suggestion) lastSuggestion.current = suggestion;
  const lastCurrency = useRef(currency);
  if (currency) lastCurrency.current = currency;
  const shown = suggestion ?? lastSuggestion.current;
  const shownCurrency = currency || lastCurrency.current;

  const today = todayInTimezone(timeZone);

  // The balance this is capped at. Zero only while the dialog is closing with nothing retained, which
  // the body never renders — every real open carries a suggestion, and a suggestion is a debt.
  const outstanding = shown?.amount ?? '0';

  const schema = useMemo(
    () =>
      buildWriteOffFormSchema({
        requiredMsg: tCommon('form.errors.required'),
        positiveMsg: t('pots.form.mustBePositive'),
        outstanding,
        exceedsMsg: t('settlements.writeOff.exceeds', {
          amount: fmt.amount(outstanding, shownCurrency),
          currency: shownCurrency,
        }),
      }),
    [fmt, outstanding, shownCurrency, t, tCommon],
  );

  const toValues = (entity: GroupSettleSuggestion | undefined): WriteOffFormValues => ({
    date: today,
    amount: entity?.amount ?? '',
    notes: '',
  });

  const form = useForm<WriteOffFormValues>({
    resolver: zodResolver(schema),
    defaultValues: toValues(suggestion),
  });

  const { submitWithLifecycle } = useEntityFormDialog({
    open,
    onOpenChange,
    form,
    entity: suggestion,
    toValues,
    onSuccess,
  });

  async function onSubmit(values: WriteOffFormValues) {
    if (!shown) return;
    await submitWithLifecycle(
      () => recordWriteOff(groupId, shown.fromMemberId, shown.toMemberId, shownCurrency, values),
      t('settlements.writeOff.success'),
      t('settlements.writeOff.error'),
    );
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('settlements.writeOff.title')}</DialogTitle>
        </DialogHeader>
        <DialogDescription>
          {shown
            ? t('settlements.writeOff.description', {
                from: shown.fromDisplayName,
                amount: fmt.amount(shown.amount, shownCurrency),
                currency: shownCurrency,
              })
            : ''}
        </DialogDescription>

        <Form {...form}>
          <form
            id="write-off-form"
            className="flex flex-col min-w-0 gap-y-4"
            onSubmit={form.handleSubmit(onSubmit)}
            noValidate
          >
            <StyledHint variant="warning" surface>
              {t('settlements.writeOff.warning')}
            </StyledHint>

            <div className="flex min-w-0 items-start gap-x-3">
              <FormField
                control={form.control}
                name="amount"
                render={({ field }) => (
                  <FormItem required className="flex-1 min-w-0">
                    <FormLabel>
                      {t('settlements.writeOff.amount.label', { currency: shownCurrency })}
                    </FormLabel>
                    <FormControl>
                      <LocaleAmountInput
                        {...field}
                        currency={shownCurrency}
                        placeholder={t('settlements.writeOff.amount.placeholder')}
                      />
                    </FormControl>
                    {/*
                     * Says the rule before the field can break it, the way the settle dialog's own
                     * amount hint does — and the rule is the OPPOSITE there, so leaving this blank
                     * would let somebody carry the wrong expectation across two adjacent dialogs.
                     */}
                    <p className="text-paragraph-xs text-muted-foreground">
                      {t('settlements.writeOff.amount.hint')}
                    </p>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="date"
                render={({ field }) => (
                  <FormItem required className="flex-1 min-w-0">
                    <FormLabel>{t('settlements.writeOff.date.label')}</FormLabel>
                    <FormControl>
                      <DatePickerInput
                        value={field.value}
                        onChange={field.onChange}
                        placeholder={t('settlements.writeOff.date.placeholder')}
                        maxDate={today}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            <FormField
              control={form.control}
              name="notes"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>{t('settlements.form.notes.label')}</FormLabel>
                  <FormControl>
                    <Input {...field} placeholder={t('settlements.writeOff.notes.placeholder')} />
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
            type="submit"
            form="write-off-form"
            variant="destructive"
            disabled={form.formState.isSubmitting}
          >
            {form.formState.isSubmitting ? t('form.cta.loading') : t('settlements.writeOff.cta')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
