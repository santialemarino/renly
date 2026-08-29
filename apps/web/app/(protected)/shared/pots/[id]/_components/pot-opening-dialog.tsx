'use client';

import { useMemo } from 'react';
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
import { PotShareRows } from '@/app/(protected)/shared/_components/pot-share-rows';
import { recordPotOpening } from '@/app/(protected)/shared/pot-actions';
import {
  buildPotOpeningFormSchema,
  type PotOpeningFormValues,
} from '@/app/(protected)/shared/pot-form-schema';
import { DatePickerInput } from '@/components/date-picker-input';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/form';
import { LocaleAmountInput } from '@/components/locale-amount-input';
import type { Group } from '@/lib/api/groups';
import type { Pot } from '@/lib/api/pots';
import { POT_PERCENTAGE_TOTAL } from '@/lib/constants/pots';
import { useEntityFormDialog } from '@/lib/hooks/use-entity-form-dialog';
import { todayInTimezone } from '@/lib/utils/dates';

interface PotOpeningDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  pot: Pot;
  group: Group;
  timeZone?: string;
  onSuccess: () => void;
}

/*
 * The opening baseline: what the pot was worth on a date, and each owner's percentage of it.
 *
 * This IS the division every later percentage derives from — the pot's equivalent of an account's
 * opening balance and date — so there is exactly one of it, and nothing before its date is in scope.
 *
 * Two things it deliberately does NOT do. It takes percentages, never units (U2: percentages in,
 * percentages out). And it does not rescale what was typed: the total is shown live and the form
 * refuses at anything but 100, because quietly turning a 90/5 split into 94.7/5.3 is worse than
 * refusing it — which is the API's position too.
 */
export function PotOpeningDialog({
  open,
  onOpenChange,
  pot,
  group,
  timeZone,
  onSuccess,
}: PotOpeningDialogProps) {
  const t = useTranslations('shared');
  const tCommon = useTranslations('common');

  const seats = useMemo(() => group.members.filter((m) => m.isActive), [group.members]);
  const today = todayInTimezone(timeZone);

  const schema = useMemo(
    () =>
      buildPotOpeningFormSchema({
        requiredMsg: tCommon('form.errors.required'),
        positiveMsg: t('pots.form.mustBePositive'),
        totalMsg: t('pots.opening.totalError', { total: POT_PERCENTAGE_TOTAL }),
      }),
    [t, tCommon],
  );

  const form = useForm<PotOpeningFormValues>({
    resolver: zodResolver(schema),
    defaultValues: { date: today, value: '', shares: [], notes: '' },
  });

  const { submitWithLifecycle } = useEntityFormDialog({
    open,
    onOpenChange,
    form,
    // Keyed on the pot so reopening after a roster change re-seeds the rows; the pot itself never
    // changes while the dialog is open.
    entity: pot,
    toValues: () => ({
      date: today,
      value: '',
      shares: seats.map((seat) => ({ memberId: seat.id, percentage: '' })),
      notes: '',
    }),
    onSuccess,
  });

  async function onSubmit(values: PotOpeningFormValues) {
    await submitWithLifecycle(
      () => recordPotOpening(pot.id, values),
      t('pots.opening.success'),
      t('pots.opening.error'),
    );
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('pots.opening.title')}</DialogTitle>
        </DialogHeader>
        <DialogDescription>{t('pots.opening.description')}</DialogDescription>

        <Form {...form}>
          <form
            id="pot-opening-form"
            className="flex flex-col min-w-0 gap-y-4"
            onSubmit={form.handleSubmit(onSubmit)}
            noValidate
          >
            <div className="flex min-w-0 items-start gap-x-3">
              <FormField
                control={form.control}
                name="date"
                render={({ field }) => (
                  <FormItem required className="flex-1 min-w-0">
                    <FormLabel>{t('pots.opening.date.label')}</FormLabel>
                    <FormControl>
                      <DatePickerInput
                        value={field.value}
                        onChange={field.onChange}
                        placeholder={t('pots.opening.date.placeholder')}
                        maxDate={today}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="value"
                render={({ field }) => (
                  <FormItem required className="flex-1 min-w-0">
                    <FormLabel>{t('pots.opening.value.label')}</FormLabel>
                    <FormControl>
                      <LocaleAmountInput
                        {...field}
                        currency={pot.baseCurrency}
                        placeholder={t('pots.opening.value.placeholder')}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            {/*
             * Shared with the guided flow's own share step, so the two cannot state the rule
             * differently. The error shows after a submit attempt here, like any other field error.
             */}
            <PotShareRows form={form} seats={seats} showTotalError={form.formState.isSubmitted} />

            <FormField
              control={form.control}
              name="notes"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>{t('pots.notes.label')}</FormLabel>
                  <FormControl>
                    <Input {...field} placeholder={t('pots.notes.placeholder')} />
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
          <Button blue type="submit" form="pot-opening-form" disabled={form.formState.isSubmitting}>
            {form.formState.isSubmitting ? t('form.cta.loading') : t('pots.opening.cta')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
