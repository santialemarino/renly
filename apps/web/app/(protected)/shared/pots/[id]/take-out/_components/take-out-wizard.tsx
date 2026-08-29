'use client';

import { useMemo, useState, useTransition } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { zodResolver } from '@hookform/resolvers/zod';
import { useTranslations } from 'next-intl';
import { useForm } from 'react-hook-form';
import { toast } from 'sonner';

import { Button, Input } from '@repo/ui/components';
import {
  WizardConfirmRow,
  WizardPanel,
  WizardShell,
} from '@/app/(protected)/shared/_components/wizard-shell';
import { WizardSummary } from '@/app/(protected)/shared/_components/wizard-summary';
import { takePotShareOut } from '@/app/(protected)/shared/pot-actions';
import {
  buildPotTakeOutFormSchema,
  type PotTakeOutFormValues,
} from '@/app/(protected)/shared/pot-form-schema';
import {
  canNamePrivateLeg,
  canTakeShareOut,
  holderShare,
  isPriceable,
  potLabel,
  potLegAccounts,
  wholeExitOutcome,
} from '@/app/(protected)/shared/pot-rules';
import { DatePickerInput } from '@/components/date-picker-input';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/form';
import { FormCombobox } from '@/components/form-combobox';
import { LocaleAmountInput } from '@/components/locale-amount-input';
import { sharedPotPath, sharedTakeOutPath } from '@/config/routes';
import type { Account } from '@/lib/api/accounts';
import type { Group } from '@/lib/api/groups';
import type { Pot, PotHoldings } from '@/lib/api/pots';
import { useFormatters } from '@/lib/i18n/formatters';
import { todayInTimezone } from '@/lib/utils/dates';

type Stage = 'who' | 'where' | 'confirm' | 'done';

const STAGE_ORDER: Stage[] = ['who', 'where', 'confirm'];

interface TakeOutWizardProps {
  // Valued AS AT `asOfDate`, so every share figure here is the one the API will price the event at.
  pot: Pot;
  group: Group;
  holdings: PotHoldings;
  privateAccounts: Account[];
  asOfDate?: string;
  timeZone?: string;
}

/*
 * Taking a member's whole share out of the shared money.
 *
 * One write, at the end, so there is no partial state to recover from — unlike the sharing flow, which
 * has three. What this one has instead is a figure that depends on a date, and it is resolved on the
 * SERVER: the date is a URL param, the page re-reads the pot as at it, and the ledger replay and the
 * valuation move together. Pricing on the client would be a second copy of the unit maths, and the one
 * number it got wrong would be the one a person checks against the ownership table.
 *
 * It sends `whole_share`, which is why the flow exists at all. A withdrawal derives its units by
 * dividing money by the unit price, and over 224,200 plausible pots the share's own value landed on the
 * holder's exact balance 4.6% of the time: refused half of the rest, and leaving a residual the other
 * half — a residual that renders as a 0.00% owner worth 0.00, forever, because a replayed balance is
 * dropped only when it is exactly zero.
 *
 * Both account legs stay optional, for the same reason a plain movement's are: the money may have moved
 * somewhere Renly does not track. What is NOT optional is saying so — leaving them blank means the
 * shares change now while the pot's value waits for its next update, so the remaining shares read
 * higher than they are. The confirmation and the closing panel both state that when it applies.
 */
export function TakeOutWizard({
  pot,
  group,
  holdings,
  privateAccounts,
  asOfDate,
  timeZone,
}: TakeOutWizardProps) {
  const fmt = useFormatters();
  const t = useTranslations('shared');
  const tCommon = useTranslations('common');
  const router = useRouter();

  const [stage, setStage] = useState<Stage>('who');
  const [pending, setPending] = useState(false);
  /*
   * The date re-read and the post-write refresh are both navigations, and both are kept observable
   * rather than fire-and-forget. A Server Action issued while a navigation is in flight is CANCELLED
   * by it and its promise never settles — no result, no catch, no finally, just a button stuck on its
   * loading label for good — so the primary stays unavailable until the navigation lands. It is also
   * the honest behaviour on its own: mid-re-read, `pot` still holds the figures for the OTHER date,
   * and mid-refresh it still holds the split from BEFORE the write.
   */
  const [isNavigating, startNavigation] = useTransition();
  // Kept from before the write, because afterwards the seat holds no share to read a name from.
  const [outcome, setOutcome] = useState<{
    name: string;
    amount: string;
    movedValue: boolean;
  } | null>(null);

  const seats = useMemo(() => group.members.filter((m) => m.isActive), [group.members]);
  const mySeatId = useMemo(() => seats.find((m) => m.isSelf)?.id ?? null, [seats]);
  const today = todayInTimezone(timeZone);
  const label = potLabel(pot, t('pots.defaultLabel'));

  const priceable = canTakeShareOut(pot);
  // Whoever holds the largest share, unless the viewer holds one — the common case is your own.
  const defaultHolder = useMemo(
    () => pot.shares.find((share) => share.isSelf) ?? pot.shares[0],
    [pot.shares],
  );

  const schema = useMemo(
    () =>
      buildPotTakeOutFormSchema({
        baseCurrency: pot.baseCurrency,
        requiredMsg: tCommon('form.errors.required'),
        positiveMsg: t('pots.form.mustBePositive'),
      }),
    [pot.baseCurrency, t, tCommon],
  );

  const form = useForm<PotTakeOutFormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      memberId: defaultHolder === undefined ? '' : String(defaultHolder.memberId),
      date: asOfDate ?? today,
      // What the share is worth on the date, which is what normally moves. Editable because the two may
      // honestly differ: someone may accept less than their share is worth in order to get out.
      amount: defaultHolder?.value ?? '',
      amountCurrency: pot.baseCurrency,
      baseAmount: '',
      privateAccountId: '',
      potAccountId: '',
      notes: '',
    },
  });

  const watched = form.watch();
  const share = holderShare(pot, Number(watched.memberId));
  const forOwnSeat = canNamePrivateLeg(Number(watched.memberId), mySeatId);
  const crossCurrency = watched.amountCurrency !== pot.baseCurrency;
  // Both sides named is what makes the pot's value fall with the money that left it.
  const movesValue = !!watched.potAccountId && !!watched.privateAccountId;

  /*
   * A money figure with its currency beside it. `fmt.amount` formats the NUMBER at the currency's
   * precision and never adds a symbol — the pot page can leave it bare because its header carries a
   * currency badge, and a guided flow has no such anchor. Same shape `pots.ledger.credited` uses.
   */
  const money = (value: string, currency: string = pot.baseCurrency) =>
    `${fmt.amount(value, currency)} ${currency}`;

  const potAccounts = useMemo(
    () => potLegAccounts(holdings, pot.baseCurrency),
    [holdings, pot.baseCurrency],
  );
  const eligiblePrivate = useMemo(
    () => privateAccounts.filter((a) => a.isActive),
    [privateAccounts],
  );

  /*
   * Changing the date re-reads the pot on the server rather than re-pricing here, so the share value
   * shown is always the one the event will be recorded at. `replace` rather than `push`: the date is a
   * correction to the same step, not a place to go back to.
   */
  function onDateChange(value: string) {
    form.setValue('date', value);
    startNavigation(() =>
      router.replace(
        value === today ? sharedTakeOutPath(pot.id) : `${sharedTakeOutPath(pot.id)}?date=${value}`,
      ),
    );
  }

  // Whose share it is decides the money figure and whether a private account may be named at all.
  function onMemberChange(value: string) {
    form.setValue('memberId', value);
    form.setValue('amount', holderShare(pot, Number(value))?.value ?? '');
    if (!canNamePrivateLeg(Number(value), mySeatId)) {
      form.setValue('privateAccountId', '');
      form.setValue('amountCurrency', pot.baseCurrency);
      form.setValue('baseAmount', '');
    }
  }

  /*
   * `amount` is in the private account's currency, so picking one settles it — merged constraint (a),
   * which the API enforces on this leg too. Across currencies the share's own value becomes the figure
   * taken from the pot (`baseAmount`, always in the base currency) and the amount that arrives in the
   * private account has to be stated, because no rate is ever stored.
   */
  function onPrivateAccountChange(value: string) {
    form.setValue('privateAccountId', value);
    const account = eligiblePrivate.find((a) => String(a.id) === value);
    const currency = account?.currency ?? pot.baseCurrency;
    form.setValue('amountCurrency', currency);
    if (currency === pot.baseCurrency) {
      form.setValue('baseAmount', '');
      form.setValue('amount', share?.value ?? '');
    } else {
      form.setValue('baseAmount', share?.value ?? '');
      form.setValue('amount', '');
    }
  }

  async function onWhoContinue() {
    if (!(await form.trigger(['memberId', 'date']))) return;
    setStage('where');
  }

  async function onWhereContinue() {
    if (!(await form.trigger(['amount', 'baseAmount']))) return;
    setStage('confirm');
  }

  async function onConfirm() {
    if (share === undefined) return;
    setPending(true);
    try {
      const result = await takePotShareOut(pot.id, pot.baseCurrency, form.getValues());
      if (!result.ok) {
        toast.error(result.conflictDetail);
        return;
      }
      setOutcome({
        name: share.displayName,
        amount: money(form.getValues('amount'), watched.amountCurrency),
        movedValue: movesValue,
      });
      setStage('done');
      // Refetches the pot so the closing panel reads the split that is now RECORDED, gated on the
      // refresh landing so no pre-write figure is ever shown as if it were the outcome.
      startNavigation(() => router.refresh());
    } catch {
      toast.error(t('pots.movement.error'));
    } finally {
      setPending(false);
    }
  }

  const steps = [
    t('pots.takeOut.steps.who'),
    t('pots.takeOut.steps.where'),
    t('pots.wizard.stepConfirm'),
  ];
  const stepIndex = STAGE_ORDER.indexOf(stage);

  const back: Partial<Record<Stage, () => void>> = {
    where: () => setStage('who'),
    confirm: () => setStage('where'),
  };
  const primary: Partial<
    Record<Stage, { label: string; loadingLabel: string; onClick: () => void; disabled?: boolean }>
  > = {
    who: {
      label: t('pots.wizard.continueCta'),
      loadingLabel: t('form.cta.loading'),
      onClick: onWhoContinue,
      disabled: !priceable || share === undefined,
    },
    where: {
      label: t('pots.wizard.continueCta'),
      loadingLabel: t('form.cta.loading'),
      onClick: onWhereContinue,
    },
    confirm: {
      label: t('pots.takeOut.confirm.cta'),
      loadingLabel: t('form.cta.loading'),
      onClick: onConfirm,
    },
  };

  return (
    <WizardShell
      title={t('pots.takeOut.title')}
      subtitle={t('pots.takeOut.subtitle', { name: label })}
      exitHref={sharedPotPath(pot.id)}
      exitLabel={t('pots.wizard.backToPot', { name: label })}
      steps={steps}
      current={stepIndex === -1 ? null : stepIndex}
      stageKey={stage}
      onBack={back[stage]}
      backLabel={t('pots.wizard.back')}
      primary={primary[stage]}
      pending={pending || isNavigating}
    >
      {/*
       * Mounted only while a step actually holds fields — otherwise the closing panel renders an
       * empty <form> beside it. The values live in `useForm` above, which never unmounts.
       */}
      {stage !== 'done' && (
        <Form {...form}>
          <form className="flex flex-col min-w-0 gap-y-6" noValidate>
            {stage === 'who' && (
              <WizardPanel
                title={t('pots.takeOut.who.title')}
                description={t('pots.takeOut.who.description')}
              >
                <div className="flex min-w-0 items-start gap-x-3">
                  <FormField
                    control={form.control}
                    name="memberId"
                    render={({ field }) => (
                      <FormItem required className="flex-1 min-w-0">
                        <FormLabel>{t('pots.takeOut.who.member.label')}</FormLabel>
                        <FormControl>
                          <FormCombobox
                            value={field.value ?? ''}
                            onValueChange={onMemberChange}
                            options={pot.shares.map((row) => ({
                              value: String(row.memberId),
                              label: `${row.displayName} · ${fmt.sharePct(Number(row.percentage))}%`,
                            }))}
                            placeholder={t('pots.takeOut.who.member.placeholder')}
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
                            onChange={onDateChange}
                            placeholder={t('pots.movement.date.placeholder')}
                            maxDate={today}
                          />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </div>

                {/*
                 * THREE states, not two. Whether the pot can be priced on that date is a fact about the
                 * date, decided by the server's answer for it, and is stated whenever it is false; what
                 * the share is worth needs a seat to be about. The picker stays usable either way, so
                 * the person can get back out of a date that does not work.
                 */}
                {!isPriceable(pot) ? (
                  <p className="text-paragraph-sm text-muted-foreground">
                    {t('pots.takeOut.who.unpriced')}
                  </p>
                ) : (
                  share?.value != null && (
                    <p className="text-paragraph-sm text-muted-foreground">
                      {t('pots.takeOut.who.worth', { amount: money(share.value) })}
                    </p>
                  )
                )}
              </WizardPanel>
            )}

            {stage === 'where' && (
              <WizardPanel
                title={t('pots.takeOut.where.title')}
                description={t('pots.takeOut.where.description')}
              >
                <FormField
                  control={form.control}
                  name="potAccountId"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>{t('pots.movement.potLeg.labelOut')}</FormLabel>
                      <FormControl>
                        <FormCombobox
                          value={field.value ?? ''}
                          onValueChange={field.onChange}
                          options={potAccounts.map((account) => ({
                            value: String(account.id),
                            label: account.name,
                          }))}
                          placeholder={t('pots.movement.potLeg.placeholder')}
                          emptyText={t('pots.movement.potLeg.empty', {
                            currency: pot.baseCurrency,
                          })}
                          className="w-full"
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                {forOwnSeat ? (
                  <FormField
                    control={form.control}
                    name="privateAccountId"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>{t('pots.movement.privateLeg.labelIn')}</FormLabel>
                        <FormControl>
                          <FormCombobox
                            value={field.value ?? ''}
                            onValueChange={onPrivateAccountChange}
                            options={eligiblePrivate.map((account) => ({
                              value: String(account.id),
                              label: `${account.name} · ${account.currency}`,
                            }))}
                            placeholder={t('pots.movement.privateLeg.placeholder')}
                            emptyText={t('pots.movement.privateLeg.empty')}
                            className="w-full"
                          />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                ) : (
                  <p className="text-paragraph-xs text-muted-foreground">
                    {t('pots.takeOut.where.otherSeat')}
                  </p>
                )}

                <FormField
                  control={form.control}
                  name="amount"
                  render={({ field }) => (
                    <FormItem required>
                      <FormLabel>
                        {t('pots.takeOut.where.amountLabel', { currency: watched.amountCurrency })}
                      </FormLabel>
                      <FormControl>
                        <LocaleAmountInput
                          {...field}
                          currency={watched.amountCurrency}
                          placeholder={t('pots.movement.amount.placeholder')}
                        />
                      </FormControl>
                      <p className="text-paragraph-xs text-muted-foreground">
                        {t('pots.takeOut.where.amountHint')}
                      </p>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                {/*
                 * Across currencies the pot side is not what arrives in the private account, and no rate
                 * is ever stored — so both figures are recorded. This one is the share's own value and is
                 * not typed: it is what the flow is about.
                 */}
                {crossCurrency && (
                  <div className="flex flex-col gap-y-1">
                    <span className="text-paragraph-sm text-muted-foreground">
                      {t('pots.takeOut.where.creditedLabel')}
                    </span>
                    <span className="text-paragraph-medium tabular-nums text-foreground">
                      {watched.baseAmount === undefined || watched.baseAmount === ''
                        ? t('pots.unvalued')
                        : money(watched.baseAmount)}
                    </span>
                    <p className="text-paragraph-xs text-muted-foreground">
                      {t('pots.takeOut.where.creditedHint')}
                    </p>
                  </div>
                )}
              </WizardPanel>
            )}

            {stage === 'confirm' && share !== undefined && (
              <WizardPanel
                title={t('pots.takeOut.confirm.title')}
                description={t('pots.takeOut.confirm.description')}
              >
                <dl className="flex flex-col p-4 gap-y-3 bg-muted/30 border border-border rounded-1.5xl">
                  <WizardConfirmRow
                    label={t('pots.takeOut.confirm.taking')}
                    value={money(watched.amount, watched.amountCurrency)}
                  />
                  <WizardConfirmRow
                    label={t('pots.takeOut.confirm.shareGivenUp')}
                    value={`${share.displayName} · ${fmt.sharePct(Number(share.percentage))}%`}
                  />
                </dl>

                {/*
                 * What happens to everyone ELSE, as one of three whole sentences rather than a predicted
                 * set of percentages. Those are recomputed server-side with the rounding remainder carried
                 * to the largest holder, so a second copy here would be a second algorithm to disagree —
                 * and these three cases need no arithmetic at all.
                 */}
                <p className="text-paragraph-sm text-muted-foreground">
                  {t(`pots.takeOut.confirm.${wholeExitOutcome(pot, share.memberId)}`, {
                    name:
                      pot.shares.find((row) => row.memberId !== share.memberId)?.displayName ?? '',
                  })}
                </p>

                {!movesValue && (
                  <p className="text-paragraph-sm text-amber-600">
                    {t('pots.takeOut.confirm.valueWaits')}
                  </p>
                )}

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
              </WizardPanel>
            )}
          </form>
        </Form>
      )}

      {stage === 'done' && outcome !== null && (
        <WizardSummary
          title={t('pots.takeOut.done.title')}
          rows={(isNavigating ? [] : pot.shares).map((row) => ({
            id: row.memberId,
            label: row.displayName,
            value: `${fmt.sharePct(Number(row.percentage))}%`,
            note: row.value === null ? t('pots.unvalued') : money(row.value),
          }))}
          lines={[
            t('pots.takeOut.done.took', { name: outcome.name, amount: outcome.amount }),
            // Same gate as the rows: mid-refresh `pot` is still the state before the write.
            ...(!isNavigating && pot.shares.length === 0
              ? [t('pots.takeOut.done.nobodyLeft')]
              : []),
            ...(outcome.movedValue ? [] : [t('pots.takeOut.done.valueWaits')]),
          ]}
          actions={
            <Button blue asChild>
              <Link href={sharedPotPath(pot.id)}>{t('pots.wizard.openShared')}</Link>
            </Button>
          }
        />
      )}
    </WizardShell>
  );
}
