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
import { recordPotReagreement } from '@/app/(protected)/shared/pot-actions';
import {
  buildPotReagreementFormSchema,
  type PotReagreementFormValues,
} from '@/app/(protected)/shared/pot-form-schema';
import { DatePickerInput } from '@/components/date-picker-input';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/form';
import { FormCombobox } from '@/components/form-combobox';
import { LocaleAmountInput } from '@/components/locale-amount-input';
import type { Group } from '@/lib/api/groups';
import type { Pot } from '@/lib/api/pots';
import { POT_PERCENTAGE_TOTAL } from '@/lib/constants/pots';
import { useEntityFormDialog } from '@/lib/hooks/use-entity-form-dialog';
import { useFormatters } from '@/lib/i18n/formatters';
import { todayInTimezone } from '@/lib/utils/dates';

interface PotReagreementDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  pot: Pot;
  group: Group;
  timeZone?: string;
  onSuccess: () => void;
}

/*
 * Changing the split: a share moving from one member to another with no money at all.
 *
 * Deliberately a different event from a contribution, and the distinction is the point. A contribution
 * is an investment — the mover's own money buys units and nobody else loses value. A re-agreement is a
 * gift or a settlement — one person's share falls so another's rises, and their VALUE moves with it.
 * Conflating them misstates what happened.
 *
 * Taken as a percentage of the whole pot, because percentages go in and percentages come out. The
 * givers are only the members who actually hold a share; the receiver can be any active seat, since
 * someone can be given one from nothing.
 */
export function PotReagreementDialog({
  open,
  onOpenChange,
  pot,
  group,
  timeZone,
  onSuccess,
}: PotReagreementDialogProps) {
  const fmt = useFormatters();
  const t = useTranslations('shared');
  const tCommon = useTranslations('common');

  const seats = useMemo(() => group.members.filter((m) => m.isActive), [group.members]);
  const today = todayInTimezone(timeZone);

  const schema = useMemo(
    () =>
      buildPotReagreementFormSchema({
        requiredMsg: tCommon('form.errors.required'),
        positiveMsg: t('pots.form.mustBePositive'),
        rangeMsg: t('pots.reagreement.rangeError', { total: POT_PERCENTAGE_TOTAL }),
        sameMemberMsg: t('pots.reagreement.sameMemberError'),
      }),
    [t, tCommon],
  );

  const form = useForm<PotReagreementFormValues>({
    resolver: zodResolver(schema),
    defaultValues: { date: today, fromMemberId: '', toMemberId: '', percentage: '', notes: '' },
  });

  const { submitWithLifecycle } = useEntityFormDialog({
    open,
    onOpenChange,
    form,
    entity: pot,
    toValues: () => ({
      date: today,
      fromMemberId: '',
      toMemberId: '',
      percentage: '',
      notes: '',
    }),
    onSuccess,
  });

  /*
   * Only holders can give. Their current share is in the label because it is the ceiling the amount is
   * measured against — the API refuses more than they hold, and seeing it beside the picker is what
   * keeps that refusal from being a surprise.
   */
  const giverOptions = pot.shares.map((share) => ({
    value: String(share.memberId),
    label: `${share.displayName} · ${fmt.sharePct(Number(share.percentage))}%`,
  }));
  const receiverOptions = seats.map((seat) => ({
    value: String(seat.id),
    label: seat.displayName,
  }));

  async function onSubmit(values: PotReagreementFormValues) {
    await submitWithLifecycle(
      () => recordPotReagreement(pot.id, values),
      t('pots.reagreement.success'),
      t('pots.reagreement.error'),
    );
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('pots.reagreement.title')}</DialogTitle>
        </DialogHeader>
        <DialogDescription>{t('pots.reagreement.description')}</DialogDescription>

        <Form {...form}>
          <form
            id="pot-reagreement-form"
            className="flex flex-col min-w-0 gap-y-4"
            onSubmit={form.handleSubmit(onSubmit)}
            noValidate
          >
            <FormField
              control={form.control}
              name="date"
              render={({ field }) => (
                <FormItem required>
                  <FormLabel>{t('pots.reagreement.date.label')}</FormLabel>
                  <FormControl>
                    <DatePickerInput
                      value={field.value}
                      onChange={field.onChange}
                      placeholder={t('pots.reagreement.date.placeholder')}
                      maxDate={today}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="fromMemberId"
              render={({ field }) => (
                <FormItem required>
                  <FormLabel>{t('pots.reagreement.from.label')}</FormLabel>
                  <FormControl>
                    <FormCombobox
                      value={field.value ?? ''}
                      onValueChange={field.onChange}
                      options={giverOptions}
                      placeholder={t('pots.reagreement.from.placeholder')}
                      className="w-full"
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="toMemberId"
              render={({ field }) => (
                <FormItem required>
                  <FormLabel>{t('pots.reagreement.to.label')}</FormLabel>
                  <FormControl>
                    <FormCombobox
                      value={field.value ?? ''}
                      onValueChange={field.onChange}
                      options={receiverOptions}
                      placeholder={t('pots.reagreement.to.placeholder')}
                      className="w-full"
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="percentage"
              render={({ field }) => (
                <FormItem required>
                  <FormLabel>{t('pots.reagreement.percentage.label')}</FormLabel>
                  <FormControl>
                    <LocaleAmountInput
                      {...field}
                      className="w-40"
                      placeholder={t('pots.reagreement.percentage.placeholder')}
                    />
                  </FormControl>
                  <p className="text-paragraph-xs text-muted-foreground">
                    {t('pots.reagreement.percentage.hint')}
                  </p>
                  <FormMessage />
                </FormItem>
              )}
            />

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
          <Button
            blue
            type="submit"
            form="pot-reagreement-form"
            disabled={form.formState.isSubmitting}
          >
            {form.formState.isSubmitting ? t('form.cta.loading') : t('pots.reagreement.cta')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
