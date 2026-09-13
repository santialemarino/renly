import { notFound } from 'next/navigation';
import { ArrowLeft } from 'lucide-react';
import { getTranslations } from 'next-intl/server';

import { PotHeader } from '@/app/(protected)/shared/pots/[id]/_components/pot-header';
import { PotHoldingsSection } from '@/app/(protected)/shared/pots/[id]/_components/pot-holdings-section';
import { PotLedgerSection } from '@/app/(protected)/shared/pots/[id]/_components/pot-ledger-section';
import { PotOwnershipSection } from '@/app/(protected)/shared/pots/[id]/_components/pot-ownership-section';
import { PotPermissionsSection } from '@/app/(protected)/shared/pots/[id]/_components/pot-permissions-section';
import { PotValueSection } from '@/app/(protected)/shared/pots/[id]/_components/pot-value-section';
import { InlineLink } from '@/components/inline-link';
import { sharedGroupPath } from '@/config/routes';
import { getAccounts } from '@/lib/api/accounts';
import { getGroup } from '@/lib/api/groups';
import { getInvestments } from '@/lib/api/investments';
import { getPot, getPotHoldings, getPotOwnershipEvents, getPotSeries } from '@/lib/api/pots';
import { getSettings } from '@/lib/api/settings';
import { API_MAX_PAGE_SIZE } from '@/lib/constants/api-constants';
import { generatePageMetadata } from '@/lib/utils/page-metadata';

// Its own namespace rather than the group list's, so a pot tab isn't titled "Groups".
export async function generateMetadata() {
  return await generatePageMetadata('shared.pots');
}

interface PotPageProps {
  params: Promise<{ id: string }>;
}

/*
 * The monitoring surface for one co-owned pot (V5): what it holds, what it is worth over time, whose
 * it is, and everything that has moved. Whoever may see the pot sees all of it, including a member
 * holding 0% — partial visibility of something you co-own is not a feature.
 */
export default async function PotPage({ params }: PotPageProps) {
  const t = await getTranslations('shared');
  const { id } = await params;

  // A non-numeric segment never reaches the API — `/shared/pots/nonsense` is a 404, not a 422.
  const potId = Number(id);
  if (!Number.isInteger(potId) || potId <= 0) notFound();

  // Null covers both "no such pot" and "one you may not see", so the page's answer is identical either
  // way and an id cannot be used to discover which pots exist.
  const pot = await getPot(potId);
  if (!pot) notFound();

  /*
   * The group carries the roster every dialog needs (which seats exist, which is yours, who is an
   * admin) — PotResponse names only the members who hold units or an explicit permission row, so it
   * cannot answer "who else could be given a share".
   *
   * The two private lists are the eligible set for the move-in picker and a movement's private leg,
   * and they are the right lists rather than filtered ones: both endpoints are owner-scoped by
   * construction, so a shared holding cannot appear in either. Active-only for the same reason the API
   * refuses an archived pot leg — an archived holding is excluded from the pot's value, so sharing one
   * or routing money through it would move a balance the NAV never sees.
   */
  const [group, holdings, events, series, accounts, investments, settings] = await Promise.all([
    getGroup(pot.groupId),
    getPotHoldings(potId),
    getPotOwnershipEvents(potId),
    getPotSeries(potId),
    getAccounts(),
    getInvestments({ activeOnly: true, pageSize: API_MAX_PAGE_SIZE }),
    getSettings().catch(() => null),
  ]);
  if (!group || !holdings || !events || !series) notFound();

  return (
    <div className="flex flex-col flex-1 p-8 gap-y-6">
      <InlineLink href={sharedGroupPath(pot.groupId)} color="muted" icon={ArrowLeft}>
        {t('pots.backToGroup', { group: group.name })}
      </InlineLink>
      <PotHeader pot={pot} group={group} holdings={holdings} />
      <PotOwnershipSection
        pot={pot}
        group={group}
        events={events}
        holdings={holdings}
        privateAccounts={accounts}
        timeZone={settings?.timezone ?? undefined}
      />
      <PotValueSection series={series} baseCurrency={pot.baseCurrency} />
      <PotHoldingsSection
        pot={pot}
        holdings={holdings}
        events={events}
        privateAccounts={accounts}
        privateInvestments={investments.items}
      />
      <PotLedgerSection pot={pot} events={events} />
      {group.myRole === 'admin' && <PotPermissionsSection pot={pot} group={group} />}
    </div>
  );
}
