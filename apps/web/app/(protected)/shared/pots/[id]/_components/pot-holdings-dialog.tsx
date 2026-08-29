'use client';

import { useEffect, useMemo, useState } from 'react';
import { Landmark, Rows3 } from 'lucide-react';
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
import { movePotHoldings } from '@/app/(protected)/shared/pot-actions';
import { ComboboxMultiSelect } from '@/components/combobox-multi-select';
import type { Account } from '@/lib/api/accounts';
import type { Investment } from '@/lib/api/investments';
import type { Pot, PotHoldings } from '@/lib/api/pots';

interface PotHoldingsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  pot: Pot;
  into: boolean;
  holdings: PotHoldings;
  privateInvestments: Investment[];
  privateAccounts: Account[];
  onSuccess: () => void;
}

/*
 * Moving holdings into a pot, or back out of it. One dialog for both directions: the payload is
 * identical and only the eligible lists and the copy differ, so two would be two places for the same
 * selection logic to drift.
 *
 * Moving IN offers the caller's own private, active holdings — the same set the API accepts, since a
 * shared row can never appear in an owner-scoped list and an archived one contributes nothing to the
 * pot's value. Moving OUT offers what the pot holds, archived included: an archived holding still
 * points at the pot, so it still blocks deleting it and still has to be retrievable.
 *
 * Naming a holding that cannot move refuses the WHOLE request rather than moving the rest, which is
 * why the selection is submitted as one call and the refusal is surfaced whole.
 */
export function PotHoldingsDialog({
  open,
  onOpenChange,
  pot,
  into,
  holdings,
  privateInvestments,
  privateAccounts,
  onSuccess,
}: PotHoldingsDialogProps) {
  const t = useTranslations('shared');
  const [investmentIds, setInvestmentIds] = useState<number[]>([]);
  const [accountIds, setAccountIds] = useState<number[]>([]);
  const [pending, setPending] = useState(false);

  // Clear the selection whenever the dialog opens, so a cancelled move is not silently resubmitted
  // next time. Reset on open rather than on close so nothing blanks out mid-exit animation.
  useEffect(() => {
    if (open) {
      setInvestmentIds([]);
      setAccountIds([]);
    }
  }, [open]);

  const investmentItems = useMemo(
    () =>
      into
        ? privateInvestments.map((i) => ({ id: i.id, label: i.name }))
        : holdings.investments.map((i) => ({
            id: i.id,
            label: i.isActive ? i.name : `${i.name} · ${t('pots.holdings.archived')}`,
          })),
    [into, privateInvestments, holdings.investments, t],
  );

  const accountItems = useMemo(
    () =>
      into
        ? privateAccounts
            .filter((a) => a.isActive)
            .map((a) => ({ id: a.id, label: `${a.name} · ${a.currency}` }))
        : holdings.accounts.map((a) => ({
            id: a.id,
            label: a.isActive
              ? `${a.name} · ${a.currency}`
              : `${a.name} · ${a.currency} · ${t('pots.holdings.archived')}`,
          })),
    [into, privateAccounts, holdings.accounts, t],
  );

  const nothingSelected = investmentIds.length === 0 && accountIds.length === 0;

  function toggle(setter: React.Dispatch<React.SetStateAction<number[]>>, id: number) {
    setter((ids) => (ids.includes(id) ? ids.filter((existing) => existing !== id) : [...ids, id]));
  }

  async function onSubmit() {
    setPending(true);
    try {
      const result = await movePotHoldings(pot.id, investmentIds, accountIds, into);
      if (!result.ok) {
        toast.error(result.conflictDetail);
        return;
      }
      toast.success(t(into ? 'pots.holdings.addSuccess' : 'pots.holdings.removeSuccess'));
      onSuccess();
      onOpenChange(false);
    } catch {
      toast.error(t('pots.holdings.error'));
    } finally {
      setPending(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {t(into ? 'pots.holdings.addTitle' : 'pots.holdings.removeTitle')}
          </DialogTitle>
        </DialogHeader>
        <DialogDescription>
          {t(into ? 'pots.holdings.addDescription' : 'pots.holdings.removeDescription')}
        </DialogDescription>

        <div className="flex flex-col min-w-0 gap-y-4">
          <div className="flex flex-col gap-y-2">
            {/* The base Label, not FormLabel: there is no react-hook-form here, and FormLabel outside
                a Form provider throws on the null field context. */}
            <Label>{t('pots.holdings.investments')}</Label>
            <ComboboxMultiSelect
              items={investmentItems}
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
              items={accountItems}
              selectedIds={accountIds}
              onToggle={(id) => toggle(setAccountIds, id)}
              placeholder={t('pots.holdings.accountsPlaceholder')}
              searchPlaceholder={t('pots.holdings.accountsSearch')}
              emptyMessage={t('pots.holdings.accountsEmpty')}
              showChips
              icon={<Landmark className="size-4" />}
            />
            {into && (
              <p className="text-paragraph-xs text-muted-foreground">
                {t('pots.holdings.accountsHint')}
              </p>
            )}
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t('form.cancel')}
          </Button>
          <Button blue onClick={onSubmit} disabled={pending || nothingSelected}>
            {pending
              ? t('form.cta.loading')
              : t(into ? 'pots.holdings.addCta' : 'pots.holdings.removeCta')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
