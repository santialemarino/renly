'use client';

import { useMemo, useRef, useState } from 'react';
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
import { SettlementPlanStep } from '@/app/(protected)/shared/[groupId]/_components/settlement-plan-step';
import {
  previewSettlement,
  recordSettlement,
  recordSettlementWaterfall,
} from '@/app/(protected)/shared/settlement-actions';
import {
  buildSettlementFormSchema,
  type SettlementFormValues,
} from '@/app/(protected)/shared/settlement-form-schema';
import {
  legCrossesCurrency,
  ownLegAccounts,
  planNeedsConfirming,
  selectedSpilloverCurrencies,
  suggestionSide,
  suggestionVoice,
} from '@/app/(protected)/shared/settlement-rules';
import { DatePickerInput } from '@/components/date-picker-input';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/form';
import { FormCombobox } from '@/components/form-combobox';
import { LocaleAmountInput } from '@/components/locale-amount-input';
import type { Account } from '@/lib/api/accounts';
import type { GroupSettlementPlan, GroupSettleSuggestion } from '@/lib/api/group-settlements';
import type { Group } from '@/lib/api/groups';
import { useEntityFormDialog } from '@/lib/hooks/use-entity-form-dialog';
import { todayInTimezone } from '@/lib/utils/dates';

// Form-internal sentinel for "no account named", matching AccountField's: a combobox cannot bind to
// a nullish value cleanly, so the choice round-trips through this and maps back to none on send.
const NO_ACCOUNT = 'none';

interface SettlementFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  group: Group;
  // The suggested payment being recorded. May go null while the close animation plays — the last
  // non-null value is retained internally so the body does not blank out mid-exit.
  suggestion?: GroupSettleSuggestion;
  currency: string;
  // The caller's own accounts. The other party's are not merely absent — the row-level policies hide
  // them, which is the whole reason each side records its own leg.
  accounts: Account[];
  timeZone?: string;
  onSuccess: () => void;
}

/*
 * Recording that one member paid another.
 *
 * The amount is pre-filled with the suggested figure — D28's one tap for the common case — and stays
 * editable, which is what makes the two other cases possible rather than blocked: a partial payment
 * lowers the balance and settlements stay additive until it clears, and an overpayment flips it the
 * other way. Neither is an error; both are what an editable field means.
 *
 * The cash leg is optional and is the CALLER's own. Mark-as-paid with no account named is the
 * default, and the only thing a name-only member's side can ever be. When the caller is on neither
 * side of the payment — which any member may record — no leg is offered at all, because they have
 * none: the two legs belong to two different people and the API refuses a request naming another's.
 *
 * A leg in a different currency from the bucket must say how much moved. There is no stored rate
 * anywhere in the model; the pair of amounts IS the record of the one somebody agreed to.
 */
export function SettlementFormDialog({
  open,
  onOpenChange,
  group,
  suggestion,
  currency,
  accounts,
  timeZone,
  onSuccess,
}: SettlementFormDialogProps) {
  const t = useTranslations('shared');
  const tCommon = useTranslations('common');

  // Retain the suggestion through the close animation, the way ConfirmDialog does — nulling it on
  // close blanks the body, so the dialog visibly empties before it fades.
  const lastSuggestion = useRef(suggestion);
  if (suggestion) lastSuggestion.current = suggestion;
  const lastCurrency = useRef(currency);
  if (currency) lastCurrency.current = currency;
  const shown = suggestion ?? lastSuggestion.current;
  const shownCurrency = currency || lastCurrency.current;

  const today = todayInTimezone(timeZone);
  const mySeatId = useMemo(
    () => group.members.find((member) => member.isSelf)?.id ?? null,
    [group.members],
  );

  // Which of the two legs is the caller's, if either. Derived from the suggestion rather than from a
  // saved row, because nothing has been recorded yet.
  const side = shown ? suggestionSide(shown, mySeatId) : null;

  const eligibleAccounts = useMemo(() => ownLegAccounts(accounts), [accounts]);

  const schema = useMemo(
    () =>
      buildSettlementFormSchema({
        bucketCurrency: shownCurrency,
        requiredMsg: tCommon('form.errors.required'),
        positiveMsg: t('pots.form.mustBePositive'),
        sameMemberMsg: t('settlements.form.sameMember'),
      }),
    [shownCurrency, t, tCommon],
  );

  const toValues = (entity: GroupSettleSuggestion | undefined): SettlementFormValues => ({
    fromMemberId: entity ? String(entity.fromMemberId) : '',
    toMemberId: entity ? String(entity.toMemberId) : '',
    date: today,
    amount: entity?.amount ?? '',
    accountId: NO_ACCOUNT,
    legCurrency: '',
    legAmount: '',
    notes: '',
  });

  const form = useForm<SettlementFormValues>({
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

  const watchedAccountId = useWatch({ control: form.control, name: 'accountId' });
  const watchedLegCurrency = useWatch({ control: form.control, name: 'legCurrency' });

  const namedAccount = watchedAccountId !== NO_ACCOUNT && !!watchedAccountId;
  // Empty rather than undefined so the label below has a string to name; an empty currency
  // crosses nothing, so the two readings stay identical.
  const legCurrency = watchedLegCurrency ?? '';
  const crossCurrency = namedAccount && legCrossesCurrency(legCurrency, shownCurrency);

  /*
   * Selecting an account settles the leg's currency, which is the whole comparison the cross-currency
   * rule makes. Cleared together with the account, so a stale currency can never make the amount
   * field appear for a leg that no longer exists.
   */
  function onAccountChange(value: string) {
    form.setValue('accountId', value);
    const account = eligibleAccounts.find((candidate) => String(candidate.id) === value);
    form.setValue('legCurrency', account?.currency ?? '');
    if (!account || account.currency === shownCurrency) form.setValue('legAmount', '');
  }

  /*
   * The plan the payer is being asked to confirm, or null while they are still filling the form.
   *
   * Held here rather than in the form because it is not a field: it is the server's answer about a
   * form that has already been filled, and it is thrown away the moment the dialog closes or the
   * payer goes back to change the amount.
   */
  const [plan, setPlan] = useState<GroupSettlementPlan | null>(null);
  const [planPending, setPlanPending] = useState(false);

  // Every close, successful or not, drops the plan — reopening on a stale one would offer to move
  // money against balances that have since changed.
  function onDialogOpenChange(next: boolean) {
    if (!next) setPlan(null);
    onOpenChange(next);
  }

  // What both the preview and the write send. The sentinel never leaves the form: an unnamed account
  // is no leg at all.
  function toRequest(values: SettlementFormValues, spilloverCurrencies?: string[]) {
    return {
      fromMemberId: Number(values.fromMemberId),
      toMemberId: Number(values.toMemberId),
      date: values.date,
      amount: values.amount,
      currency: shownCurrency,
      spilloverCurrencies,
      accountId: values.accountId === NO_ACCOUNT ? '' : values.accountId,
      legCurrency: values.legCurrency,
      legAmount: values.legAmount,
      notes: values.notes,
    };
  }

  /*
   * Submitting asks the server where the payment would land BEFORE recording anything.
   *
   * The extra round trip happens on every settlement, including the ordinary ones, and that is the
   * right trade: the alternative is the client deciding whether an overpayment can spill, which needs
   * the other buckets AND a rate, and would be a second implementation of the rule that decides it.
   * When there is nothing to confirm — the common case by far — it records straight through.
   */
  async function onSubmit(values: SettlementFormValues) {
    const preview = await previewSettlement(group.id, toRequest(values), side);
    if (preview.ok && planNeedsConfirming(preview.data)) {
      setPlan(preview.data);
      return;
    }
    await submitWithLifecycle(
      () =>
        recordSettlement(
          group.id,
          shownCurrency,
          { ...values, accountId: values.accountId === NO_ACCOUNT ? '' : values.accountId },
          side,
        ),
      t('settlements.form.success'),
      t('settlements.form.error'),
    );
  }

  // Re-asks the server for a plan over the smaller set. Not recomputed here: unticking a bucket makes
  // the excess flow on to the next one, at rates only the server has.
  async function onTogglePlanBucket(currency: string, selected: boolean) {
    if (!plan) return;
    const next = plan.buckets
      .filter((bucket) => (bucket.currency === currency ? selected : bucket.selected))
      .map((bucket) => bucket.currency);
    setPlanPending(true);
    const preview = await previewSettlement(group.id, toRequest(form.getValues(), next), side);
    setPlanPending(false);
    if (preview.ok) setPlan(preview.data);
  }

  // Records the confirmed plan: several settlements, written together or not at all. The request
  // names which buckets were kept and never how much to put in them, so the server re-allocates.
  async function onConfirmPlan() {
    if (!plan) return;
    await submitWithLifecycle(
      () =>
        recordSettlementWaterfall(
          group.id,
          toRequest(form.getValues(), selectedSpilloverCurrencies(plan)),
          side,
        ),
      t('settlements.form.success'),
      t('settlements.form.error'),
    );
  }

  return (
    <Dialog open={open} onOpenChange={onDialogOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {plan ? t('settlements.plan.title') : t('settlements.form.title')}
          </DialogTitle>
        </DialogHeader>
        <DialogDescription>
          {/*
           * Names the pair and nothing else. The suggested figure is NOT restated here: the amount
           * field below is editable, so a description asserting what was paid would contradict the
           * form the moment somebody records a partial payment.
           */}
          {plan
            ? t('settlements.plan.description')
            : shown
              ? t(`settlements.form.description.${suggestionVoice(shown, mySeatId)}`, {
                  from: shown.fromDisplayName,
                  to: shown.toDisplayName,
                })
              : ''}
        </DialogDescription>

        {plan && (
          <SettlementPlanStep plan={plan} onToggle={onTogglePlanBucket} pending={planPending} />
        )}

        {/*
         * Kept MOUNTED behind the plan rather than unmounted, and that is load-bearing: react-hook-form
         * unregisters a field whose control leaves the DOM and deletes its value, so a form torn down
         * to show the plan would come back to Back with the amount and the account gone.
         */}
        <div className={plan ? 'hidden' : 'contents'}>
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
                  name="amount"
                  render={({ field }) => (
                    <FormItem required className="flex-1 min-w-0">
                      <FormLabel>
                        {t('settlements.form.amount.label', { currency: shownCurrency })}
                      </FormLabel>
                      <FormControl>
                        <LocaleAmountInput
                          {...field}
                          currency={shownCurrency}
                          placeholder={t('settlements.form.amount.placeholder')}
                        />
                      </FormControl>
                      <p className="text-paragraph-xs text-muted-foreground">
                        {t('settlements.form.amount.hint')}
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
                      <FormLabel>{t('settlements.form.date.label')}</FormLabel>
                      <FormControl>
                        <DatePickerInput
                          value={field.value}
                          onChange={field.onChange}
                          placeholder={t('settlements.form.date.placeholder')}
                          maxDate={today}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>

              {/*
               * The caller's own leg, offered only when they are one of the two people. A third member
               * may still record the payment — the API asks only for membership — but they have no
               * account in it to name, and naming somebody else's is refused outright.
               */}
              {side !== null && (
                <>
                  <FormField
                    control={form.control}
                    name="accountId"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>
                          {side === 'outgoing'
                            ? t('settlements.form.account.labelOut')
                            : t('settlements.form.account.labelIn')}
                        </FormLabel>
                        <FormControl>
                          <FormCombobox
                            value={field.value ?? NO_ACCOUNT}
                            onValueChange={onAccountChange}
                            className="w-full"
                            options={[
                              { value: NO_ACCOUNT, label: t('settlements.form.account.none') },
                              ...eligibleAccounts.map((account) => ({
                                // Every currency is offered, so each option names its own: account
                                // names are not unique, and the common same-name pair in two
                                // currencies would otherwise be two identical rows.
                                value: String(account.id),
                                label: `${account.name} · ${account.currency}`,
                              })),
                            ]}
                          />
                        </FormControl>
                        <p className="text-paragraph-xs text-muted-foreground">
                          {t('settlements.form.account.hint')}
                        </p>
                        <FormMessage />
                      </FormItem>
                    )}
                  />

                  {/*
                   * Revealed only across currencies, and required then: no rate is ever stored, so what
                   * moved through the account has to be stated. Within one currency the account moved
                   * exactly what came off the balance, and a different figure is refused rather than
                   * quietly preferred — it would be a bank fee inflating a payment.
                   */}
                  {crossCurrency && (
                    <FormField
                      control={form.control}
                      name="legAmount"
                      render={({ field }) => (
                        <FormItem required>
                          <FormLabel>
                            {t('settlements.form.legAmount.label', { currency: legCurrency })}
                          </FormLabel>
                          <FormControl>
                            <LocaleAmountInput
                              {...field}
                              currency={legCurrency}
                              placeholder={t('settlements.form.legAmount.placeholder')}
                            />
                          </FormControl>
                          <p className="text-paragraph-xs text-muted-foreground">
                            {t('settlements.form.legAmount.hint')}
                          </p>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  )}
                </>
              )}

              <FormField
                control={form.control}
                name="notes"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>{t('settlements.form.notes.label')}</FormLabel>
                    <FormControl>
                      <Input {...field} placeholder={t('settlements.form.notes.placeholder')} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </form>
          </Form>
        </div>

        <DialogFooter>
          {plan ? (
            <>
              {/* Back, not Cancel: the form is still filled in behind this, and going back to change
                  the amount is the reason somebody would decline a plan. */}
              <Button variant="outline" onClick={() => setPlan(null)}>
                {t('settlements.plan.back')}
              </Button>
              <Button
                blue
                onClick={onConfirmPlan}
                disabled={form.formState.isSubmitting || planPending}
              >
                {form.formState.isSubmitting ? t('form.cta.loading') : t('settlements.plan.cta')}
              </Button>
            </>
          ) : (
            <>
              <Button variant="outline" onClick={() => onDialogOpenChange(false)}>
                {t('form.cancel')}
              </Button>
              <Button
                blue
                type="submit"
                form="settlement-form"
                disabled={form.formState.isSubmitting}
              >
                {form.formState.isSubmitting ? t('form.cta.loading') : t('settlements.form.cta')}
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
