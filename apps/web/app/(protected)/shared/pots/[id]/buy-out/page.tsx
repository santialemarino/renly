import { notFound } from 'next/navigation';

import { canRecordReagreement } from '@/app/(protected)/shared/pot-rules';
import { BuyOutWizard } from '@/app/(protected)/shared/pots/[id]/buy-out/_components/buy-out-wizard';
import { getGroup } from '@/lib/api/groups';
import { getPot } from '@/lib/api/pots';
import { getSettings } from '@/lib/api/settings';
import { isIsoDate } from '@/lib/utils/dates';
import { generatePageMetadata } from '@/lib/utils/page-metadata';
import { startRead } from '@/lib/utils/start-read';

export async function generateMetadata() {
  return await generatePageMetadata('shared.pots.buyOut');
}

interface BuyOutPageProps {
  params: Promise<{ id: string }>;
  // The date the share is valued at, in the URL so the SERVER re-reads the pot as at it.
  searchParams: Promise<{ date?: string }>;
}

/*
 * "Buy out a share" (U6): one member takes over another's whole share.
 *
 * Records the shares changing hands and nothing else, and says so. The money the buyer pays the seller
 * moves between two DIFFERENT people's private accounts, and no Renly movement spans those — a
 * transfer must stay within one scope, and an ownership event's private leg must be the caller's own
 * account. So the flow states the gap in words rather than recording half of what happened; the other
 * half arrives with settle-up.
 *
 * The date is a URL param for the same reason the take-out flow's is: `getPot(id, date)` bounds both
 * the ledger replay and the valuation, so the figure shown is the figure the event is recorded at, with
 * no second copy of the unit maths here to disagree with the server.
 */
export default async function BuyOutPage({ params, searchParams }: BuyOutPageProps) {
  const { id } = await params;
  const { date } = await searchParams;

  const potId = Number(id);
  if (!Number.isInteger(potId) || potId <= 0) notFound();

  const asOfDate = date !== undefined && isIsoDate(date) ? date : undefined;

  // The settings start with the pot, and the group as soon as the pot names it. The pot is awaited
  // first, so a pot that does not exist (or is read-only to you) is the 404 whatever the others say.
  const potRead = getPot(potId, asOfDate);
  const reads = startRead(
    Promise.all([
      potRead.then((found) => (found ? getGroup(found.groupId) : null)),
      getSettings().catch(() => null),
    ]),
  );

  const pot = await potRead;
  if (!pot) notFound();
  if (!pot.canWrite) notFound();

  const [group, settings] = await reads;
  if (!group) notFound();

  // Buying out needs a holder to buy from AND a second active seat to buy for, which is exactly what
  // gates the manual change-of-split too. A chosen date may make it inapplicable; entering cold may not.
  if (!canRecordReagreement(pot, group.activeMemberCount) && asOfDate === undefined) notFound();

  return (
    <BuyOutWizard
      pot={pot}
      group={group}
      asOfDate={asOfDate}
      timeZone={settings?.timezone ?? undefined}
    />
  );
}
