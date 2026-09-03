'use client';

import { useEffect, useMemo, useState, useTransition } from 'react';
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
import { buyPotShareOut } from '@/app/(protected)/shared/pot-actions';
import {
  buildPotBuyOutFormSchema,
  type PotBuyOutFormValues,
} from '@/app/(protected)/shared/pot-form-schema';
import {
  buyOutLeavesOneHolder,
  canRecordReagreement,
  holderShare,
  isPriceable,
} from '@/app/(protected)/shared/pot-rules';
import { DatePickerInput } from '@/components/date-picker-input';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/form';
import { FormCombobox } from '@/components/form-combobox';
import { sharedBuyOutPath, sharedPotPath } from '@/config/routes';
import type { Group } from '@/lib/api/groups';
import type { Pot } from '@/lib/api/pots';
import { useFormatters } from '@/lib/i18n/formatters';
import { potLabel } from '@/lib/pots';
import { todayInTimezone } from '@/lib/utils/dates';

type Stage = 'who' | 'recorded' | 'done';

const STAGE_ORDER: Stage[] = ['who', 'recorded'];

interface BuyOutWizardProps {
  // Valued AS AT `asOfDate`, so the figure shown is the one the event is recorded at.
  pot: Pot;
  group: Group;
  asOfDate?: string;
  timeZone?: string;
}

/*
 * One member taking over another's whole share.
 *
 * Two steps, because there are only two questions: who and whose, and then what Renly does and does
 * not record. The second is not a formality — it is the honest half of this flow. The shares change
 * hands and that IS recorded; the money paid for them is not, because it moves between two different
 * people's private accounts and nothing in Renly spans those. Saying so is better than recording a
 * cash leg through the shared account that never happened.
 *
 * It sends `whole_share` rather than the seller's percentage, and that is what makes a buy-out possible
 * at all: a stake stated as a percentage of the pot has to be rounded to two decimals and multiplied
 * back out by the units outstanding, which reproduced the seller's exact balance 18 times in 200,000
 * plausible pots. The rest split evenly between the API refusing (for asking to move precisely what
 * they own) and the seller keeping a residual that reads 0.00% and never goes away.
 *
 * Buying only PART of someone's share is a different thing and stays with the manual change-of-split
 * form, which takes a percentage on purpose.
 */
export function BuyOutWizard({ pot, group, asOfDate, timeZone }: BuyOutWizardProps) {
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
  // Kept from before the write: afterwards the seller holds no share to read a name from, and the
  // closing panel is about what happened rather than about what is on screen now.
  const [outcome, setOutcome] = useState<{ seller: string; buyer: string } | null>(null);

  const seats = useMemo(() => group.members.filter((m) => m.isActive), [group.members]);
  const today = todayInTimezone(timeZone);
  const label = potLabel(pot, tCommon('potDefaultLabel'));
  const applicable = canRecordReagreement(pot, group.activeMemberCount);

  const schema = useMemo(
    () =>
      buildPotBuyOutFormSchema({
        requiredMsg: tCommon('form.errors.required'),
        sameMemberMsg: t('pots.reagreement.sameMemberError'),
      }),
    [t, tCommon],
  );

  const form = useForm<PotBuyOutFormValues>({
    resolver: zodResolver(schema),
    /*
     * Validated on change, which these flows need and the dialogs beside them do not: a dialog submits
     * through `handleSubmit`, so react-hook-form flips `isSubmitted` and its default
     * `reValidateMode: 'onChange'` starts clearing errors as fields are fixed. A step advances through
     * `trigger()` instead, which never sets that flag — so without this a "This field is required"
     * stayed on screen after the field was filled, for the rest of the flow.
     */
    mode: 'onChange',
    defaultValues: { date: asOfDate ?? today, fromMemberId: '', toMemberId: '', notes: '' },
  });

  /*
   * A money figure with its currency beside it. `fmt.amount` formats the NUMBER at the currency's
   * precision and never adds a symbol — the pot page can leave it bare because its header carries a
   * currency badge, and a guided flow has no such anchor. Same shape `pots.ledger.credited` uses.
   */
  const money = (value: string, currency: string = pot.baseCurrency) =>
    `${fmt.amount(value, currency)} ${currency}`;

  const watched = form.watch();
  const seller = holderShare(pot, Number(watched.fromMemberId));
  const buyer = seats.find((seat) => String(seat.id) === watched.toMemberId);
  // The only holder left, if exactly one is — for the closing panel. Withheld until a refresh lands,
  // because until then `pot` still describes the split from BEFORE the write.
  const soleHolder = !isNavigating && pot.shares.length === 1 ? pot.shares[0] : undefined;

  /*
   * Clears a seller the re-read no longer knows about. Someone holding a share today may have held
   * none on an earlier date, and the selection survived the re-read pointing at nobody — which reached
   * the second step with an empty panel and a "Record it" that silently did nothing, because both are
   * guarded on a seller that no longer exists. The picker goes back to its placeholder instead.
   */
  useEffect(() => {
    if (holderShare(pot, Number(form.getValues('fromMemberId'))) === undefined) {
      form.setValue('fromMemberId', '');
    }
  }, [pot, form]);

  /*
   * Changing the date re-reads the pot on the server rather than re-valuing here, so what the share is
   * said to be worth is what the ledger will record. `replace`, not `push`: it corrects this step.
   */
  function onDateChange(value: string) {
    form.setValue('date', value);
    startNavigation(() =>
      router.replace(
        value === today ? sharedBuyOutPath(pot.id) : `${sharedBuyOutPath(pot.id)}?date=${value}`,
      ),
    );
  }

  async function onWhoContinue() {
    if (!(await form.trigger())) return;
    setStage('recorded');
  }

  async function onConfirm() {
    if (seller === undefined || buyer === undefined) return;
    setPending(true);
    try {
      const result = await buyPotShareOut(pot.id, form.getValues());
      if (!result.ok) {
        toast.error(result.conflictDetail);
        return;
      }
      setOutcome({ seller: seller.displayName, buyer: buyer.displayName });
      setStage('done');
      // Refetches the pot so the closing panel reads the split that is now RECORDED, gated on the
      // refresh landing so no pre-write figure is ever shown as if it were the outcome.
      startNavigation(() => router.refresh());
    } catch {
      toast.error(t('pots.reagreement.error'));
    } finally {
      setPending(false);
    }
  }

  const steps = [t('pots.buyOut.steps.who'), t('pots.buyOut.steps.recorded')];
  const stepIndex = STAGE_ORDER.indexOf(stage);

  const primary: Partial<
    Record<Stage, { label: string; loadingLabel: string; onClick: () => void; disabled?: boolean }>
  > = {
    who: {
      label: t('pots.wizard.continueCta'),
      loadingLabel: t('form.cta.loading'),
      onClick: onWhoContinue,
      disabled: !applicable,
    },
    recorded: {
      label: t('pots.buyOut.recorded.cta'),
      loadingLabel: t('form.cta.loading'),
      onClick: onConfirm,
    },
  };

  return (
    <WizardShell
      title={t('pots.buyOut.title')}
      subtitle={t('pots.buyOut.subtitle', { name: label })}
      exitHref={sharedPotPath(pot.id)}
      exitLabel={t('pots.wizard.backToPot', { name: label })}
      steps={steps}
      current={stepIndex === -1 ? null : stepIndex}
      stageKey={stage}
      onBack={stage === 'recorded' ? () => setStage('who') : undefined}
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
                title={t('pots.buyOut.who.title')}
                description={t('pots.buyOut.who.description')}
              >
                <FormField
                  control={form.control}
                  name="fromMemberId"
                  render={({ field }) => (
                    <FormItem required>
                      <FormLabel>{t('pots.buyOut.who.from.label')}</FormLabel>
                      <FormControl>
                        <FormCombobox
                          value={field.value ?? ''}
                          onValueChange={field.onChange}
                          // Holders only, with their share beside them: it is the thing moving.
                          options={pot.shares.map((row) => ({
                            value: String(row.memberId),
                            label: `${row.displayName} · ${fmt.sharePct(Number(row.percentage))}%`,
                          }))}
                          placeholder={t('pots.buyOut.who.from.placeholder')}
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
                      <FormLabel>{t('pots.buyOut.who.to.label')}</FormLabel>
                      <FormControl>
                        <FormCombobox
                          value={field.value ?? ''}
                          onValueChange={field.onChange}
                          // Any active seat: someone can be bought in from holding nothing at all.
                          options={seats.map((seat) => ({
                            value: String(seat.id),
                            label: seat.displayName,
                          }))}
                          placeholder={t('pots.buyOut.who.to.placeholder')}
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
                    <FormItem required>
                      <FormLabel>{t('pots.reagreement.date.label')}</FormLabel>
                      <FormControl>
                        <DatePickerInput
                          value={field.value}
                          onChange={onDateChange}
                          placeholder={t('pots.reagreement.date.placeholder')}
                          maxDate={today}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                {/*
                 * THREE states, not two. Whether the pot can be priced on that date is a fact about the
                 * date and is stated whenever it is false; what the share is worth needs a seat to be
                 * about. Collapsing them into a ternary made an unpicked seller read as "there is no
                 * value on record", which is a claim about the pot and was simply untrue.
                 */}
                {!isPriceable(pot) ? (
                  <p className="text-paragraph-sm text-muted-foreground">
                    {t('pots.buyOut.who.unpriced')}
                  </p>
                ) : (
                  seller?.value != null && (
                    <p className="text-paragraph-sm text-muted-foreground">
                      {t('pots.buyOut.who.worth', { amount: money(seller.value) })}
                    </p>
                  )
                )}
              </WizardPanel>
            )}

            {stage === 'recorded' && seller !== undefined && buyer !== undefined && (
              <WizardPanel
                title={t('pots.buyOut.recorded.title')}
                description={t('pots.buyOut.recorded.description')}
              >
                <dl className="flex flex-col p-4 gap-y-3 bg-muted/30 border border-border rounded-1.5xl">
                  <WizardConfirmRow
                    label={t('pots.buyOut.recorded.moving')}
                    value={`${seller.displayName} → ${buyer.displayName}`}
                  />
                  <WizardConfirmRow
                    label={t('pots.buyOut.recorded.worth', { date: fmt.date(watched.date) })}
                    value={seller.value === null ? t('pots.unvalued') : money(seller.value)}
                  />
                </dl>

                <p className="text-paragraph-sm text-muted-foreground">
                  {t('pots.buyOut.recorded.recordedHere')}
                </p>

                {/*
                 * The honest half. A buyer→seller payment is a movement between two DIFFERENT people's
                 * private accounts, and nothing in Renly spans those, so it is not recorded — stated
                 * plainly rather than routed through the shared account as two events that never happened.
                 */}
                <p className="text-paragraph-sm text-amber-600">
                  {t('pots.buyOut.recorded.cashNotRecorded')}
                </p>

                {/*
                 * What it means for everyone else, as one of two whole sentences rather than a predicted
                 * set of percentages — those are recomputed server-side with their rounding remainder
                 * carried to the largest holder, so a copy here would be a second algorithm to disagree.
                 */}
                <p className="text-paragraph-sm text-muted-foreground">
                  {buyOutLeavesOneHolder(pot, seller.memberId, buyer.id)
                    ? t('pots.buyOut.recorded.allTo', { name: buyer.displayName })
                    : t('pots.buyOut.recorded.othersUntouched')}
                </p>

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
          title={t('pots.buyOut.done.title')}
          rows={(isNavigating ? [] : pot.shares).map((row) => ({
            id: row.memberId,
            label: row.displayName,
            value: `${fmt.sharePct(Number(row.percentage))}%`,
            note: row.value === null ? t('pots.unvalued') : money(row.value),
          }))}
          lines={[
            t('pots.buyOut.done.moved', { name: outcome.seller }),
            // Read from the REFRESHED pot, so it states the split that is now recorded. One holder
            // left is exactly 100% by definition rather than by any calculation done here.
            ...(soleHolder === undefined
              ? []
              : [t('pots.buyOut.done.oneHolderLeft', { name: soleHolder.displayName })]),
            t('pots.buyOut.done.cash'),
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
