'use client';

import { useTranslations } from 'next-intl';

import {
  DollarRateConsent,
  type DollarRateConsentProposal,
} from '@/app/(protected)/shared/_components/dollar-rate-consent';
import {
  agreePotDollarRate,
  proposePotDollarRate,
  withdrawPotDollarRate,
} from '@/app/(protected)/shared/pot-actions';
import type { SharedDollarRate } from '@/lib/constants/dollar-rates';

interface PotDollarRateSectionProps {
  potId: number;
  dollarRate: SharedDollarRate;
  proposal: DollarRateConsentProposal | null;
  canChange: boolean;
}

/*
 * The pot's dollar rate, under the figures it explains, changed by its OWNERS' agreement. Takes the
 * rate's own fields rather than the pot, because an owner the pot is hidden from sees this section and
 * nothing else of it.
 */
export function PotDollarRateSection({
  potId,
  dollarRate,
  proposal,
  canChange,
}: PotDollarRateSectionProps) {
  const t = useTranslations('shared');

  return (
    <DollarRateConsent
      idPrefix={`pot-${potId}`}
      copy="pots.dollarRate"
      fieldLabel={t('pots.form.dollarRate.label')}
      fieldPlaceholder={t('pots.form.dollarRate.placeholder')}
      dollarRate={dollarRate}
      proposal={proposal}
      canChange={canChange}
      onPropose={(rate) => proposePotDollarRate(potId, rate)}
      onAgree={() => agreePotDollarRate(potId)}
      onWithdraw={() => withdrawPotDollarRate(potId)}
    />
  );
}
