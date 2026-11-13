'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { DollarSign } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';

import {
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Label,
} from '@repo/ui/components';
import type {
  SharedDataResult,
  SharedMutationResult,
} from '@/app/(protected)/shared/mutation-result';
import { FormCombobox } from '@/components/form-combobox';
import { SHARED_DOLLAR_RATES, type SharedDollarRate } from '@/lib/constants/dollar-rates';

// A pending change of a shared dollar rate, as the API resolves it for the reader.
export interface DollarRateConsentProposal {
  dollarRate: SharedDollarRate;
  proposedBy: string;
  // The parties who have not agreed yet; empty once everyone has.
  waitingOn: string[];
  canAgree: boolean;
  canWithdraw: boolean;
}

interface DollarRateConsentProps {
  // Prefixes the picker's id, so two of these on one page never share one.
  idPrefix: string;
  // The copy's namespace under `shared` — `pots.dollarRate` or `moneySettings.dollarRate` — whose keys
  // say who agrees (a pot's owners, a group's members).
  copy: string;
  // The picker's label and placeholder, which each caller already words for its own form.
  fieldLabel: string;
  fieldPlaceholder: string;
  dollarRate: SharedDollarRate;
  proposal: DollarRateConsentProposal | null;
  canChange: boolean;
  onPropose: (
    rate: SharedDollarRate,
  ) => Promise<SharedDataResult<{ dollarRateProposal: DollarRateConsentProposal | null }>>;
  onAgree: () => Promise<SharedMutationResult>;
  onWithdraw: () => Promise<SharedMutationResult>;
}

/*
 * A shared dollar rate, and the one way to change it: by the agreement of everyone it affects. One
 * party proposes, every other agrees, and nothing changes until all have — so a pending proposal is
 * stated here with whom it still waits on, and the reader is offered exactly what the API says they may
 * do about it. A pot's owners and a group's members agree the same way, so both render this; only the
 * copy (who agrees) and the three writes differ.
 *
 * Every sentence is whole per rate rather than a label interpolated into one, so each language can
 * phrase it its own way.
 */
export function DollarRateConsent({
  idPrefix,
  copy,
  fieldLabel,
  fieldPlaceholder,
  dollarRate,
  proposal,
  canChange,
  onPropose,
  onAgree,
  onWithdraw,
}: DollarRateConsentProps) {
  const t = useTranslations('shared');
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [rate, setRate] = useState<SharedDollarRate>(dollarRate);
  const [pending, setPending] = useState(false);

  const options = SHARED_DOLLAR_RATES.filter((option) => option !== dollarRate).map((option) => ({
    value: option,
    label: t(`pots.dollarRate.options.${option}`),
  }));

  // Runs one write, toasts its outcome, and refreshes the page so the figures follow the rate.
  async function run(write: () => Promise<SharedMutationResult>, success: string) {
    setPending(true);
    try {
      const result = await write();
      if (!result.ok) {
        toast.error(result.conflictDetail);
        return;
      }
      toast.success(success);
      router.refresh();
    } catch {
      toast.error(t(`${copy}.error`));
    } finally {
      setPending(false);
    }
  }

  async function handlePropose() {
    setPending(true);
    try {
      const result = await onPropose(rate);
      if (!result.ok) {
        toast.error(result.conflictDetail);
        return;
      }
      toast.success(
        result.data.dollarRateProposal ? t(`${copy}.proposedSuccess`) : t(`${copy}.changedSuccess`),
      );
      setOpen(false);
      router.refresh();
    } catch {
      toast.error(t(`${copy}.error`));
    } finally {
      setPending(false);
    }
  }

  function handleOpen() {
    setRate(options[0]?.value ?? dollarRate);
    setOpen(true);
  }

  return (
    <div className="flex flex-col gap-y-2">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <p className="flex items-center gap-x-2 text-paragraph-sm text-muted-foreground">
          <DollarSign className="size-4 shrink-0" />
          {t(`${copy}.notice.${dollarRate}`)}
        </p>
        {canChange && (
          <Button variant="outline" size="sm" onClick={handleOpen}>
            {t(`${copy}.change`)}
          </Button>
        )}
      </div>

      {proposal && (
        <div className="flex flex-wrap items-center justify-between px-4 py-3 gap-x-3 gap-y-2 bg-muted/30 border border-border rounded-1.5xl">
          <div className="flex flex-col min-w-0 gap-y-0.5">
            <p className="text-paragraph-sm text-foreground">
              {t(`${copy}.proposal.${proposal.dollarRate}`, { proposer: proposal.proposedBy })}
            </p>
            <p className="text-paragraph-xs text-muted-foreground">
              {proposal.waitingOn.length > 0
                ? t(`${copy}.waitingOn`, {
                    count: proposal.waitingOn.length,
                    names: proposal.waitingOn.join(', '),
                  })
                : t(`${copy}.nobodyLeft`)}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-x-2">
            {proposal.canWithdraw && (
              <Button
                variant="outline"
                disabled={pending}
                onClick={() => run(onWithdraw, t(`${copy}.withdrawSuccess`))}
              >
                {t(`${copy}.withdraw`)}
              </Button>
            )}
            {proposal.canAgree && (
              <Button
                blue
                disabled={pending}
                onClick={() => run(onAgree, t(`${copy}.agreeSuccess`))}
              >
                {t(`${copy}.agree`)}
              </Button>
            )}
          </div>
        </div>
      )}

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t(`${copy}.dialog.title`)}</DialogTitle>
          </DialogHeader>
          <DialogDescription>{t(`${copy}.dialog.description`)}</DialogDescription>
          <div className="flex flex-col gap-y-2">
            <Label required htmlFor={`${idPrefix}-dollar-rate`}>
              {fieldLabel}
            </Label>
            <FormCombobox
              id={`${idPrefix}-dollar-rate`}
              value={rate}
              onValueChange={(value) => setRate(value as SharedDollarRate)}
              options={options}
              placeholder={fieldPlaceholder}
              className="w-full"
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>
              {t('form.cancel')}
            </Button>
            <Button blue disabled={pending} onClick={handlePropose}>
              {pending ? t(`${copy}.dialog.loading`) : t(`${copy}.dialog.submit`)}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
