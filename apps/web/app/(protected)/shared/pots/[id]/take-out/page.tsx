import { notFound } from 'next/navigation';

import { canTakeShareOut } from '@/app/(protected)/shared/pot-rules';
import { TakeOutWizard } from '@/app/(protected)/shared/pots/[id]/take-out/_components/take-out-wizard';
import { getAccounts } from '@/lib/api/accounts';
import { getGroup } from '@/lib/api/groups';
import { getPot, getPotHoldings } from '@/lib/api/pots';
import { getSettings } from '@/lib/api/settings';
import { isIsoDate } from '@/lib/utils/dates';
import { generatePageMetadata } from '@/lib/utils/page-metadata';

export async function generateMetadata() {
  return await generatePageMetadata('shared.pots.takeOut');
}

interface TakeOutPageProps {
  params: Promise<{ id: string }>;
  // The date the share is priced at. In the URL rather than in client state so the SERVER re-reads the
  // pot as at that date — see below.
  searchParams: Promise<{ date?: string }>;
}

/*
 * "Take a share out" (U6): one member's whole share leaves the shared money.
 *
 * The date lives in the URL, and that is the design rather than a convenience. A share is worth what
 * the pot was worth on the day, so `getPot(id, date)` bounds BOTH the ledger replay and the valuation
 * — exactly what the API's own `_require_price` does when it records the event. So every figure the
 * flow shows is the figure it will be recorded at, with no second copy of the unit maths on the client
 * to disagree with the server.
 *
 * The consequence is that a chosen date can make the flow inapplicable (a pot with no known value then
 * has no price to redeem units at). Entering cold is refused in that case; choosing such a date once
 * inside is not, because the person needs the picker to get back out of it.
 */
export default async function TakeOutPage({ params, searchParams }: TakeOutPageProps) {
  const { id } = await params;
  const { date } = await searchParams;

  const potId = Number(id);
  if (!Number.isInteger(potId) || potId <= 0) notFound();

  // A malformed date is dropped rather than 404'd: it would otherwise be a way to break a shared link.
  const asOfDate = date !== undefined && isIsoDate(date) ? date : undefined;

  const pot = await getPot(potId, asOfDate);
  if (!pot) notFound();
  // Entirely a write flow, so there is nothing to show without write access — the same answer /admin
  // gives a non-admin, rather than a read-only view of a form that could not be submitted.
  if (!pot.canWrite) notFound();
  if (!canTakeShareOut(pot) && asOfDate === undefined) notFound();

  const [group, holdings, accounts, settings] = await Promise.all([
    getGroup(pot.groupId),
    getPotHoldings(potId),
    getAccounts(),
    getSettings().catch(() => null),
  ]);
  if (!group || !holdings) notFound();

  return (
    <TakeOutWizard
      pot={pot}
      group={group}
      holdings={holdings}
      privateAccounts={accounts}
      asOfDate={asOfDate}
      timeZone={settings?.timezone ?? undefined}
    />
  );
}
