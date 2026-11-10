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
import {
  agreePotDollarRate,
  proposePotDollarRate,
  withdrawPotDollarRate,
} from '@/app/(protected)/shared/pot-actions';
import { FormCombobox } from '@/components/form-combobox';
import type { PotDollarRateProposal } from '@/lib/api/pots';
import { POT_DOLLAR_RATES, type PotDollarRate } from '@/lib/constants/pots';

interface PotDollarRateSectionProps {
  potId: number;
  dollarRate: PotDollarRate;
  proposal: PotDollarRateProposal | null;
  canChange: boolean;
}

/*
 * The pot's dollar rate, under the figures it explains, and the one way to change it: by the owners'
 * agreement. One owner proposes, every other owner agrees, and nothing changes until all have — so a
 * pending proposal is stated here with whom it still waits on, and the reader is offered exactly what
 * the API says they may do about it.
 *
 * Every sentence is whole per rate rather than a label interpolated into one, so each language can
 * phrase it its own way. Takes the rate's own fields rather than the pot, because an owner the pot is
 * hidden from sees this section and nothing else of it.
 */
export function PotDollarRateSection({
  potId,
  dollarRate,
  proposal,
  canChange,
}: PotDollarRateSectionProps) {
  const t = useTranslations('shared');
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [rate, setRate] = useState<PotDollarRate>(dollarRate);
  const [pending, setPending] = useState(false);

  const options = POT_DOLLAR_RATES.filter((option) => option !== dollarRate).map((option) => ({
    value: option,
    label: t(`pots.dollarRate.options.${option}`),
  }));

  // Runs one write, toasts its outcome, and refreshes the page so the figures follow the rate.
  async function run(
    write: () => Promise<{ ok: boolean; conflictDetail?: string }>,
    success: string,
  ) {
    setPending(true);
    try {
      const result = await write();
      if (!result.ok) {
        toast.error(result.conflictDetail);
        return false;
      }
      toast.success(success);
      router.refresh();
      return true;
    } catch {
      toast.error(t('pots.dollarRate.error'));
      return false;
    } finally {
      setPending(false);
    }
  }

  async function onPropose() {
    setPending(true);
    try {
      const result = await proposePotDollarRate(potId, rate);
      if (!result.ok) {
        toast.error(result.conflictDetail);
        return;
      }
      toast.success(
        result.data.dollarRateProposal
          ? t('pots.dollarRate.proposedSuccess')
          : t('pots.dollarRate.changedSuccess'),
      );
      setOpen(false);
      router.refresh();
    } catch {
      toast.error(t('pots.dollarRate.error'));
    } finally {
      setPending(false);
    }
  }

  function onOpen() {
    setRate(options[0]?.value ?? dollarRate);
    setOpen(true);
  }

  return (
    <div className="flex flex-col gap-y-2">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <p className="flex items-center gap-x-2 text-paragraph-sm text-muted-foreground">
          <DollarSign className="size-4 shrink-0" />
          {t(`pots.dollarRate.notice.${dollarRate}`)}
        </p>
        {canChange && (
          <Button variant="outline" size="sm" onClick={onOpen}>
            {t('pots.dollarRate.change')}
          </Button>
        )}
      </div>

      {proposal && (
        <div className="flex flex-wrap items-center justify-between px-4 py-3 gap-x-3 gap-y-2 bg-muted/30 border border-border rounded-1.5xl">
          <div className="flex flex-col min-w-0 gap-y-0.5">
            <p className="text-paragraph-sm text-foreground">
              {t(`pots.dollarRate.proposal.${proposal.dollarRate}`, {
                proposer: proposal.proposedBy,
              })}
            </p>
            <p className="text-paragraph-xs text-muted-foreground">
              {proposal.waitingOn.length > 0
                ? t('pots.dollarRate.waitingOn', {
                    count: proposal.waitingOn.length,
                    names: proposal.waitingOn.join(', '),
                  })
                : t('pots.dollarRate.nobodyLeft')}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-x-2">
            {proposal.canWithdraw && (
              <Button
                variant="outline"
                disabled={pending}
                onClick={() =>
                  run(() => withdrawPotDollarRate(potId), t('pots.dollarRate.withdrawSuccess'))
                }
              >
                {t('pots.dollarRate.withdraw')}
              </Button>
            )}
            {proposal.canAgree && (
              <Button
                blue
                disabled={pending}
                onClick={() =>
                  run(() => agreePotDollarRate(potId), t('pots.dollarRate.agreeSuccess'))
                }
              >
                {t('pots.dollarRate.agree')}
              </Button>
            )}
          </div>
        </div>
      )}

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('pots.dollarRate.dialog.title')}</DialogTitle>
          </DialogHeader>
          <DialogDescription>{t('pots.dollarRate.dialog.description')}</DialogDescription>
          <div className="flex flex-col gap-y-2">
            <Label required htmlFor={`pot-${potId}-dollar-rate`}>
              {t('pots.form.dollarRate.label')}
            </Label>
            <FormCombobox
              id={`pot-${potId}-dollar-rate`}
              value={rate}
              onValueChange={(value) => setRate(value as PotDollarRate)}
              options={options}
              placeholder={t('pots.form.dollarRate.placeholder')}
              className="w-full"
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>
              {t('form.cancel')}
            </Button>
            <Button blue disabled={pending} onClick={onPropose}>
              {pending ? t('pots.dollarRate.dialog.loading') : t('pots.dollarRate.dialog.submit')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
