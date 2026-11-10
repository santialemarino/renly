import { getTranslations } from 'next-intl/server';

import { PageHeader } from '@/app/(protected)/_components/page-header';
import { PotDollarRateSection } from '@/app/(protected)/shared/pots/[id]/_components/pot-dollar-rate-section';
import type { PotDollarRateState } from '@/lib/api/pots';
import { potLabel } from '@/lib/pots';

interface PotDollarRateOnlyProps {
  state: PotDollarRateState;
}

/*
 * The pot page for an owner the pot is hidden from: its name, its group, and its dollar rate with any
 * change waiting for their agreement — and nothing else. Visibility is set per member, but a stake is a
 * stake, and the owners decide the rate together; without this the owner would be asked to agree to a
 * change on a page that answers them 404.
 */
export async function PotDollarRateOnly({ state }: PotDollarRateOnlyProps) {
  const t = await getTranslations('shared');
  const tCommon = await getTranslations('common');

  return (
    <div className="flex flex-col flex-1 p-8 gap-y-6">
      <PageHeader
        title={potLabel(state, tCommon('potDefaultLabel'))}
        subtitle={t('pots.subtitle', { group: state.groupName })}
      />
      <p className="text-paragraph-sm text-muted-foreground">{t('pots.dollarRate.hiddenOwner')}</p>
      <PotDollarRateSection
        potId={state.potId}
        dollarRate={state.dollarRate}
        proposal={state.dollarRateProposal}
        canChange={state.canChangeDollarRate}
      />
    </div>
  );
}
