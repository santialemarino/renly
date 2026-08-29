'use client';

import { useMemo, useState, useTransition } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { zodResolver } from '@hookform/resolvers/zod';
import { Landmark, Rows3 } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { useForm } from 'react-hook-form';
import { toast } from 'sonner';

import { Button, Input, Label } from '@repo/ui/components';
import { CurrencyCombobox } from '@/app/(protected)/_components/currency-combobox';
import { PotShareRows } from '@/app/(protected)/shared/_components/pot-share-rows';
import {
  WizardConfirmRow,
  WizardPanel,
  WizardShell,
} from '@/app/(protected)/shared/_components/wizard-shell';
import { WizardSummary } from '@/app/(protected)/shared/_components/wizard-summary';
import { createPot, movePotHoldings, recordPotOpening } from '@/app/(protected)/shared/pot-actions';
import {
  buildPotOpeningFormSchema,
  openingSharesTotal,
  type PotOpeningFormValues,
} from '@/app/(protected)/shared/pot-form-schema';
import { suggestedBaseCurrency, type SharePotStage } from '@/app/(protected)/shared/pot-rules';
import { ComboboxMultiSelect } from '@/components/combobox-multi-select';
import { DatePickerInput } from '@/components/date-picker-input';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/form';
import { FormCombobox } from '@/components/form-combobox';
import { LocaleAmountInput } from '@/components/locale-amount-input';
import { sharedGroupPath, sharedPotPath, sharedSharePath } from '@/config/routes';
import type { Account } from '@/lib/api/accounts';
import type { Group } from '@/lib/api/groups';
import type { Investment } from '@/lib/api/investments';
import type { Pot } from '@/lib/api/pots';
import { POT_PERCENTAGE_TOTAL, POT_VISIBILITIES, type PotVisibility } from '@/lib/constants/pots';
import { useFormatters } from '@/lib/i18n/formatters';
import { todayInTimezone } from '@/lib/utils/dates';

// The panels that are actually steps, in order. `done` and `divided` are outcomes, not positions.
const STAGE_ORDER: SharePotStage[] = ['pick', 'value', 'shares', 'confirm'];

interface ShareWizardProps {
  group: Group;
  // Null until this run creates it. Non-null on a resumed run, and refreshed after the final write —
  // which is what lets the closing panel state what was actually recorded rather than what was asked.
  pot: Pot | null;
  // How many things the pot ACTUALLY holds. Distinct from the current selection on purpose — see below.
  sharedCount: number;
  entryStage: SharePotStage;
  privateAccounts: Account[];
  privateInvestments: Investment[];
  preferredCurrencies?: string[];
  timeZone?: string;
}

/*
 * Sharing something you already own, end to end: what it is, what it is worth, whose it is, confirm.
 *
 * The three writes happen at two points and in an order that is not interchangeable. Step 1 creates
 * the pot and moves the holdings in; step 4 records the baseline. Holdings can still LEAVE a pot whose
 * ownership has not been agreed (409 pot_already_divided afterwards), so everything before the last
 * write stays undoable by hand — which is what makes a failure between them safe rather than
 * unrecoverable.
 *
 * The id goes into the URL the moment the pot exists, before the holdings even move. That is the whole
 * recovery mechanism: the step is derived from server state, so a reload, a crash or a closed tab
 * re-enters at the first thing still missing instead of creating a second pot.
 *
 * The value on step 2 is prefilled from what the holdings turned out to be worth, which is the one
 * figure the user would otherwise have to go and look up — and the move's own response carries it, so
 * it costs no extra read. It stays editable because the baseline is a statement about a DATE, and a
 * back-dated one is not today's figure.
 */
export function ShareWizard({
  group,
  pot,
  sharedCount,
  entryStage,
  privateAccounts,
  privateInvestments,
  preferredCurrencies,
  timeZone,
}: ShareWizardProps) {
  const fmt = useFormatters();
  const t = useTranslations('shared');
  const tCommon = useTranslations('common');
  const router = useRouter();

  /*
   * Seeded from the server's answer and then owned by the client, which is deliberate: after the final
   * write the derived entry becomes `divided` (a baseline now exists), and the person who just recorded
   * it should be reading the closing panel rather than being told the flow no longer applies.
   */
  const [stage, setStage] = useState<SharePotStage>(entryStage);
  const [potId, setPotId] = useState<number | null>(pot?.id ?? null);
  const [investmentIds, setInvestmentIds] = useState<number[]>([]);
  const [accountIds, setAccountIds] = useState<number[]>([]);
  const [name, setName] = useState('');
  const [baseCurrency, setBaseCurrency] = useState<string | null>(null);
  const [visibility, setVisibility] = useState<PotVisibility>('members');
  const [pending, setPending] = useState(false);
  const [sharesAttempted, setSharesAttempted] = useState(false);
  const [valuePrefilled, setValuePrefilled] = useState(pot?.nav !== null && pot?.nav !== undefined);
  /*
   * Navigations, kept observable rather than fire-and-forget. Two reasons, and the first is a real
   * defect this prevents: a Server Action issued while a navigation is in flight is CANCELLED by
   * it, and its promise never settles — no result, no catch, no finally, just a button stuck on its
   * loading label for good. So the primary is unavailable until the navigation lands. The second is
   * honesty: until a refresh lands, `pot` still describes the state BEFORE the write.
   */
  const [isNavigating, startNavigation] = useTransition();

  const seats = useMemo(() => group.members.filter((m) => m.isActive), [group.members]);
  const today = todayInTimezone(timeZone);
  const eligibleAccounts = useMemo(
    () => privateAccounts.filter((a) => a.isActive),
    [privateAccounts],
  );

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
    /*
     * Validated on change, which these flows need and the dialogs beside them do not: a dialog submits
     * through `handleSubmit`, so react-hook-form flips `isSubmitted` and its default
     * `reValidateMode: 'onChange'` starts clearing errors as fields are fixed. A step advances through
     * `trigger()` instead, which never sets that flag — so without this a "This field is required"
     * stayed on screen after the field was filled, for the rest of the flow.
     */
    mode: 'onChange',
    defaultValues: {
      date: today,
      // Prefilled on a resumed run for the same reason it is after the move: it is what the holdings
      // are worth, and the person should not have to go and add them up.
      value: pot?.nav ?? '',
      shares: seats.map((seat) => ({ memberId: seat.id, percentage: '' })),
      notes: '',
    },
  });

  const watched = form.watch();
  const sharesBalanced = openingSharesTotal(watched.shares ?? []) === POT_PERCENTAGE_TOTAL;
  /*
   * Two counts, and conflating them was a real defect: how many things are SELECTED gates step 1, and
   * how many the pot HOLDS is what the confirmation states. They are equal only on an uninterrupted
   * run — every resumed one arrives with an empty selection, so a confirmation built from it read
   * "Sharing 0 things" about a pot holding two.
   */
  const selectedCount = investmentIds.length + accountIds.length;
  const isNewPot = potId === null;

  /*
   * The currency to offer: whichever most of the selection already uses. Not a nicety — a movement's
   * pot-side leg must be an account in the pot's base currency, so a pot created in a currency none of
   * its accounts use has no usable cash leg and the first contribution is refused.
   */
  const suggestedCurrency = useMemo(() => {
    const currencies = [
      ...privateInvestments.filter((i) => investmentIds.includes(i.id)).map((i) => i.baseCurrency),
      ...eligibleAccounts.filter((a) => accountIds.includes(a.id)).map((a) => a.currency),
    ];
    return suggestedBaseCurrency(currencies);
  }, [privateInvestments, eligibleAccounts, investmentIds, accountIds]);

  /*
   * The pot's own base currency wins the moment the pot exists, and the suggestion is only ever a
   * pre-creation guess. Not a preference — the suggestion is derived from the PRIVATE lists, and the
   * things this flow just moved in are no longer in them, so from step 2 onwards it answers null and
   * every figure downstream loses its currency. That is exactly what the browser showed: a confirmation
   * reading `48000.00`.
   */
  const chosenCurrency = pot?.baseCurrency ?? baseCurrency ?? suggestedCurrency;

  /*
   * A money figure with its currency beside it. `fmt.amount` formats the NUMBER at the currency's
   * precision and never adds a symbol — the pot page can leave it bare because its header carries a
   * currency badge, and a guided flow has no such anchor. Same shape `pots.ledger.credited` uses.
   * Takes the currency explicitly here, because this flow runs before the pot exists to have one.
   */
  const money = (value: string, currency: string) => `${fmt.amount(value, currency)} ${currency}`;

  function toggle(setter: React.Dispatch<React.SetStateAction<number[]>>, id: number) {
    setter((ids) => (ids.includes(id) ? ids.filter((existing) => existing !== id) : [...ids, id]));
  }

  /*
   * Step 1's two writes, and then — only then — the URL.
   *
   * NEVER navigate with a write still to come. `router.replace` starts a navigation, and a Server
   * Action issued after it is CANCELLED by that navigation: the promise never settles, so neither the
   * result branch nor `catch` nor `finally` ever runs. The button sits on its loading label forever
   * with no error anywhere, and `tsc`, ESLint, the unit tests and `build:web` all pass it. Only the
   * browser showed it, and it took a stuck spinner to notice.
   *
   * So the id goes into the URL once nothing is in flight, and on BOTH paths — by then the pot exists
   * either way, and a failure on the move is exactly the case the URL has to survive: without it a
   * reload would start over and make a second pot. Retrying skips the creation, `potId` being set.
   */
  async function onPickContinue() {
    if (chosenCurrency === null) return;
    /*
     * Nothing new to move, but the pot already holds what it needs — so this step is simply satisfied.
     * That is the state Back from step 2 lands in: the selection was consumed by the move, and
     * re-submitting it would ask the API to move holdings that are no longer private, which answers
     * "Holding not found" about something the picker was still showing.
     */
    if (selectedCount === 0) {
      if (sharedCount > 0) setStage('value');
      return;
    }
    setPending(true);
    // Declared out here so `finally` can see it on every exit — including a thrown one.
    let created: number | null = null;
    try {
      let targetId = potId;
      if (targetId === null) {
        const result = await createPot(group.id, {
          name,
          baseCurrency: chosenCurrency,
          visibility,
        });
        if (!result.ok) {
          toast.error(result.conflictDetail);
          return;
        }
        targetId = result.data.id;
        created = targetId;
        setPotId(targetId);
      }

      const moved = await movePotHoldings(targetId, investmentIds, accountIds, true);
      if (!moved.ok) {
        toast.error(moved.conflictDetail);
        return;
      }
      // What they turned out to be worth, from the write's own response rather than a second read.
      form.setValue('value', moved.data.nav ?? '');
      setValuePrefilled(moved.data.nav !== null);
      // The selection has been consumed. Coming back to this step should offer an empty picker for
      // anything MORE to add, not the same rows already sitting in the pot.
      setInvestmentIds([]);
      setAccountIds([]);
      setStage('value');
    } catch {
      toast.error(t('pots.share.moveError'));
    } finally {
      setPending(false);
      // In `finally` because the pot may exist however this ended — refused, thrown or fine — and the
      // URL is the only thing that makes it findable again. Putting it on the success path alone left
      // a thrown move with a pot nobody could reach, which a reload would then duplicate.
      // Here and nowhere earlier: by now every await has settled, so there is no Server Action left for
      // the navigation to cancel — a cancelled one never settles at all, and the flow hangs for good.
      const madeId = created;
      if (madeId !== null) {
        startNavigation(() => router.replace(sharedSharePath(group.id, madeId)));
      }
    }
  }

  async function onValueContinue() {
    if (!(await form.trigger(['date', 'value']))) return;
    setStage('shares');
  }

  function onSharesContinue() {
    setSharesAttempted(true);
    if (!sharesBalanced) return;
    setStage('confirm');
  }

  async function onConfirm() {
    if (potId === null) return;
    setPending(true);
    try {
      const result = await recordPotOpening(potId, form.getValues());
      if (!result.ok) {
        toast.error(result.conflictDetail);
        return;
      }
      setStage('done');
      // Refetches the pot so the closing panel reads the RECORDED split rather than the typed one,
      // gated on the refresh landing so no pre-write figure is shown as if it were the outcome.
      startNavigation(() => router.refresh());
    } catch {
      toast.error(t('pots.opening.error'));
    } finally {
      setPending(false);
    }
  }

  const steps = [
    t('pots.share.steps.pick'),
    t('pots.share.steps.value'),
    t('pots.share.steps.shares'),
    t('pots.wizard.stepConfirm'),
  ];
  const stepIndex = STAGE_ORDER.indexOf(stage);

  const back: Record<string, () => void> = {
    value: () => setStage('pick'),
    shares: () => setStage('value'),
    confirm: () => setStage('shares'),
  };

  // The forward control per step. `done` and `divided` have none: there is nothing further to do.
  const primary = {
    pick: {
      label: t('pots.wizard.continueCta'),
      loadingLabel: t('form.cta.loading'),
      onClick: onPickContinue,
      // Unavailable only when there is nothing at all — neither picked now nor already in the pot.
      disabled: (selectedCount === 0 && sharedCount === 0) || chosenCurrency === null,
    },
    value: {
      label: t('pots.wizard.continueCta'),
      loadingLabel: t('form.cta.loading'),
      onClick: onValueContinue,
    },
    shares: {
      label: t('pots.wizard.continueCta'),
      loadingLabel: t('form.cta.loading'),
      onClick: onSharesContinue,
    },
    confirm: {
      label: t('pots.share.confirm.cta'),
      loadingLabel: t('form.cta.loading'),
      onClick: onConfirm,
    },
  }[stage as 'pick' | 'value' | 'shares' | 'confirm'];

  return (
    <WizardShell
      title={t('pots.share.title')}
      subtitle={t('pots.share.subtitle', { group: group.name })}
      exitHref={sharedGroupPath(group.id)}
      exitLabel={t('pots.backToGroup', { group: group.name })}
      steps={steps}
      current={stepIndex === -1 ? null : stepIndex}
      stageKey={stage}
      onBack={back[stage]}
      backLabel={t('pots.wizard.back')}
      primary={primary}
      pending={pending || isNavigating}
    >
      {stage === 'divided' && (
        <WizardPanel
          title={t('pots.share.divided.title')}
          description={t('pots.share.divided.description')}
        >
          {potId !== null && (
            <Button blue asChild className="self-start">
              <Link href={sharedPotPath(potId)}>{t('pots.wizard.openShared')}</Link>
            </Button>
          )}
        </WizardPanel>
      )}

      {stage === 'pick' && (
        <WizardPanel
          title={t('pots.share.pick.title')}
          description={t('pots.share.pick.description')}
        >
          <div className="flex flex-col gap-y-2">
            <Label>{t('pots.holdings.investments')}</Label>
            <ComboboxMultiSelect
              items={privateInvestments.map((i) => ({ id: i.id, label: i.name }))}
              selectedIds={investmentIds}
              onToggle={(id) => toggle(setInvestmentIds, id)}
              placeholder={t('pots.holdings.investmentsPlaceholder')}
              searchPlaceholder={t('pots.holdings.investmentsSearch')}
              emptyMessage={t('pots.holdings.investmentsEmpty')}
              showChips
              icon={<Rows3 className="size-4" />}
            />
          </div>

          <div className="flex flex-col gap-y-2">
            <Label>{t('pots.holdings.accounts')}</Label>
            <ComboboxMultiSelect
              items={eligibleAccounts.map((a) => ({
                id: a.id,
                label: `${a.name} · ${a.currency}`,
              }))}
              selectedIds={accountIds}
              onToggle={(id) => toggle(setAccountIds, id)}
              placeholder={t('pots.holdings.accountsPlaceholder')}
              searchPlaceholder={t('pots.holdings.accountsSearch')}
              emptyMessage={t('pots.holdings.accountsEmpty')}
              showChips
              icon={<Landmark className="size-4" />}
            />
            <p className="text-paragraph-xs text-muted-foreground">
              {t('pots.holdings.accountsHint')}
            </p>
          </div>

          {/*
           * Stated rather than left to a dead button: the primary is unavailable until something is
           * picked, and an unexplained disabled control is what this repo refuses everywhere else.
           */}
          {selectedCount === 0 && sharedCount === 0 && (
            <p className="text-paragraph-xs text-muted-foreground">
              {t('pots.share.pick.nothingSelected')}
            </p>
          )}

          {isNewPot ? (
            <div className="flex flex-col pt-2 gap-y-4 border-t border-border">
              <div className="flex flex-col gap-y-2">
                <Label>{t('pots.form.name.label')}</Label>
                <Input
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  placeholder={t('pots.form.name.placeholder')}
                />
                <p className="text-paragraph-xs text-muted-foreground">
                  {t('pots.form.name.hint')}
                </p>
              </div>

              <div className="flex flex-col gap-y-2">
                <Label required>{t('pots.form.baseCurrency.label')}</Label>
                <CurrencyCombobox
                  value={chosenCurrency}
                  exclude={[]}
                  preferredCurrencies={preferredCurrencies}
                  placeholder={t('pots.form.baseCurrency.placeholder')}
                  searchPlaceholder={t('pots.form.baseCurrency.searchPlaceholder')}
                  noResults={t('pots.form.baseCurrency.noResults')}
                  onChange={setBaseCurrency}
                />
                <p className="text-paragraph-xs text-muted-foreground">
                  {/* Two whole strings: which one is true depends on whether the figure came from the
                      selection or from the user, and that is a different fact about the same field. */}
                  {suggestedCurrency !== null && baseCurrency === null
                    ? t('pots.share.pick.currencyHint')
                    : t('pots.form.baseCurrency.hint')}
                </p>
              </div>

              <div className="flex flex-col gap-y-2">
                <Label required>{t('pots.form.visibility.label')}</Label>
                <FormCombobox
                  value={visibility}
                  onValueChange={(value) => setVisibility(value as PotVisibility)}
                  options={POT_VISIBILITIES.map((option) => ({
                    value: option,
                    label: t(`pots.visibility.${option}`),
                  }))}
                  placeholder={t('pots.form.visibility.placeholder')}
                  className="w-full"
                />
                <p className="text-paragraph-xs text-muted-foreground">
                  {t('pots.form.visibility.hint')}
                </p>
              </div>
            </div>
          ) : (
            <p className="text-paragraph-xs text-muted-foreground">
              {t('pots.share.pick.intoExisting')}
            </p>
          )}
        </WizardPanel>
      )}

      {/*
       * Mounted only for the stages that actually hold fields — otherwise `pick`, `done` and `divided`
       * each render an empty <form> element. The values live in `useForm` above, which never unmounts,
       * so nothing is lost when this does.
       */}
      {(stage === 'value' || stage === 'shares' || stage === 'confirm') && (
        <Form {...form}>
          <form className="flex flex-col min-w-0 gap-y-6" noValidate>
            {stage === 'value' && (
              <WizardPanel
                title={t('pots.share.value.title')}
                description={t('pots.share.value.description')}
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
                            currency={chosenCurrency ?? undefined}
                            placeholder={t('pots.opening.value.placeholder')}
                          />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </div>

                {/*
                 * Three mutually exclusive statements about where the figure came from, each a whole
                 * string. The last one matters most: the prefill is TODAY's value, so a back-dated
                 * baseline gets a figure that is right for the wrong day unless the user checks it.
                 */}
                <p className="text-paragraph-xs text-muted-foreground">
                  {!valuePrefilled
                    ? t('pots.share.value.unvalued')
                    : watched.date === today
                      ? t('pots.share.value.prefilled')
                      : t('pots.share.value.recheck')}
                </p>
              </WizardPanel>
            )}

            {stage === 'shares' && (
              <WizardPanel
                title={t('pots.share.shares.title')}
                description={t('pots.share.shares.description')}
              >
                <PotShareRows form={form} seats={seats} showTotalError={sharesAttempted} />
              </WizardPanel>
            )}

            {stage === 'confirm' && (
              <WizardPanel
                title={t('pots.share.confirm.title')}
                description={t('pots.share.confirm.description')}
              >
                <dl className="flex flex-col p-4 gap-y-3 bg-muted/30 border border-border rounded-1.5xl">
                  <WizardConfirmRow
                    label={t('pots.share.confirm.sharing')}
                    value={t('pots.share.confirm.thingCount', { count: sharedCount })}
                  />
                  <WizardConfirmRow
                    label={t('pots.share.confirm.worth', { date: fmt.date(watched.date) })}
                    value={
                      chosenCurrency === null ? watched.value : money(watched.value, chosenCurrency)
                    }
                  />
                  {/*
                   * Percentages only, and no money per person. The value each share works out to is
                   * derived server-side from the pot's own valuation with its rounding remainder carried
                   * to the largest holder — so a figure computed here would be a second copy of that
                   * algorithm, and the one it got wrong is the one someone checks. The closing panel
                   * states the recorded figures instead.
                   */}
                  {seats.map((seat, index) => {
                    const percentage = watched.shares?.[index]?.percentage;
                    if (!percentage) return null;
                    return (
                      <WizardConfirmRow
                        key={seat.id}
                        label={seat.displayName}
                        value={`${fmt.sharePct(Number(percentage))}%`}
                      />
                    );
                  })}
                </dl>

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

      {stage === 'done' && (
        <WizardSummary
          title={t('pots.share.done.title')}
          rows={(isNavigating ? [] : (pot?.shares ?? [])).map((share) => ({
            id: share.memberId,
            label: share.displayName,
            value: `${fmt.sharePct(Number(share.percentage))}%`,
            note:
              share.value === null || pot === null
                ? t('pots.unvalued')
                : money(share.value, pot.baseCurrency),
          }))}
          lines={[
            t('pots.share.done.baseline', { date: fmt.date(form.getValues('date')) }),
            t('pots.share.done.growth'),
            t('pots.share.done.nextMoney'),
          ]}
          actions={
            potId !== null && (
              <>
                <Button blue asChild>
                  <Link href={sharedPotPath(potId)}>{t('pots.wizard.openShared')}</Link>
                </Button>
                <Button variant="outline" asChild>
                  <Link href={sharedGroupPath(group.id)}>
                    {t('pots.wizard.backToGroup', { group: group.name })}
                  </Link>
                </Button>
              </>
            )
          }
        />
      )}
    </WizardShell>
  );
}
