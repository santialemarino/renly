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
import {
  ExpenseScopeField,
  toHandover,
  type ExpenseHandover,
} from '@/app/(protected)/_components/expense-scope-field';
import { ExpenseSplitRows } from '@/app/(protected)/_components/expense-split-rows';
import {
  createSharedExpense,
  getGroupExpenseContext,
  updateSharedExpense,
  type GroupExpenseContext,
} from '@/app/(protected)/shared/shared-expense-actions';
import {
  buildSharedExpenseFormSchema,
  type SharedExpenseFormValues,
} from '@/app/(protected)/shared/shared-expense-form-schema';
import {
  canNameOwnInstrument,
  inactiveSeatNames,
  isJointlyFunded,
  reopenChangedMethod,
  reopenSplitMethod,
  wasParticipant,
} from '@/app/(protected)/shared/shared-expense-rules';
import { AccountField } from '@/components/account-field';
import { DatePickerInput } from '@/components/date-picker-input';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/form';
import { FormCombobox } from '@/components/form-combobox';
import { LocaleAmountInput } from '@/components/locale-amount-input';
import { PaymentMethodFields } from '@/components/payment-method-fields';
import { StyledHint } from '@/components/styled-hint';
import type { Account } from '@/lib/api/accounts';
import type { CreditCard } from '@/lib/api/credit-cards';
import type { Group, GroupMember } from '@/lib/api/groups';
import type { SharedExpense } from '@/lib/api/shared-expenses';
import { DEFAULT_SPLIT_METHOD, SPLIT_METHODS } from '@/lib/constants/shared-expenses';
import { useEntityFormDialog } from '@/lib/hooks/use-entity-form-dialog';
import { useFormatters } from '@/lib/i18n/formatters';
import { sortExpenseCategoriesByLabel } from '@/lib/utils/categories';
import { todayInTimezone } from '@/lib/utils/dates';

interface SharedExpenseFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  group: Group;
  // The expense being replaced, or undefined to record a new one.
  expense?: SharedExpense;
  prefill?: ExpenseHandover;
  // The caller's OWN accounts. Another member's are not merely absent from this list — the row-level
  // policies hide them entirely, which is why the funding block only ever renders for your own seat.
  accounts?: Account[];
  creditCards?: CreditCard[];
  preferredCurrencies?: string[];
  supportedCurrencies?: string[];
  timeZone?: string;
  // Rendered only when supplied AND recording a new expense: the scope control that swaps this form
  // for the private one. The hub does not pass it — there is nothing there to swap to.
  scopeGroups?: Group[];
  onScopeChange?: (scope: string, values: ExpenseHandover) => void;
  onSuccess: () => void;
}

/*
 * Recording or replacing one of a group's shared expenses.
 *
 * The form answers three questions, and keeping them apart is what makes one form cover every case
 * F3 describes:
 *
 *   1. WHAT was spent — date, amount, currency, category, notes. Ordinary expense fields.
 *   2. WHO fronted it. Either joint money, in which case the pot's owners fronted it in their own
 *      proportions and naming a payer is refused outright; or one member, who must be named. Those
 *      are genuinely different answers rather than one field with a null, which is also why the API
 *      has no payer column.
 *   3. WHO was in on it, and in what proportion. The split.
 *
 * The instrument — a payment method, a card, an account — is asked ONLY for the viewer's own seat.
 * That is not a simplification: the API requires a named card or account to belong to the payer, and
 * the policies hide every other member's from this caller, so a picker there could only offer
 * accounts that answer 404. Recording that somebody else paid is a note that they did.
 *
 * A PUT replaces the whole expense rather than patching it, matching the API, because the amount, the
 * method and the participants are one interlocking statement: changing the amount without restating
 * the split would leave exact figures that no longer add up to it.
 */
export function SharedExpenseFormDialog({
  open,
  onOpenChange,
  group,
  expense,
  prefill,
  accounts,
  creditCards,
  preferredCurrencies,
  supportedCurrencies,
  timeZone,
  scopeGroups,
  onScopeChange,
  onSuccess,
}: SharedExpenseFormDialogProps) {
  const fmt = useFormatters();
  const t = useTranslations('shared');
  const tCommon = useTranslations('common');

  /*
   * The group's shared accounts and its agreed default split, read when the dialog opens rather than
   * with the page — see getGroupExpenseContext for why this read lives in an actions file. Null
   * until it lands, which is also what stops the default being applied to a form somebody is already
   * typing into.
   */
  const [context, setContext] = useState<GroupExpenseContext | null>(null);

  /*
   * The loaded context belongs to ONE group, so it is dropped the moment the group changes.
   *
   * Without this the dialog keeps the previous group's shared accounts and default split for as long
   * as the new read takes — and on `/expenses`, where the scope control can point this same instance
   * at a different group, that means offering an account the API would refuse
   * (400 shared_expense_funding_scope). "Offered then refused" is precisely the experience these
   * rules exist to avoid. Re-opening on the SAME group deliberately keeps the last answer rather than
   * blanking the picker; the read below refreshes it either way.
   */
  useEffect(() => {
    setContext(null);
  }, [group.id]);

  const today = todayInTimezone(timeZone);
  const mySeatId = useMemo(
    () => group.members.find((member) => member.isSelf)?.id ?? null,
    [group.members],
  );

  /*
   * The rows the split editor shows: every ACTIVE seat, plus any former seat the saved expense
   * already names. A new expense never offers a former seat, and an old one has to show the people
   * it was actually divided between — otherwise reopening it would silently drop somebody's share.
   */
  const seats = useMemo(() => {
    const named = new Set(expense?.splits.map((split) => split.memberId) ?? []);
    return group.members.filter((member) => member.isActive || named.has(member.id));
  }, [group.members, expense]);

  const sortedCategories = useMemo(
    () => sortExpenseCategoriesByLabel((key) => tCommon(key), fmt.locale),
    [tCommon, fmt.locale],
  );

  const schema = useMemo(
    () =>
      buildSharedExpenseFormSchema({
        requiredMsg: tCommon('form.errors.required'),
        positiveMsg: t('pots.form.mustBePositive'),
        participantsMsg: t('expenses.split.errors.participants'),
        splitTotalMsg: t('expenses.split.errors.exact'),
      }),
    [t, tCommon],
  );

  /*
   * Seeds the form from a saved expense, or from whatever a swap carried across.
   *
   * The split figures come from the STORED AMOUNTS, which is the only lossless statement of a saved
   * division — see `reopenSplitMethod` for why a percentage split reopens as exact amounts, and
   * `wasParticipant` for why a row that fronted money without consuming any is not a participant.
   */
  const toValues = (entity: SharedExpense | undefined): SharedExpenseFormValues => {
    if (!entity) {
      return {
        /*
         * `||`, not `??`: a handover carries what the user actually TYPED, and the private form
         * starts its date EMPTY — so an untouched date arrives as '', which `??` would keep and
         * which would leave this form with no date at all. Nothing typed falls back to this form's
         * own default, so the same door always opens on the same state.
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
        fundingSource: 'member',
        payerMemberId: mySeatId === null ? '' : String(mySeatId),
        sharedAccountId: '',
        paymentMethod: undefined,
        creditCardId: undefined,
        accountId: null,
      };
    }
    const joint = isJointlyFunded(entity);
    const method = reopenSplitMethod(entity);
    const splitsBySeat = new Map(entity.splits.map((split) => [split.memberId, split]));
    return {
      date: entity.date,
      amount: entity.amount,
      currency: entity.currency,
      category: (entity.category ?? undefined) as SharedExpenseFormValues['category'],
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
      fundingSource: joint ? 'joint' : 'member',
      payerMemberId: joint ? '' : String(entity.payerMemberId),
      sharedAccountId: joint && entity.paidFromAccountId ? String(entity.paidFromAccountId) : '',
      paymentMethod: (entity.paymentMethod ??
        undefined) as SharedExpenseFormValues['paymentMethod'],
      creditCardId: entity.creditCardId ?? undefined,
      /*
       * Kept even when the payer is somebody else, whose account this caller cannot see. The field is
       * not rendered then, so nothing clears it and it round-trips untouched — without which an
       * unrelated edit to a teammate's expense would quietly drop the account their money left.
       */
      accountId: joint ? null : entity.paidFromAccountId,
    };
  };

  const form = useForm<SharedExpenseFormValues>({
    resolver: zodResolver(schema),
    defaultValues: toValues(expense),
  });

  const { submitWithLifecycle } = useEntityFormDialog({
    open,
    onOpenChange,
    form,
    entity: expense,
    toValues,
    onSuccess,
  });

  const watchedCurrency = useWatch({ control: form.control, name: 'currency' });
  const watchedFunding = useWatch({ control: form.control, name: 'fundingSource' });
  const watchedPayerId = useWatch({ control: form.control, name: 'payerMemberId' });
  const watchedMethod = useWatch({ control: form.control, name: 'splitMethod' });
  const watchedPaymentMethod = useWatch({ control: form.control, name: 'paymentMethod' });
  const watchedSharedAccountId = useWatch({ control: form.control, name: 'sharedAccountId' });
  const watchedSplits = useWatch({ control: form.control, name: 'splits' });

  /*
   * The shared accounts this expense could actually be paid from: the group's, in the expense's own
   * currency. The currency match is the API's rule (400 account_currency_mismatch) — these sums carry
   * one amount, so a mismatched link would take a foreign-currency figure straight off the balance.
   */
  const eligibleFunding = useMemo(
    () =>
      (context?.fundingAccounts ?? []).filter((account) => account.currency === watchedCurrency),
    [context, watchedCurrency],
  );

  const forOwnSeat = canNameOwnInstrument(watchedPayerId ? Number(watchedPayerId) : null, mySeatId);
  const isJoint = watchedFunding === 'joint';

  // Every seat this request would name — the participants and the payer. A former one is refused by
  // the API with an answer that carries no error code, so the form says which person it is about.
  const blockedNames = useMemo(() => {
    const named = (watchedSplits ?? [])
      .filter((split) => split.included)
      .map((split) => split.memberId);
    if (!isJoint && watchedPayerId) named.push(Number(watchedPayerId));
    return inactiveSeatNames(named, group.members);
  }, [watchedSplits, watchedPayerId, isJoint, group.members]);

  /*
   * Loads the group's context once per opening. A closed dialog fetches nothing, and a reopened one
   * re-reads: a pot's accounts and the group's default can both have changed on another page since.
   *
   * The default split is applied only to a NEW expense whose form is still untouched. A saved one
   * carries the method it was divided by, and a form somebody has already typed into is theirs —
   * moving the method under them once a late response lands would silently change the division.
   */
  useEffect(() => {
    if (!open) return;
    let active = true;
    getGroupExpenseContext(group.id)
      .then((loaded) => {
        if (!active) return;
        setContext(loaded);
        if (!expense && !form.formState.isDirty) {
          form.setValue('splitMethod', loaded.defaultSplitMethod);
        }
      })
      .catch(() => {
        if (active) setContext({ fundingAccounts: [], defaultSplitMethod: DEFAULT_SPLIT_METHOD });
      });
    return () => {
      active = false;
    };
  }, [open, group.id, expense, form]);

  /*
   * Keeps the joint-funding half honest as the currency moves.
   *
   * A combobox whose value matches no option silently renders its placeholder, so a shared account
   * left selected after the currency changed would look cleared while still being submitted. And a
   * currency with no shared account at all has no joint branch to be on, so the form falls back to
   * "somebody paid" rather than sitting on a source it cannot name.
   */
  useEffect(() => {
    // Nothing is decided until the group's accounts have actually arrived. Without this the effect
    // reads "not loaded yet" as "this group has no shared account" and quietly rewrites a saved
    // JOINT expense into a member-funded one with no payer, the instant it is opened for an edit.
    if (context === null || watchedFunding !== 'joint') return;
    if (eligibleFunding.length === 0) {
      form.setValue('fundingSource', 'member');
      form.setValue('sharedAccountId', '');
      return;
    }
    if (
      watchedSharedAccountId &&
      !eligibleFunding.some((account) => String(account.id) === watchedSharedAccountId)
    ) {
      form.setValue('sharedAccountId', '');
    }
  }, [context, watchedFunding, eligibleFunding, watchedSharedAccountId, form]);

  /*
   * Clears the instrument whenever the funding shape changes.
   *
   * A card or an account belongs to one person, so an id left over from a different payer would be
   * submitted as theirs and answer 404 — and on the joint branch the API refuses an instrument
   * outright, because the shared account IS how the money moved.
   */
  function onPayerChange(value: string) {
    form.setValue('payerMemberId', value);
    form.setValue('paymentMethod', undefined);
    form.setValue('creditCardId', undefined);
    form.setValue('accountId', null);
  }

  function onFundingSourceChange(value: string) {
    form.setValue('fundingSource', value as SharedExpenseFormValues['fundingSource']);
    if (value === 'joint') {
      form.setValue('payerMemberId', '');
      form.setValue('paymentMethod', undefined);
      form.setValue('creditCardId', undefined);
      form.setValue('accountId', null);
      return;
    }
    form.setValue('sharedAccountId', '');
    if (!form.getValues('payerMemberId') && mySeatId !== null) {
      form.setValue('payerMemberId', String(mySeatId));
    }
  }

  async function onSubmit(values: SharedExpenseFormValues) {
    await submitWithLifecycle(
      () =>
        expense
          ? updateSharedExpense(group.id, expense.id, values)
          : createSharedExpense(group.id, values),
      expense ? t('expenses.form.updateSuccess') : t('expenses.form.createSuccess'),
      t('expenses.form.saveError'),
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
            {expense ? t('expenses.form.titleEdit') : t('expenses.form.titleCreate')}
          </DialogTitle>
        </DialogHeader>
        <DialogDescription>
          {t('expenses.form.description', { group: group.name })}
        </DialogDescription>

        <Form {...form}>
          <form
            id="shared-expense-form"
            className="flex flex-col min-w-0 gap-y-4"
            onSubmit={form.handleSubmit(onSubmit)}
            noValidate
          >
            {scopeGroups && !expense && onScopeChange && (
              <ExpenseScopeField
                groups={scopeGroups}
                value={String(group.id)}
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
                    <FormLabel>{t('expenses.form.date.label')}</FormLabel>
                    <FormControl>
                      <DatePickerInput
                        value={field.value}
                        onChange={field.onChange}
                        placeholder={t('expenses.form.date.placeholder')}
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
                    <FormLabel>{t('expenses.form.currency.label')}</FormLabel>
                    <FormControl>
                      <CurrencyCombobox
                        value={field.value || null}
                        exclude={[]}
                        codes={supportedCurrencies}
                        preferredCurrencies={preferredCurrencies}
                        placeholder={t('expenses.form.currency.placeholder')}
                        searchPlaceholder={t('expenses.form.currency.searchPlaceholder')}
                        noResults={t('expenses.form.currency.noResults')}
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
                    <FormLabel>{t('expenses.form.amount.label')}</FormLabel>
                    <FormControl>
                      <LocaleAmountInput
                        {...field}
                        currency={watchedCurrency || undefined}
                        placeholder={t('expenses.form.amount.placeholder')}
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
                    <FormLabel>{t('expenses.form.category.label')}</FormLabel>
                    <FormControl>
                      <FormCombobox
                        value={field.value ?? ''}
                        onValueChange={field.onChange}
                        placeholder={t('expenses.form.category.placeholder')}
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
             * Who fronted it. Offered as a choice only while the group HAS a shared account in this
             * currency to choose — otherwise there is no second answer, and a picker with one option
             * is a question with no purpose.
             */}
            {eligibleFunding.length > 0 && (
              <FormField
                control={form.control}
                name="fundingSource"
                render={({ field }) => (
                  <FormItem required>
                    <FormLabel>{t('expenses.form.funding.label')}</FormLabel>
                    <FormControl>
                      <FormCombobox
                        value={field.value}
                        onValueChange={onFundingSourceChange}
                        className="w-full"
                        options={[
                          { value: 'member', label: t('expenses.form.funding.member') },
                          { value: 'joint', label: t('expenses.form.funding.joint') },
                        ]}
                      />
                    </FormControl>
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
                    <FormLabel>{t('expenses.form.sharedAccount.label')}</FormLabel>
                    <FormControl>
                      <FormCombobox
                        value={field.value ?? ''}
                        onValueChange={field.onChange}
                        className="w-full"
                        placeholder={t('expenses.form.sharedAccount.placeholder')}
                        emptyText={t('expenses.form.sharedAccount.empty', {
                          currency: watchedCurrency,
                        })}
                        options={eligibleFunding.map((account) => ({
                          // The pot's name rides along because a group with two pots can hold two
                          // accounts with the same name — nothing constrains either to be unique.
                          value: String(account.id),
                          label: account.potName
                            ? `${account.name} · ${account.potName}`
                            : account.name,
                        }))}
                      />
                    </FormControl>
                    <p className="text-paragraph-xs text-muted-foreground">
                      {t('expenses.form.sharedAccount.hint')}
                    </p>
                    <FormMessage />
                  </FormItem>
                )}
              />
            ) : (
              <FormField
                control={form.control}
                name="payerMemberId"
                render={({ field }) => (
                  <FormItem required>
                    <FormLabel>{t('expenses.form.payer.label')}</FormLabel>
                    <FormControl>
                      <FormCombobox
                        value={field.value ?? ''}
                        onValueChange={onPayerChange}
                        options={seatOptions}
                        placeholder={t('expenses.form.payer.placeholder')}
                        className="w-full"
                      />
                    </FormControl>
                    <p className="text-paragraph-xs text-muted-foreground">
                      {forOwnSeat
                        ? t('expenses.form.payer.hintSelf')
                        : t('expenses.form.payer.hintOther')}
                    </p>
                    <FormMessage />
                  </FormItem>
                )}
              />
            )}

            {/*
             * The instrument, for the viewer's own seat only. A card or account named here must be
             * the payer's, and the policies hide everyone else's — so offering these for another
             * member could only produce a 404 naming an account they can genuinely see nowhere.
             */}
            {!isJoint && forOwnSeat && (
              <>
                <PaymentMethodFields
                  control={form.control}
                  setValue={form.setValue}
                  creditCards={creditCards}
                  preferredCurrencies={preferredCurrencies}
                />
                {/* A card charge raises the card's liability now and only draws cash later at
                    settlement, so it never also links an account. */}
                {watchedPaymentMethod !== 'credit_card' && (
                  <AccountField
                    control={form.control}
                    setValue={form.setValue}
                    accounts={accounts ?? []}
                    currency={watchedCurrency || undefined}
                    label={t('expenses.form.account.label')}
                    hint={t('expenses.form.account.hint')}
                    name="accountId"
                  />
                )}
              </>
            )}

            <FormField
              control={form.control}
              name="splitMethod"
              render={({ field }) => (
                <FormItem required>
                  <FormLabel>{t('expenses.form.splitMethod.label')}</FormLabel>
                  <FormControl>
                    <FormCombobox
                      value={field.value}
                      onValueChange={field.onChange}
                      className="w-full"
                      options={SPLIT_METHODS.map((method) => ({
                        value: method,
                        label: t(`expenses.split.methods.${method}`),
                      }))}
                    />
                  </FormControl>
                  {/* Said only when reopening actually changed the method, so it explains a real
                      difference the user can see rather than describing the form in general. */}
                  {expense && reopenChangedMethod(expense) && watchedMethod === 'exact' && (
                    <p className="text-paragraph-xs text-muted-foreground">
                      {t('expenses.form.splitMethod.reopenedAsExact')}
                    </p>
                  )}
                  <FormMessage />
                </FormItem>
              )}
            />

            <ExpenseSplitRows
              form={form}
              seats={seats}
              currency={watchedCurrency}
              showTotalError={form.formState.isSubmitted}
            />

            {blockedNames.length > 0 && (
              <StyledHint variant="warning">
                {t('expenses.form.formerSeats', {
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
                  <FormLabel>{t('expenses.form.notes.label')}</FormLabel>
                  <FormControl>
                    <Textarea {...field} placeholder={t('expenses.form.notes.placeholder')} />
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
            form="shared-expense-form"
            disabled={form.formState.isSubmitting || blockedNames.length > 0}
          >
            {form.formState.isSubmitting ? t('form.cta.loading') : t('expenses.form.cta')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
