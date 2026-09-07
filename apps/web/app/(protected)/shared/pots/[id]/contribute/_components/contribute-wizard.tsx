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
import { contributePotHolding } from '@/app/(protected)/shared/pot-actions';
import {
  buildPotContributeFormSchema,
  type PotContributeFormValues,
} from '@/app/(protected)/shared/pot-form-schema';
import {
  findHolding,
  hasContributableHoldings,
  holdingKey,
} from '@/app/(protected)/shared/pot-rules';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/form';
import { FormCombobox } from '@/components/form-combobox';
import { sharedPotPath } from '@/config/routes';
import type { Pot, PotHoldings } from '@/lib/api/pots';
import { useFormatters } from '@/lib/i18n/formatters';
import { potLabel } from '@/lib/pots';

type Stage = 'what' | 'confirm' | 'done';

const STAGE_ORDER: Stage[] = ['what', 'confirm'];

interface ContributeWizardProps {
  pot: Pot;
  // Only what the API would accept: it applies the same seven refusals as filters, so nothing here
  // can be picked and then refused.
  holdings: PotHoldings;
}

/*
 * Contributing something you own to shared money whose split is already agreed.
 *
 * The shortest of the four flows, and the emptiness is what it is about. There is no amount, because
 * the value is a fact about the holding — and a contribution valued higher than the thing would issue
 * units against value that never arrived and dilute every other owner, which is the exact harm this
 * flow exists to close. There is no date, because a holding counts in the pot's value from the moment
 * it moves, so pricing it at an earlier one hands the difference out pro-rata. And there is no member,
 * because the holding is yours.
 *
 * One write, at the end, so there is nothing partial to recover from. What it needs instead is to say
 * clearly what happens to everybody else — their share keeps its value and loses percentage — because
 * that is the sentence a person is owed before handing an asset to a group.
 */
export function ContributeWizard({ pot, holdings }: ContributeWizardProps) {
  const fmt = useFormatters();
  const t = useTranslations('shared');
  const tCommon = useTranslations('common');
  const router = useRouter();

  const [stage, setStage] = useState<Stage>('what');
  const [pending, setPending] = useState(false);
  /*
   * The post-write refresh is a navigation, and it is kept observable rather than fire-and-forget: a
   * Server Action issued while one is in flight is CANCELLED by it and its promise never settles. It
   * is also the honest state on its own — until the refresh lands, `pot` still holds the split from
   * BEFORE the write, so the closing panel would state the previous shares as if they were the result.
   */
  const [isNavigating, startNavigation] = useTransition();
  // Kept from before the write: afterwards the holding is the pot's and no longer a candidate here.
  const [outcome, setOutcome] = useState<{ name: string; amount: string; credited: string } | null>(
    null,
  );

  const label = potLabel(pot, tCommon('potDefaultLabel'));
  const anythingToOffer = hasContributableHoldings(holdings);

  const schema = useMemo(
    () => buildPotContributeFormSchema(tCommon('form.errors.required')),
    [tCommon],
  );

  const form = useForm<PotContributeFormValues>({
    resolver: zodResolver(schema),
    // Validated on change for the reason every wizard here is: a step advances through `trigger()`,
    // which never sets `isSubmitted`, so react-hook-form's default re-validation never starts and a
    // "this field is required" would stay on screen after the field was filled.
    mode: 'onChange',
    defaultValues: { holding: '', notes: '' },
  });

  const watched = form.watch();
  const chosen = findHolding(holdings, watched.holding);

  /*
   * A money figure with its currency beside it. `fmt.amount` formats the NUMBER at the currency's
   * precision and never adds a symbol — the pot page can leave figures bare because its header carries
   * a currency badge, and a guided flow has no such anchor.
   */
  const money = (value: string, currency: string = pot.baseCurrency) =>
    `${fmt.amount(value, currency)} ${currency}`;

  /*
   * One control over two lists, grouped so a row's kind is visible rather than inferred from its name.
   * The key carries the kind because ids collide across the two tables.
   */
  const options = useMemo(
    () => [
      ...holdings.investments.map((row) => ({
        value: holdingKey('investment', row.id),
        label: row.name,
        group: t('pots.holdings.investments'),
      })),
      ...holdings.accounts.map((row) => ({
        value: holdingKey('account', row.id),
        label: row.name,
        group: t('pots.holdings.accounts'),
      })),
    ],
    [holdings, t],
  );

  // Both figures are non-null for every row the API offered — the picker's whole contract — so the
  // sentence never has to hedge about a value it is showing.
  const converted = chosen !== null && chosen.currency !== pot.baseCurrency;

  async function onWhatContinue() {
    if (!(await form.trigger(['holding']))) return;
    setStage('confirm');
  }

  async function onConfirm() {
    if (chosen === null) return;
    setPending(true);
    try {
      const result = await contributePotHolding(pot.id, form.getValues());
      if (!result.ok) {
        toast.error(result.conflictDetail);
        return;
      }
      setOutcome({
        name: chosen.name,
        amount: money(chosen.value ?? '0', chosen.currency),
        credited: money(chosen.baseValue ?? '0'),
      });
      setStage('done');
      // Refetches the pot so the closing panel reads the split that is now RECORDED, gated on the
      // refresh landing so no pre-write figure is ever shown as if it were the outcome.
      startNavigation(() => router.refresh());
    } catch {
      toast.error(t('pots.contribute.error'));
    } finally {
      setPending(false);
    }
  }

  const steps = [t('pots.contribute.steps.what'), t('pots.wizard.stepConfirm')];
  const stepIndex = STAGE_ORDER.indexOf(stage);

  const back: Partial<Record<Stage, () => void>> = { confirm: () => setStage('what') };
  const primary: Partial<
    Record<Stage, { label: string; loadingLabel: string; onClick: () => void; disabled?: boolean }>
  > = {
    what: {
      label: t('pots.wizard.continueCta'),
      loadingLabel: t('form.cta.loading'),
      onClick: onWhatContinue,
      disabled: !anythingToOffer,
    },
    confirm: {
      label: t('pots.contribute.confirm.cta'),
      loadingLabel: t('form.cta.loading'),
      onClick: onConfirm,
    },
  };

  return (
    <WizardShell
      title={t('pots.contribute.title')}
      subtitle={t('pots.contribute.subtitle', { name: label })}
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
            {stage === 'what' && (
              <WizardPanel
                title={t('pots.contribute.what.title')}
                description={t('pots.contribute.what.description')}
              >
                <FormField
                  control={form.control}
                  name="holding"
                  render={({ field }) => (
                    <FormItem required>
                      <FormLabel>{t('pots.contribute.what.holding.label')}</FormLabel>
                      <FormControl>
                        <FormCombobox
                          value={field.value ?? ''}
                          onValueChange={field.onChange}
                          options={options}
                          placeholder={t('pots.contribute.what.holding.placeholder')}
                          emptyText={t('pots.contribute.what.holding.empty')}
                          className="w-full"
                          data-testid="contribute-holding"
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                {/*
                 * What it is worth, stated the moment it is picked rather than only on the next step:
                 * the value IS the decision here, and a person choosing between two holdings needs to
                 * see it while choosing. Across currencies both figures are shown, because the one
                 * that buys the share is the converted one.
                 */}
                {chosen !== null && (
                  <div className="flex flex-col gap-y-1">
                    <p
                      className="text-paragraph-sm text-muted-foreground"
                      data-testid="contribute-worth"
                    >
                      {converted
                        ? t('pots.contribute.what.worthConverted', {
                            amount: money(chosen.value ?? '0', chosen.currency),
                            credited: money(chosen.baseValue ?? '0'),
                          })
                        : t('pots.contribute.what.worth', {
                            amount: money(chosen.value ?? '0', chosen.currency),
                          })}
                    </p>
                    {/* Only an investment carries one; an account's balance is derived, so it has no
                        valuation date and the line would be an invented fact. */}
                    {chosen.valuedOn !== null && (
                      <p className="text-paragraph-xs text-muted-foreground">
                        {t('pots.contribute.what.valuedOn', { date: fmt.date(chosen.valuedOn) })}
                      </p>
                    )}
                  </div>
                )}

                <p className="text-paragraph-xs text-muted-foreground">
                  {t('pots.contribute.what.hint')}
                </p>
              </WizardPanel>
            )}

            {stage === 'confirm' && chosen !== null && (
              <WizardPanel
                title={t('pots.contribute.confirm.title')}
                description={t('pots.contribute.confirm.description')}
              >
                <dl className="flex flex-col p-4 gap-y-3 bg-muted/30 border border-border rounded-1.5xl">
                  <WizardConfirmRow
                    label={t('pots.contribute.confirm.adding')}
                    value={`${chosen.name} · ${money(chosen.value ?? '0', chosen.currency)}`}
                  />
                  {/* Only when they differ: repeating the same figure under a second label reads as
                      two facts and invites a comparison that does not exist. */}
                  {converted && (
                    <WizardConfirmRow
                      label={t('pots.contribute.confirm.credited')}
                      value={money(chosen.baseValue ?? '0')}
                    />
                  )}
                </dl>

                {/*
                 * What happens to everybody, in sentences rather than predicted percentages — those
                 * are recomputed server-side with the rounding remainder carried to the largest
                 * holder, so a second copy here would be a second algorithm to disagree with, and the
                 * figure it got wrong is the one a person checks.
                 */}
                <p className="text-paragraph-sm text-muted-foreground">
                  {t('pots.contribute.confirm.youGet', { amount: money(chosen.baseValue ?? '0') })}
                </p>
                <p className="text-paragraph-sm text-muted-foreground">
                  {t('pots.contribute.confirm.othersUnchanged')}
                </p>

                {/*
                 * The one honest caveat this flow has. Units are issued at the pot's value as it
                 * stands, so a pot nobody has re-valued in months prices the contribution against a
                 * figure that is out of date — and the contributor is the one who loses or gains by it.
                 * Stated when it applies rather than hidden, the same shape the take-out's
                 * "the value waits" line has.
                 */}
                {pot.isStale && pot.valuedAsOf !== null && (
                  <p className="text-paragraph-sm text-amber-600">
                    {t('pots.contribute.confirm.stale', { date: fmt.date(pot.valuedAsOf) })}
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
          title={t('pots.contribute.done.title')}
          // Empty mid-refresh: `pot` still holds the split from before the write until it lands.
          rows={(isNavigating ? [] : pot.shares).map((row) => ({
            id: row.memberId,
            label: row.displayName,
            value: `${fmt.sharePct(Number(row.percentage))}%`,
            note: row.value === null ? t('pots.unvalued') : money(row.value),
          }))}
          lines={[
            t('pots.contribute.done.added', { name: outcome.name, amount: outcome.amount }),
            t('pots.contribute.done.received', { amount: outcome.credited }),
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
