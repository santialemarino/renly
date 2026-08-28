'use client';

import { useMemo } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { useTranslations } from 'next-intl';
import { useForm, useWatch } from 'react-hook-form';

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
import { recordPotMovement } from '@/app/(protected)/shared/pot-actions';
import {
  buildPotMovementFormSchema,
  type PotMovementFormValues,
} from '@/app/(protected)/shared/pot-form-schema';
import { canNamePrivateLeg, potLegAccounts } from '@/app/(protected)/shared/pot-rules';
import { DatePickerInput } from '@/components/date-picker-input';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/form';
import { FormCombobox } from '@/components/form-combobox';
import { LocaleAmountInput } from '@/components/locale-amount-input';
import type { Account } from '@/lib/api/accounts';
import type { Group } from '@/lib/api/groups';
import type { Pot, PotHoldings } from '@/lib/api/pots';
import { POT_MOVEMENT_TYPES } from '@/lib/constants/pots';
import { useEntityFormDialog } from '@/lib/hooks/use-entity-form-dialog';
import { todayInTimezone } from '@/lib/utils/dates';

interface PotMovementDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  pot: Pot;
  group: Group;
  holdings: PotHoldings;
  privateAccounts: Account[];
  timeZone?: string;
  onSuccess: () => void;
}

/*
 * A contribution or a withdrawal: money crossing the scope boundary, priced at the pot's unit price on
 * the date. This is the one place value enters or leaves a pot, and it is a distinct mechanic from a
 * transfer for a reason — a transfer is net-worth-neutral by construction, and moving joint money into
 * a personal account is emphatically not neutral for the other owners.
 *
 * The form asks "which of your accounts" and "which of the pot's", because that is what the person
 * knows; the action maps them onto the API's directional `from`/`to` legs. Both are optional: money can
 * arrive from outside Renly, or land in an investment rather than a tracked account.
 *
 * The private leg is offered only when the movement is recorded for the viewer's OWN seat, because the
 * API requires that leg to be the caller's own account whoever the movement is for — recording
 * someone else's contribution can only be a note about money that moved elsewhere.
 */
export function PotMovementDialog({
  open,
  onOpenChange,
  pot,
  group,
  holdings,
  privateAccounts,
  timeZone,
  onSuccess,
}: PotMovementDialogProps) {
  const t = useTranslations('shared');
  const tCommon = useTranslations('common');

  const seats = useMemo(() => group.members.filter((m) => m.isActive), [group.members]);
  const mySeatId = useMemo(() => seats.find((m) => m.isSelf)?.id ?? null, [seats]);
  const today = todayInTimezone(timeZone);

  const schema = useMemo(
    () =>
      buildPotMovementFormSchema({
        baseCurrency: pot.baseCurrency,
        requiredMsg: tCommon('form.errors.required'),
        positiveMsg: t('pots.form.mustBePositive'),
      }),
    [pot.baseCurrency, t, tCommon],
  );

  const form = useForm<PotMovementFormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      type: 'contribution',
      date: today,
      memberId: mySeatId === null ? '' : String(mySeatId),
      amount: '',
      amountCurrency: pot.baseCurrency,
      baseAmount: '',
      privateAccountId: '',
      potAccountId: '',
      notes: '',
    },
  });

  const { submitWithLifecycle } = useEntityFormDialog({
    open,
    onOpenChange,
    form,
    entity: pot,
    toValues: () => ({
      type: 'contribution' as const,
      date: today,
      memberId: mySeatId === null ? '' : String(mySeatId),
      amount: '',
      amountCurrency: pot.baseCurrency,
      baseAmount: '',
      privateAccountId: '',
      potAccountId: '',
      notes: '',
    }),
    onSuccess,
  });

  const watchedType = useWatch({ control: form.control, name: 'type' });
  const watchedMemberId = useWatch({ control: form.control, name: 'memberId' });
  const watchedCurrency = useWatch({ control: form.control, name: 'amountCurrency' });

  const forOwnSeat = canNamePrivateLeg(Number(watchedMemberId), mySeatId);
  const crossCurrency = watchedCurrency !== pot.baseCurrency;
  const isContribution = watchedType === 'contribution';

  /*
   * The eligible pot-side accounts: ones this pot holds, active, in its base currency. All three are
   * the API's rules — an archived one is excluded from the pot's value, so routing money through it
   * would move the account and leave the NAV where it was.
   */
  const potAccounts = useMemo(
    () => potLegAccounts(holdings, pot.baseCurrency),
    [holdings, pot.baseCurrency],
  );

  // Active private accounts only, matching what a transfer offers: an archived one is not somewhere to
  // route new money even though the API would take it.
  const eligiblePrivate = useMemo(
    () => privateAccounts.filter((a) => a.isActive),
    [privateAccounts],
  );

  const typeOptions = POT_MOVEMENT_TYPES.map((type) => ({
    value: type,
    label: t(`pots.eventTypes.${type}`),
  }));
  const seatOptions = seats.map((seat) => ({ value: String(seat.id), label: seat.displayName }));
  const privateOptions = eligiblePrivate.map((account) => ({
    value: String(account.id),
    label: `${account.name} · ${account.currency}`,
  }));
  const potAccountOptions = potAccounts.map((account) => ({
    value: String(account.id),
    label: account.name,
  }));

  /*
   * `amount` is in the private account's currency, so selecting one settles it — merged constraint (a),
   * "entry currency = account currency", which the API now enforces on this leg too. With no private
   * account named there is nothing to derive it from, so the field stays the pot's base currency and
   * the movement is single-currency.
   */
  function onPrivateAccountChange(value: string) {
    form.setValue('privateAccountId', value);
    const account = eligiblePrivate.find((a) => String(a.id) === value);
    const currency = account?.currency ?? pot.baseCurrency;
    form.setValue('amountCurrency', currency);
    if (currency === pot.baseCurrency) form.setValue('baseAmount', '');
  }

  async function onSubmit(values: PotMovementFormValues) {
    await submitWithLifecycle(
      () => recordPotMovement(pot.id, pot.baseCurrency, values),
      t('pots.movement.success'),
      t('pots.movement.error'),
    );
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('pots.movement.title')}</DialogTitle>
        </DialogHeader>
        <DialogDescription>{t('pots.movement.description')}</DialogDescription>

        <Form {...form}>
          <form
            id="pot-movement-form"
            className="flex flex-col min-w-0 gap-y-4"
            onSubmit={form.handleSubmit(onSubmit)}
            noValidate
          >
            <div className="flex min-w-0 items-start gap-x-3">
              <FormField
                control={form.control}
                name="type"
                render={({ field }) => (
                  <FormItem required className="flex-1 min-w-0">
                    <FormLabel>{t('pots.movement.type.label')}</FormLabel>
                    <FormControl>
                      <FormCombobox
                        value={field.value ?? ''}
                        onValueChange={field.onChange}
                        options={typeOptions}
                        placeholder={t('pots.movement.type.placeholder')}
                        className="w-full"
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
                  <FormItem required className="flex-1 min-w-0">
                    <FormLabel>{t('pots.movement.date.label')}</FormLabel>
                    <FormControl>
                      <DatePickerInput
                        value={field.value}
                        onChange={field.onChange}
                        placeholder={t('pots.movement.date.placeholder')}
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
              name="memberId"
              render={({ field }) => (
                <FormItem required>
                  <FormLabel>{t('pots.movement.member.label')}</FormLabel>
                  <FormControl>
                    <FormCombobox
                      value={field.value ?? ''}
                      onValueChange={(value) => {
                        field.onChange(value);
                        // A private leg only makes sense for your own seat, so clear it when the
                        // movement is recorded for someone else rather than sending an id the API
                        // will refuse as not yours.
                        if (!canNamePrivateLeg(Number(value), mySeatId)) {
                          form.setValue('privateAccountId', '');
                          form.setValue('amountCurrency', pot.baseCurrency);
                          form.setValue('baseAmount', '');
                        }
                      }}
                      options={seatOptions}
                      placeholder={t('pots.movement.member.placeholder')}
                      className="w-full"
                    />
                  </FormControl>
                  <p className="text-paragraph-xs text-muted-foreground">
                    {t('pots.movement.member.hint')}
                  </p>
                  <FormMessage />
                </FormItem>
              )}
            />

            {forOwnSeat && (
              <FormField
                control={form.control}
                name="privateAccountId"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>
                      {isContribution
                        ? t('pots.movement.privateLeg.labelOut')
                        : t('pots.movement.privateLeg.labelIn')}
                    </FormLabel>
                    <FormControl>
                      <FormCombobox
                        value={field.value ?? ''}
                        onValueChange={onPrivateAccountChange}
                        options={privateOptions}
                        placeholder={t('pots.movement.privateLeg.placeholder')}
                        emptyText={t('pots.movement.privateLeg.empty')}
                        className="w-full"
                      />
                    </FormControl>
                    <p className="text-paragraph-xs text-muted-foreground">
                      {t('pots.movement.privateLeg.hint')}
                    </p>
                    <FormMessage />
                  </FormItem>
                )}
              />
            )}

            <FormField
              control={form.control}
              name="potAccountId"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>
                    {isContribution
                      ? t('pots.movement.potLeg.labelIn')
                      : t('pots.movement.potLeg.labelOut')}
                  </FormLabel>
                  <FormControl>
                    <FormCombobox
                      value={field.value ?? ''}
                      onValueChange={field.onChange}
                      options={potAccountOptions}
                      placeholder={t('pots.movement.potLeg.placeholder')}
                      emptyText={t('pots.movement.potLeg.empty', {
                        currency: pot.baseCurrency,
                      })}
                      className="w-full"
                    />
                  </FormControl>
                  <p className="text-paragraph-xs text-muted-foreground">
                    {t('pots.movement.potLeg.hint', { currency: pot.baseCurrency })}
                  </p>
                  <FormMessage />
                </FormItem>
              )}
            />

            <div className="flex min-w-0 items-start gap-x-3">
              <FormField
                control={form.control}
                name="amount"
                render={({ field }) => (
                  <FormItem required className="flex-1 min-w-0">
                    <FormLabel>
                      {t('pots.movement.amount.label', { currency: watchedCurrency })}
                    </FormLabel>
                    <FormControl>
                      <LocaleAmountInput
                        {...field}
                        currency={watchedCurrency}
                        placeholder={t('pots.movement.amount.placeholder')}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              {/*
               * Revealed only across currencies, and required then: the two legs are denominated
               * differently and no rate is ever stored, so the credited figure has to be stated. Within
               * one currency it IS the amount, and the API stores it that way.
               */}
              {crossCurrency && (
                <FormField
                  control={form.control}
                  name="baseAmount"
                  render={({ field }) => (
                    <FormItem required className="flex-1 min-w-0">
                      <FormLabel>
                        {t('pots.movement.baseAmount.label', { currency: pot.baseCurrency })}
                      </FormLabel>
                      <FormControl>
                        <LocaleAmountInput
                          {...field}
                          currency={pot.baseCurrency}
                          placeholder={t('pots.movement.baseAmount.placeholder')}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              )}
            </div>

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
            form="pot-movement-form"
            disabled={form.formState.isSubmitting}
          >
            {form.formState.isSubmitting ? t('form.cta.loading') : t('pots.movement.cta')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
