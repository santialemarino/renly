'use client';

import { useEffect, useMemo, useState } from 'react';
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
  Textarea,
} from '@repo/ui/components';
import { CurrencyCombobox } from '@/app/(protected)/_components/currency-combobox';
import { EntryScopeField } from '@/app/(protected)/_components/entry-scope-field';
import { EntrySplitRows } from '@/app/(protected)/_components/entry-split-rows';
import { EntryTypeField } from '@/app/(protected)/_components/entry-type-field';
import {
  createSharedIncome,
  getGroupIncomeContext,
  updateSharedIncome,
  type GroupIncomeContext,
} from '@/app/(protected)/shared/shared-income-actions';
import {
  buildSharedIncomeFormSchema,
  NO_SOURCE,
  type SharedIncomeFormValues,
} from '@/app/(protected)/shared/shared-income-form-schema';
import {
  canNameOwnDestination,
  inactiveSeatNames,
  isJointlyHeld,
  ownershipDefaultShares,
  rememberedDestination,
  seatNames,
  wasParticipant,
} from '@/app/(protected)/shared/shared-income-rules';
import { reopenChangedMethod, reopenSplitMethod } from '@/app/(protected)/shared/split-rules';
import { AccountField } from '@/components/account-field';
import { DatePickerInput } from '@/components/date-picker-input';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/form';
import { FormCombobox } from '@/components/form-combobox';
import { LocaleAmountInput } from '@/components/locale-amount-input';
import { StyledHint } from '@/components/styled-hint';
import type { Account } from '@/lib/api/accounts';
import type { Group, GroupMember } from '@/lib/api/groups';
import type { SharedIncome } from '@/lib/api/shared-income';
import type { EntryType } from '@/lib/constants/entries';
import { DEFAULT_SPLIT_METHOD, SPLIT_METHODS } from '@/lib/constants/shared-expenses';
import { DEFAULT_INCOME_DESTINATION, INCOME_DESTINATIONS } from '@/lib/constants/shared-income';
import { toHandover, type IncomeHandover } from '@/lib/entry-handover';
import { useEntityFormDialog } from '@/lib/hooks/use-entity-form-dialog';
import { useFormatters } from '@/lib/i18n/formatters';
import { sortIncomeCategoriesByLabel } from '@/lib/utils/categories';
import { todayInTimezone } from '@/lib/utils/dates';

interface SharedIncomeFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  group: Group;
  // The row being replaced, or undefined to record new income.
  income?: SharedIncome;
  prefill?: IncomeHandover;
  // The caller's OWN accounts. Another member's are not merely absent from this list — the row-level
  // policies hide them entirely, which is why the account field only renders for your own seat.
  accounts?: Account[];
  preferredCurrencies?: string[];
  supportedCurrencies?: string[];
  timeZone?: string;
  // Rendered only when supplied AND recording new income: the scope control that swaps this form for
  // the private one. The hub does not pass it — there is nothing there to swap to.
  scopeGroups?: Group[];
  onScopeChange?: (scope: string, values: IncomeHandover) => void;
  /*
   * The global quick-add's entry-type control, on the same terms as the scope control above: supplied
   * only by the caller that has another form to swap TO, and rendered only while recording a new
   * entry. The group hub does not pass it — there is nothing there to swap to.
   */
  onEntryTypeChange?: (type: EntryType, values: IncomeHandover) => void;
  onSuccess: () => void;
}

/*
 * Recording or replacing a piece of a group's shared income.
 *
 * The form answers three questions, and keeping them apart is what makes one form cover every shape
 * F1 and F2 describe:
 *
 *   1. WHAT arrived — date, amount, currency, category, notes, and the co-owned asset it came from.
 *   2. WHERE it went. Either it stayed joint, in which case it lands in a shared account and the
 *      pot's owners hold it in their own proportions and naming a recipient is refused outright; or it
 *      reached one person, who must be named. Those are genuinely different answers rather than one
 *      field with a null, which is also why the API has no receiver column.
 *   3. WHO gets a share, and in what proportion. The split — which the source asset PRE-FILLS with
 *      that asset's ownership proportions (F1), because rent from a property the group owns 60/40 is
 *      60/40 income unless somebody says otherwise.
 *
 * The account is asked ONLY for the viewer's own seat. That is not a simplification: the API requires
 * a named account to belong to the recipient, and the policies hide every other member's from this
 * caller, so a picker there could only offer accounts that answer 404. Recording that somebody else
 * collected the money is a note that they did.
 *
 * A PUT replaces the whole row rather than patching it, matching the API, because the amount, the
 * method and the participants are one interlocking statement: changing the amount without restating
 * the split would leave exact figures that no longer add up to it.
 */
export function SharedIncomeFormDialog({
  open,
  onOpenChange,
  group,
  income,
  prefill,
  accounts,
  preferredCurrencies,
  supportedCurrencies,
  timeZone,
  scopeGroups,
  onScopeChange,
  onEntryTypeChange,
  onSuccess,
}: SharedIncomeFormDialogProps) {
  const fmt = useFormatters();
  const t = useTranslations('shared');
  const tCommon = useTranslations('common');

  /*
   * The group's shared accounts, its co-owned assets, its agreed default split and its income so far —
   * read when the dialog opens rather than with the page. See getGroupIncomeContext for why this read
   * lives in an actions file. Null until it lands, which is also what stops any default being applied
   * to a form somebody is already typing into.
   */
  const [context, setContext] = useState<GroupIncomeContext | null>(null);
  /*
   * Owners of the chosen source asset who have no row in the split editor, so their share could not be
   * pre-filled. Held rather than derived because it is about the last SELECTION rather than the current
   * form state — re-deriving it would keep the warning on screen after the user divided it themselves.
   */
  const [unreachableOwners, setUnreachableOwners] = useState<string[]>([]);

  /*
   * The loaded context belongs to ONE group, so it is dropped the moment the group changes.
   *
   * Without this the dialog keeps the previous group's accounts, assets and remembered destinations
   * for as long as the new read takes — and on `/income`, where the scope control can point this same
   * instance at a different group, that means offering an account the API would refuse
   * (400 shared_income_destination_scope) and an asset it would refuse too
   * (400 shared_income_source_scope). "Offered then refused" is precisely the experience these rules
   * exist to avoid, and it is the defect PR 5b's last review round found on the expense side.
   */
  useEffect(() => {
    setContext(null);
    setUnreachableOwners([]);
  }, [group.id]);

  const today = todayInTimezone(timeZone);
  const mySeatId = useMemo(
    () => group.members.find((member) => member.isSelf)?.id ?? null,
    [group.members],
  );

  /*
   * The rows the split editor shows: every ACTIVE seat, plus any former seat the saved row already
   * names. New income never offers a former seat, and an old row has to show the people it was
   * actually divided between — otherwise reopening it would silently drop somebody's share.
   */
  const seats = useMemo(() => {
    const named = new Set(income?.splits.map((split) => split.memberId) ?? []);
    return group.members.filter((member) => member.isActive || named.has(member.id));
  }, [group.members, income]);

  const sortedCategories = useMemo(
    () => sortIncomeCategoriesByLabel((key) => tCommon(key), fmt.locale),
    [tCommon, fmt.locale],
  );

  const schema = useMemo(
    () =>
      buildSharedIncomeFormSchema({
        requiredMsg: tCommon('form.errors.required'),
        positiveMsg: t('pots.form.mustBePositive'),
        participantsMsg: t('split.errors.participants'),
        splitTotalMsg: t('split.errors.exact'),
      }),
    [t, tCommon],
  );

  /*
   * Seeds the form from a saved row, or from whatever a swap carried across.
   *
   * The split figures come from the STORED AMOUNTS, which is the only lossless statement of a saved
   * division — see `reopenSplitMethod` for why a percentage split reopens as exact amounts, and
   * `wasParticipant` for why a row that received money without being entitled to any is not a
   * participant.
   */
  const toValues = (entity: SharedIncome | undefined): SharedIncomeFormValues => {
    if (!entity) {
      return {
        /*
         * `||`, not `??`: a handover carries what the user actually TYPED, and the private form
         * starts its date EMPTY — so an untouched date arrives as '', which `??` would keep and which
         * would leave this form with no date at all. Nothing typed falls back to this form's own
         * default, so the same door always opens on the same state.
         */
        date: prefill?.date || today,
        amount: prefill?.amount ?? '',
        currency: prefill?.currency ?? '',
        category: prefill?.category,
        notes: prefill?.notes ?? '',
        splitMethod: DEFAULT_SPLIT_METHOD,
        splits: seats.map((seat) => ({
          memberId: seat.id,
          included: seat.isActive,
          figure: '',
        })),
        destination: DEFAULT_INCOME_DESTINATION,
        sourceInvestmentId: NO_SOURCE,
        receivedByMemberId: mySeatId === null ? '' : String(mySeatId),
        sharedAccountId: '',
        accountId: null,
      };
    }
    const joint = isJointlyHeld(entity);
    const method = reopenSplitMethod(entity);
    const splitsBySeat = new Map(entity.splits.map((split) => [split.memberId, split]));
    return {
      date: entity.date,
      amount: entity.amount,
      currency: entity.currency,
      category: (entity.category ?? undefined) as SharedIncomeFormValues['category'],
      notes: entity.notes ?? '',
      splitMethod: method,
      splits: seats.map((seat) => {
        const split = splitsBySeat.get(seat.id);
        return {
          memberId: seat.id,
          included: split !== undefined && wasParticipant(split),
          figure: method === 'equal' || split === undefined ? '' : split.amount,
        };
      }),
      destination: entity.destination,
      sourceInvestmentId:
        entity.sourceInvestmentId === null ? NO_SOURCE : String(entity.sourceInvestmentId),
      receivedByMemberId: joint ? '' : String(entity.receivedByMemberId),
      sharedAccountId: joint && entity.paidToAccountId ? String(entity.paidToAccountId) : '',
      /*
       * Kept even when the recipient is somebody else, whose account this caller cannot see. The field
       * is not rendered then, so nothing clears it and it round-trips untouched — without which an
       * unrelated edit to a teammate's row would quietly drop the account their money landed in.
       */
      accountId: joint ? null : entity.paidToAccountId,
    };
  };

  const form = useForm<SharedIncomeFormValues>({
    resolver: zodResolver(schema),
    defaultValues: toValues(income),
  });

  const { submitWithLifecycle } = useEntityFormDialog({
    open,
    onOpenChange,
    form,
    entity: income,
    toValues,
    onSuccess,
  });

  const watchedCurrency = useWatch({ control: form.control, name: 'currency' });
  const watchedDestination = useWatch({ control: form.control, name: 'destination' });
  const watchedReceiverId = useWatch({ control: form.control, name: 'receivedByMemberId' });
  const watchedMethod = useWatch({ control: form.control, name: 'splitMethod' });
  const watchedSourceId = useWatch({ control: form.control, name: 'sourceInvestmentId' });
  const watchedSharedAccountId = useWatch({ control: form.control, name: 'sharedAccountId' });
  const watchedSplits = useWatch({ control: form.control, name: 'splits' });

  /*
   * The shared accounts this income could actually have landed in: the group's, in its own currency.
   * The currency match is the API's rule (400 account_currency_mismatch) — these sums carry one
   * amount, so a mismatched link would add a foreign-currency figure straight to the balance.
   */
  const eligibleAccounts = useMemo(
    () =>
      (context?.destinationAccounts ?? []).filter(
        (account) => account.currency === watchedCurrency,
      ),
    [context, watchedCurrency],
  );

  const isJoint = watchedDestination === 'joint';
  const forOwnSeat = canNameOwnDestination(
    watchedReceiverId ? Number(watchedReceiverId) : null,
    mySeatId,
  );
  const selectedSource = useMemo(
    () => (context?.sources ?? []).find((source) => String(source.id) === watchedSourceId) ?? null,
    [context, watchedSourceId],
  );

  // Every seat this request would name — the participants and the recipient. A former one is refused
  // by the API with an answer that carries no error code, so the form says which person it is about.
  const blockedNames = useMemo(() => {
    const named = (watchedSplits ?? [])
      .filter((split) => split.included)
      .map((split) => split.memberId);
    if (!isJoint && watchedReceiverId) named.push(Number(watchedReceiverId));
    return inactiveSeatNames(named, group.members);
  }, [watchedSplits, watchedReceiverId, isJoint, group.members]);

  /*
   * Loads the group's context once per opening. A closed dialog fetches nothing, and a reopened one
   * re-reads: a pot's accounts, its holdings, its ownership and the group's default can all have
   * changed on another page since.
   *
   * The default split method is applied only to NEW income whose form is still untouched. A saved row
   * carries the method it was divided by, and a form somebody has already typed into is theirs —
   * moving the method under them once a late response lands would silently change the division.
   */
  useEffect(() => {
    if (!open) return;
    /*
     * Cleared on every opening, because the form is reset then and the source goes back to "nothing in
     * particular" — a warning naming somebody about an asset the form no longer references is a
     * sentence about nothing on screen. `onSourceChange` clears it too, but only when the user picks a
     * source; reopening does not go through it.
     */
    setUnreachableOwners([]);
    let active = true;
    getGroupIncomeContext(group.id)
      .then((loaded) => {
        if (!active) return;
        setContext(loaded);
        if (!income && !form.formState.isDirty) {
          form.setValue('splitMethod', loaded.defaultSplitMethod);
        }
      })
      .catch(() => {
        if (active) {
          setContext({
            destinationAccounts: [],
            sources: [],
            defaultSplitMethod: DEFAULT_SPLIT_METHOD,
            history: [],
          });
        }
      });
    return () => {
      active = false;
    };
  }, [open, group.id, income, form]);

  /*
   * Keeps the joint half honest as the currency moves.
   *
   * A combobox whose value matches no option silently renders its placeholder, so a shared account
   * left selected after the currency changed would look cleared while still being submitted. And a
   * currency with no shared account at all has no joint branch to be on, so the form falls back to
   * "one person received it" rather than sitting on a destination it cannot name.
   *
   * Gated on the context having ARRIVED, not on the list's length: "not loaded yet" and "this group
   * has no shared account" are the same value and opposite facts, and reading the first as the second
   * silently rewrites a saved JOINT row into a distributed one with no recipient the instant it is
   * opened for an edit. That is the defect the expense form shipped and the browser caught.
   */
  useEffect(() => {
    if (context === null || watchedDestination !== 'joint') return;
    if (eligibleAccounts.length === 0) {
      form.setValue('destination', 'distributed');
      form.setValue('sharedAccountId', '');
      return;
    }
    if (
      watchedSharedAccountId &&
      !eligibleAccounts.some((account) => String(account.id) === watchedSharedAccountId)
    ) {
      form.setValue('sharedAccountId', '');
    }
  }, [context, watchedDestination, eligibleAccounts, watchedSharedAccountId, form]);

  /*
   * F1 and F2 together: picking a source asset divides the income the way that asset is owned, and
   * re-selects the destination this source was last recorded with.
   *
   * Only on NEW income, and only while the form is untouched — the same gate the default split method
   * uses, and for the stronger reason here: rewriting a saved row's split from today's ownership would
   * restate a division the group already agreed on, which is exactly what pinning the proportions at
   * write time exists to prevent.
   *
   * `percentage` rather than exact amounts, because the pot's own figures already sum to exactly 100
   * (its remainder is assigned to the largest holder) while amounts derived from them would round a
   * second time and could miss the total.
   */
  function onSourceChange(value: string) {
    form.setValue('sourceInvestmentId', value);
    setUnreachableOwners([]);
    if (income) return;
    const source = (context?.sources ?? []).find((entry) => String(entry.id) === value) ?? null;
    const remembered = rememberedDestination(
      context?.history ?? [],
      value === NO_SOURCE ? null : Number(value),
    );
    if (remembered !== null) onDestinationChange(remembered);
    if (source === null) return;
    const { shares, missingOwners } = ownershipDefaultShares(
      source.shares,
      seats.map((seat) => seat.id),
    );
    /*
     * An owner with no row in the editor — a member who left the group while still holding units, which
     * the design supports on purpose. The remaining percentages would not reach 100, so the split is
     * left exactly as it was and the form says whose absence stopped it. Anything else hands the user a
     * division the API refuses for a reason they did not choose.
     */
    if (missingOwners.length > 0) {
      setUnreachableOwners(seatNames(missingOwners, group.members));
      return;
    }
    if (shares.size === 0) return;
    form.setValue('splitMethod', 'percentage');
    form.setValue(
      'splits',
      seats.map((seat) => ({
        memberId: seat.id,
        included: shares.has(seat.id),
        figure: shares.get(seat.id) ?? '',
      })),
    );
  }

  /*
   * Clears the other branch's field whenever the destination changes.
   *
   * A shared account and a recipient are answers to different questions, so an id left over from the
   * branch the user just left would be submitted alongside the one they meant — and the API refuses
   * exactly that pairing rather than ignoring it.
   */
  function onDestinationChange(value: string) {
    form.setValue('destination', value as SharedIncomeFormValues['destination']);
    if (value === 'joint') {
      form.setValue('receivedByMemberId', '');
      form.setValue('accountId', null);
      return;
    }
    form.setValue('sharedAccountId', '');
    if (!form.getValues('receivedByMemberId') && mySeatId !== null) {
      form.setValue('receivedByMemberId', String(mySeatId));
    }
  }

  // Clears the account whenever the recipient changes: an account belongs to one person, so an id left
  // over from a different recipient would be submitted as theirs and answer 404.
  function onReceiverChange(value: string) {
    form.setValue('receivedByMemberId', value);
    form.setValue('accountId', null);
  }

  async function onSubmit(values: SharedIncomeFormValues) {
    await submitWithLifecycle(
      () =>
        income
          ? updateSharedIncome(group.id, income.id, values)
          : createSharedIncome(group.id, values),
      income ? t('income.form.updateSuccess') : t('income.form.createSuccess'),
      t('income.form.saveError'),
    );
  }

  const seatOptions = seats
    .filter((seat: GroupMember) => seat.isActive)
    .map((seat) => ({ value: String(seat.id), label: seat.displayName }));

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>
            {income ? t('income.form.titleEdit') : t('income.form.titleCreate')}
          </DialogTitle>
        </DialogHeader>
        <DialogDescription>{t('income.form.description', { group: group.name })}</DialogDescription>

        <Form {...form}>
          <form
            id="shared-income-form"
            className="flex flex-col min-w-0 gap-y-4"
            onSubmit={form.handleSubmit(onSubmit)}
            noValidate
          >
            {/* Which KIND of entry — the quick-add's other swap, on the same create-only terms. */}
            {onEntryTypeChange && !income && (
              <EntryTypeField
                value="income"
                onValueChange={(type) => onEntryTypeChange(type, toHandover(form.getValues()))}
                disabled={form.formState.isSubmitting}
              />
            )}

            {scopeGroups && !income && onScopeChange && (
              <EntryScopeField
                groups={scopeGroups}
                value={String(group.id)}
                hint={tCommon('entryScope.incomeHint')}
                onValueChange={(scope) => onScopeChange(scope, toHandover(form.getValues()))}
                disabled={form.formState.isSubmitting}
              />
            )}

            <div className="flex min-w-0 items-start gap-x-3">
              <FormField
                control={form.control}
                name="date"
                render={({ field }) => (
                  <FormItem required className="flex-1 min-w-0">
                    <FormLabel>{t('income.form.date.label')}</FormLabel>
                    <FormControl>
                      <DatePickerInput
                        value={field.value}
                        onChange={field.onChange}
                        placeholder={t('income.form.date.placeholder')}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="currency"
                render={({ field }) => (
                  <FormItem required className="flex-1 min-w-0">
                    <FormLabel>{t('income.form.currency.label')}</FormLabel>
                    <FormControl>
                      <CurrencyCombobox
                        value={field.value || null}
                        exclude={[]}
                        codes={supportedCurrencies}
                        preferredCurrencies={preferredCurrencies}
                        placeholder={t('income.form.currency.placeholder')}
                        searchPlaceholder={t('income.form.currency.searchPlaceholder')}
                        noResults={t('income.form.currency.noResults')}
                        onChange={field.onChange}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            <div className="flex min-w-0 items-start gap-x-3">
              <FormField
                control={form.control}
                name="amount"
                render={({ field }) => (
                  <FormItem required className="flex-1 min-w-0">
                    <FormLabel>{t('income.form.amount.label')}</FormLabel>
                    <FormControl>
                      <LocaleAmountInput
                        {...field}
                        currency={watchedCurrency || undefined}
                        placeholder={t('income.form.amount.placeholder')}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="category"
                render={({ field }) => (
                  <FormItem className="flex-1 min-w-0">
                    <FormLabel>{t('income.form.category.label')}</FormLabel>
                    <FormControl>
                      <FormCombobox
                        value={field.value ?? ''}
                        onValueChange={field.onChange}
                        placeholder={t('income.form.category.placeholder')}
                        className="w-full"
                        options={sortedCategories.map((category) => ({
                          value: category,
                          label: tCommon(`categories.${category}`),
                        }))}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            {/*
             * F1: where it came from. Offered only when the group's shared money actually holds
             * something — a picker whose only option is "nothing in particular" is a question with no
             * purpose, and every group starts there.
             */}
            {(context?.sources ?? []).length > 0 && (
              <FormField
                control={form.control}
                name="sourceInvestmentId"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>{t('income.form.source.label')}</FormLabel>
                    <FormControl>
                      <FormCombobox
                        value={field.value}
                        onValueChange={onSourceChange}
                        className="w-full"
                        options={[
                          { value: NO_SOURCE, label: t('income.form.source.none') },
                          ...(context?.sources ?? []).map((source) => ({
                            // The pot's name rides along because a group with two pots can hold two
                            // assets with the same name — nothing constrains either to be unique.
                            value: String(source.id),
                            label: source.potName
                              ? `${source.name} · ${source.potName}`
                              : source.name,
                          })),
                        ]}
                      />
                    </FormControl>
                    <p className="text-paragraph-xs text-muted-foreground">
                      {/* Said in the past tense once a source is picked, because by then the split
                          below has already been rewritten and the hint is explaining what happened
                          rather than what would. */}
                      {selectedSource
                        ? t('income.form.source.applied', { asset: selectedSource.name })
                        : t('income.form.source.hint')}
                    </p>
                    <FormMessage />
                  </FormItem>
                )}
              />
            )}

            {/*
             * F2: where it went. Offered as a choice only while the group HAS a shared account in this
             * currency for it to stay joint in — otherwise there is no second answer, and a picker
             * with one option is a question with no purpose.
             */}
            {eligibleAccounts.length > 0 && (
              <FormField
                control={form.control}
                name="destination"
                render={({ field }) => (
                  <FormItem required>
                    <FormLabel>{t('income.form.destination.label')}</FormLabel>
                    <FormControl>
                      <FormCombobox
                        value={field.value}
                        onValueChange={onDestinationChange}
                        className="w-full"
                        options={INCOME_DESTINATIONS.map((destination) => ({
                          value: destination,
                          label: t(`income.form.destination.${destination}`),
                        }))}
                      />
                    </FormControl>
                    <p className="text-paragraph-xs text-muted-foreground">
                      {isJoint
                        ? t('income.form.destination.hintJoint')
                        : t('income.form.destination.hintDistributed')}
                    </p>
                    <FormMessage />
                  </FormItem>
                )}
              />
            )}

            {isJoint ? (
              <FormField
                control={form.control}
                name="sharedAccountId"
                render={({ field }) => (
                  <FormItem required>
                    <FormLabel>{t('income.form.sharedAccount.label')}</FormLabel>
                    <FormControl>
                      <FormCombobox
                        value={field.value ?? ''}
                        onValueChange={field.onChange}
                        className="w-full"
                        placeholder={t('income.form.sharedAccount.placeholder')}
                        emptyText={t('income.form.sharedAccount.empty', {
                          currency: watchedCurrency,
                        })}
                        options={eligibleAccounts.map((account) => ({
                          value: String(account.id),
                          label: account.potName
                            ? `${account.name} · ${account.potName}`
                            : account.name,
                        }))}
                      />
                    </FormControl>
                    <p className="text-paragraph-xs text-muted-foreground">
                      {t('income.form.sharedAccount.hint')}
                    </p>
                    <FormMessage />
                  </FormItem>
                )}
              />
            ) : (
              <FormField
                control={form.control}
                name="receivedByMemberId"
                render={({ field }) => (
                  <FormItem required>
                    <FormLabel>{t('income.form.receiver.label')}</FormLabel>
                    <FormControl>
                      <FormCombobox
                        value={field.value ?? ''}
                        onValueChange={onReceiverChange}
                        options={seatOptions}
                        placeholder={t('income.form.receiver.placeholder')}
                        className="w-full"
                      />
                    </FormControl>
                    <p className="text-paragraph-xs text-muted-foreground">
                      {forOwnSeat
                        ? t('income.form.receiver.hintSelf')
                        : t('income.form.receiver.hintOther')}
                    </p>
                    <FormMessage />
                  </FormItem>
                )}
              />
            )}

            {/*
             * Where it landed, for the viewer's own seat only. An account named here must be the
             * recipient's, and the policies hide everyone else's — so offering this for another member
             * could only produce a 404 naming an account they can genuinely see nowhere.
             */}
            {!isJoint && forOwnSeat && (
              <AccountField
                control={form.control}
                setValue={form.setValue}
                accounts={accounts ?? []}
                currency={watchedCurrency || undefined}
                label={t('income.form.account.label')}
                hint={t('income.form.account.hint')}
                name="accountId"
              />
            )}

            <FormField
              control={form.control}
              name="splitMethod"
              render={({ field }) => (
                <FormItem required>
                  <FormLabel>{t('income.form.splitMethod.label')}</FormLabel>
                  <FormControl>
                    <FormCombobox
                      value={field.value}
                      onValueChange={field.onChange}
                      className="w-full"
                      options={SPLIT_METHODS.map((method) => ({
                        value: method,
                        label: t(`split.methods.${method}`),
                      }))}
                    />
                  </FormControl>
                  {/* Said only when reopening actually changed the method, so it explains a real
                      difference the user can see rather than describing the form in general. */}
                  {income && reopenChangedMethod(income) && watchedMethod === 'exact' && (
                    <p className="text-paragraph-xs text-muted-foreground">
                      {t('income.form.splitMethod.reopenedAsExact')}
                    </p>
                  )}
                  <FormMessage />
                </FormItem>
              )}
            />

            <EntrySplitRows
              control={form.control}
              seats={seats}
              currency={watchedCurrency}
              participantsLabel={t('income.split.participants.label')}
              showTotalError={form.formState.isSubmitted}
            />

            {unreachableOwners.length > 0 && (
              <StyledHint variant="warning">
                {t('income.form.source.ownerNotInGroup', {
                  count: unreachableOwners.length,
                  names: fmt.list(unreachableOwners),
                })}
              </StyledHint>
            )}

            {blockedNames.length > 0 && (
              <StyledHint variant="warning">
                {t('income.form.formerSeats', {
                  count: blockedNames.length,
                  names: fmt.list(blockedNames),
                })}
              </StyledHint>
            )}

            <FormField
              control={form.control}
              name="notes"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>{t('income.form.notes.label')}</FormLabel>
                  <FormControl>
                    <Textarea {...field} placeholder={t('income.form.notes.placeholder')} />
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
            form="shared-income-form"
            disabled={form.formState.isSubmitting || blockedNames.length > 0}
          >
            {form.formState.isSubmitting ? t('form.cta.loading') : t('income.form.cta')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
