'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { AnimatePresence, motion } from 'motion/react';
import { useTranslations } from 'next-intl';
import { useWatch, type Control, type FieldValues, type UseFormSetValue } from 'react-hook-form';

import { Button, Tooltip, TooltipContent, TooltipTrigger } from '@repo/ui/components';
import { CreditCardFormDialog } from '@/app/(protected)/_components/credit-card-form-dialog';
import { FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/form';
import { FormCombobox } from '@/components/form-combobox';
import type { CreditCard } from '@/lib/api/credit-cards';
import { ANIMATION_DEFAULT } from '@/lib/constants/animations';
import { PAYMENT_METHODS, type PaymentMethod } from '@/lib/constants/categories';

// Minimal form shape this component operates on. Every embedding form schema must declare
// both keys with these exact types (the four entry/plan form schemas do, via PAYMENT_METHODS).
export type PaymentMethodFormValues = {
  paymentMethod?: PaymentMethod;
  creditCardId?: number;
};

interface PaymentMethodFieldsProps<T extends PaymentMethodFormValues & FieldValues> {
  control: Control<T>;
  setValue: UseFormSetValue<T>;
  creditCards?: CreditCard[];
  preferredCurrencies?: string[];
  // Locked-plan support (installments): disables both selects and, when disabledTooltip is
  // set, wraps them in the same tooltip pattern the installment dialog uses today.
  disabled?: boolean;
  disabledTooltip?: string;
}

// Wraps a control in the locked-tooltip pattern only when a tooltip string is provided.
function MaybeLockedTooltip({
  tooltip,
  show,
  children,
}: {
  tooltip?: string;
  show: boolean;
  children: React.ReactNode;
}) {
  if (!tooltip) return <>{children}</>;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <div>{children}</div>
      </TooltipTrigger>
      {show && <TooltipContent>{tooltip}</TooltipContent>}
    </Tooltip>
  );
}

export function PaymentMethodFields<T extends PaymentMethodFormValues & FieldValues>({
  control: controlProp,
  setValue: setValueProp,
  creditCards,
  preferredCurrencies,
  disabled = false,
  disabledTooltip,
}: PaymentMethodFieldsProps<T>) {
  /*
   * Narrow the caller's form typing to the minimal shape. Safe because T extends
   * PaymentMethodFormValues and this component only reads/writes those two fields.
   * (RHF's Control/SetValue generics are invariant, so a direct assignment won't compile.)
   */
  const control = controlProp as unknown as Control<PaymentMethodFormValues>;
  const setValue = setValueProp as unknown as UseFormSetValue<PaymentMethodFormValues>;

  const t = useTranslations('common.paymentMethod');
  const router = useRouter();
  const [cardDialogOpen, setCardDialogOpen] = useState(false);
  // Cards created inline from this form, so the new card is selectable immediately without
  // waiting for the parent page's server refetch.
  const [inlineCards, setInlineCards] = useState<CreditCard[]>([]);
  const watchedPaymentMethod = useWatch({ control, name: 'paymentMethod' });
  const watchedCreditCardId = useWatch({ control, name: 'creditCardId' });

  // Server-provided cards merged with inline-created ones (deduped by id — after the
  // router.refresh() fired on create, the server prop includes the new card too).
  const allCards = [
    ...(creditCards ?? []),
    ...inlineCards.filter((c) => !creditCards?.some((p) => p.id === c.id)),
  ];
  const activeCards = allCards.filter((c) => c.isActive);
  /*
   * A stored card the offerable list can't show — archived since it was picked — still has to render,
   * or the trigger falls back to its placeholder and reads as cleared while form state keeps the id
   * (the same failure the account picker guards against; see lib/utils/account-field-options).
   * Appended, never offered: it is only there so the control tells the truth about what is stored.
   */
  const storedCard = allCards.find((c) => c.id === watchedCreditCardId);
  const unofferableCard = storedCard && !storedCard.isActive ? storedCard : undefined;
  const showCardRow = watchedPaymentMethod === 'credit_card';
  const hasActiveCards = activeCards.length > 0 || !!unofferableCard;

  // Clear credit card when payment method changes away from credit_card.
  useEffect(() => {
    if (watchedPaymentMethod !== 'credit_card' && watchedCreditCardId !== undefined) {
      setValue('creditCardId', undefined);
    }
  }, [watchedPaymentMethod, watchedCreditCardId, setValue]);

  function handleCardCreated(card: CreditCard) {
    setInlineCards((prev) => [...prev, card]);
    setValue('creditCardId', card.id, { shouldValidate: true });
  }

  return (
    <>
      <FormField
        control={control}
        name="paymentMethod"
        render={({ field }) => (
          <FormItem>
            <FormLabel>{t('label')}</FormLabel>
            <MaybeLockedTooltip tooltip={disabledTooltip} show={disabled}>
              <FormControl>
                <FormCombobox
                  value={field.value ?? ''}
                  onValueChange={field.onChange}
                  disabled={disabled}
                  placeholder={t('placeholder')}
                  options={PAYMENT_METHODS.map((method) => ({
                    value: method,
                    label: t(`methods.${method}`),
                  }))}
                />
              </FormControl>
            </MaybeLockedTooltip>
            <FormMessage />
          </FormItem>
        )}
      />

      <AnimatePresence initial={false}>
        {showCardRow && (
          <motion.div
            key="credit-card"
            initial={{ opacity: 0, height: 0, overflow: 'hidden' }}
            animate={{ opacity: 1, height: 'auto', overflow: 'visible' }}
            exit={{ opacity: 0, height: 0, overflow: 'hidden' }}
            transition={{ duration: ANIMATION_DEFAULT }}
            style={{ marginTop: -16 }}
          >
            <div className="pt-4">
              {hasActiveCards ? (
                <FormField
                  control={control}
                  name="creditCardId"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>{t('creditCard.label')}</FormLabel>
                      <MaybeLockedTooltip tooltip={disabledTooltip} show={disabled}>
                        <FormControl>
                          <FormCombobox
                            value={field.value?.toString() ?? ''}
                            onValueChange={(v) => field.onChange(Number(v))}
                            disabled={disabled}
                            placeholder={t('creditCard.placeholder')}
                            data-testid="payment-method-card-select"
                            options={[
                              ...activeCards.map((card) => ({
                                value: card.id.toString(),
                                label: card.name,
                              })),
                              ...(unofferableCard
                                ? [
                                    {
                                      value: unofferableCard.id.toString(),
                                      label: t('creditCard.archived', {
                                        name: unofferableCard.name,
                                      }),
                                    },
                                  ]
                                : []),
                            ]}
                          />
                        </FormControl>
                      </MaybeLockedTooltip>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              ) : (
                <div className="flex items-center justify-between p-3 gap-x-3 border border-dashed rounded-lg">
                  <p className="text-paragraph-sm text-muted-foreground">{t('noCards.message')}</p>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={disabled}
                    data-testid="payment-method-add-card"
                    onClick={() => setCardDialogOpen(true)}
                  >
                    {t('noCards.addCard')}
                  </Button>
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Stacked on top of the host form dialog — Radix portals it above with its own
          overlay, dimming the form behind (same stacking the expense form's soft-confirm
          dialogs already use). The host form stays mounted, so its values survive. */}
      <CreditCardFormDialog
        stacked
        open={cardDialogOpen}
        onOpenChange={setCardDialogOpen}
        preferredCurrencies={preferredCurrencies}
        onSuccess={() => router.refresh()}
        onCreated={handleCardCreated}
      />
    </>
  );
}
