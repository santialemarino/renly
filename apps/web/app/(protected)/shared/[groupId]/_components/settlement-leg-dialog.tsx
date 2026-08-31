'use client';

import { useMemo, useRef } from 'react';
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
} from '@repo/ui/components';
import { setSettlementLeg } from '@/app/(protected)/shared/settlement-actions';
import {
  buildSettlementLegFormSchema,
  type SettlementLegFormValues,
} from '@/app/(protected)/shared/settlement-form-schema';
import {
  legCrossesCurrency,
  ownLegAccountId,
  ownLegAccounts,
  ownLegAmount,
  ownSettlementSide,
} from '@/app/(protected)/shared/settlement-rules';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/form';
import { FormCombobox } from '@/components/form-combobox';
import { LocaleAmountInput } from '@/components/locale-amount-input';
import type { Account } from '@/lib/api/accounts';
import type { GroupSettlement } from '@/lib/api/group-settlements';
import { useEntityFormDialog } from '@/lib/hooks/use-entity-form-dialog';
import { useFormatters } from '@/lib/i18n/formatters';

// Form-internal sentinel for "no account named" — the same round-trip AccountField makes, because a
// combobox cannot bind to a nullish value cleanly. Selecting it CLEARS the leg rather than leaving it.
const NO_ACCOUNT = 'none';

interface SettlementLegDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  groupId: number;
  // The settlement whose leg is being attached. May go null while the close animation plays.
  settlement?: GroupSettlement;
  mySeatId: number | null;
  accounts: Account[];
  onSuccess: () => void;
}

/*
 * Which of the caller's own accounts a settlement moved through.
 *
 * It is a dialog of its own because the leg is the one part of a shared settlement row that only its
 * owner can state. A settlement is a single record both parties see, but "which of MY accounts this
 * went through" is a fact only I have — and only I can even see the account, since the row-level
 * policies hide everyone else's. So each side attaches theirs whenever they get to it: the payer
 * usually while recording the payment, the payee at the moment they confirm receiving it.
 *
 * Without it a payee's own balance would stay wrong for a payment they really received, with no way
 * to fix it — which is exactly the case that put this endpoint in the API.
 *
 * Available on a confirmed settlement too, unlike deletion. What confirmation vouches for is the
 * amount and the fact of the payment, and neither changes here.
 */
export function SettlementLegDialog({
  open,
  onOpenChange,
  groupId,
  settlement,
  mySeatId,
  accounts,
  onSuccess,
}: SettlementLegDialogProps) {
  const fmt = useFormatters();
  const t = useTranslations('shared');
  const tCommon = useTranslations('common');

  const lastSettlement = useRef(settlement);
  if (settlement) lastSettlement.current = settlement;
  const shown = settlement ?? lastSettlement.current;

  const side = shown ? ownSettlementSide(shown, mySeatId) : null;
  const bucketCurrency = shown?.currency ?? '';
  const storedAccountId = shown ? ownLegAccountId(shown, mySeatId) : null;

  /*
   * The accounts the picker OFFERS: the caller's own, active. An archived one is not somewhere to
   * route money, even though the API would take it.
   *
   * The already-attached account is appended when it is not among them, and that is load-bearing
   * rather than tidy: a combobox whose value matches no option silently renders its placeholder, so
   * an archived leg would read as cleared while the form still held its id — and saving would then
   * either resubmit it invisibly or, worse, look like it had removed something it had not.
   */
  const offerableAccounts = useMemo(() => {
    const active = ownLegAccounts(accounts);
    const stored = accounts.find((candidate) => candidate.id === storedAccountId);
    return stored && !active.some((candidate) => candidate.id === stored.id)
      ? [...active, stored]
      : active;
  }, [accounts, storedAccountId]);

  const schema = useMemo(
    () =>
      buildSettlementLegFormSchema({
        bucketCurrency,
        requiredMsg: tCommon('form.errors.required'),
      }),
    [bucketCurrency, tCommon],
  );

  /*
   * Seeds from whichever leg is the caller's — never the other side's, which they may not write and
   * whose account they cannot see. `ownLegAmount` is null within one currency by design: the account
   * moved exactly what came off the bucket, so there is no second figure to show.
   */
  const toValues = (entity: GroupSettlement | undefined): SettlementLegFormValues => {
    const accountId = entity ? ownLegAccountId(entity, mySeatId) : null;
    const account = offerableAccounts.find((candidate) => candidate.id === accountId);
    return {
      accountId: accountId === null ? NO_ACCOUNT : String(accountId),
      legCurrency: account?.currency ?? '',
      legAmount: (entity ? ownLegAmount(entity, mySeatId) : null) ?? '',
    };
  };

  const form = useForm<SettlementLegFormValues>({
    resolver: zodResolver(schema),
    defaultValues: toValues(settlement),
  });

  const { submitWithLifecycle } = useEntityFormDialog({
    open,
    onOpenChange,
    form,
    entity: settlement,
    toValues,
    onSuccess,
  });

  const watchedAccountId = useWatch({ control: form.control, name: 'accountId' });
  const watchedLegCurrency = useWatch({ control: form.control, name: 'legCurrency' });

  const namedAccount = watchedAccountId !== NO_ACCOUNT && !!watchedAccountId;
  // Empty rather than undefined so the label below has a string to name; an empty currency
  // crosses nothing, so the two readings stay identical.
  const legCurrency = watchedLegCurrency ?? '';
  const crossCurrency = namedAccount && legCrossesCurrency(legCurrency, bucketCurrency);

  function onAccountChange(value: string) {
    form.setValue('accountId', value);
    const account = offerableAccounts.find((candidate) => String(candidate.id) === value);
    form.setValue('legCurrency', account?.currency ?? '');
    if (!account || account.currency === bucketCurrency) form.setValue('legAmount', '');
  }

  async function onSubmit(values: SettlementLegFormValues) {
    if (!shown) return;
    await submitWithLifecycle(
      () =>
        setSettlementLeg(groupId, shown.id, bucketCurrency, {
          ...values,
          accountId: values.accountId === NO_ACCOUNT ? '' : values.accountId,
        }),
      t('settlements.leg.success'),
      t('settlements.leg.error'),
    );
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('settlements.leg.title')}</DialogTitle>
        </DialogHeader>
        <DialogDescription>
          {shown
            ? t('settlements.leg.description', {
                amount: fmt.amount(shown.amount, shown.currency),
                currency: shown.currency,
                from: shown.fromDisplayName,
                to: shown.toDisplayName,
              })
            : ''}
        </DialogDescription>

        <Form {...form}>
          <form
            id="settlement-leg-form"
            className="flex flex-col min-w-0 gap-y-4"
            onSubmit={form.handleSubmit(onSubmit)}
            noValidate
          >
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
                        { value: NO_ACCOUNT, label: t('settlements.leg.clear') },
                        ...offerableAccounts.map((account) => ({
                          value: String(account.id),
                          label: account.isActive
                            ? `${account.name} · ${account.currency}`
                            : tCommon('accountField.archived', {
                                name: `${account.name} · ${account.currency}`,
                              }),
                        })),
                      ]}
                    />
                  </FormControl>
                  <p className="text-paragraph-xs text-muted-foreground">
                    {t('settlements.leg.hint')}
                  </p>
                  <FormMessage />
                </FormItem>
              )}
            />

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
          </form>
        </Form>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t('form.cancel')}
          </Button>
          <Button
            blue
            type="submit"
            form="settlement-leg-form"
            disabled={form.formState.isSubmitting}
          >
            {form.formState.isSubmitting ? t('form.cta.loading') : t('settlements.leg.cta')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
