import { notFound } from 'next/navigation';

import { canContributeHolding } from '@/app/(protected)/shared/pot-rules';
import { ContributeWizard } from '@/app/(protected)/shared/pots/[id]/contribute/_components/contribute-wizard';
import { getContributableHoldings, getPot } from '@/lib/api/pots';
import { generatePageMetadata } from '@/lib/utils/page-metadata';

export async function generateMetadata() {
  return await generatePageMetadata('shared.pots.contribute');
}

interface ContributePageProps {
  params: Promise<{ id: string }>;
}

/*
 * "Contribute something you own" (U6): a holding leaves your private scope, is valued where it
 * stands, and buys you a share worth exactly that.
 *
 * The fourth guided flow, and the one that replaces a refusal. Moving a holding into a divided pot on
 * its own raises the pot's value while nobody's units change, so what came wholly out of one person's
 * scope is gifted pro-rata to every owner — silently. Pairing the move with units priced against the
 * pot's EXISTING holdings is what makes it honest.
 *
 * There is no date in the URL, unlike take-out and buy-out, and its absence is the design rather than
 * a simplification. Those two price a SHARE, which is worth what the pot was worth on the day; this
 * one prices a HOLDING that has no pot-membership history at all — it counts in the pot's value from
 * the moment it moves. So a past date would issue units for what it was worth then against an asset
 * the pot gains at what it is worth now, and hand the difference out pro-rata.
 *
 * It needs no roster either, which is what makes it the shortest of the four: the holding is the
 * caller's, so the share is the caller's, and there is no seat to pick.
 */
export default async function ContributePage({ params }: ContributePageProps) {
  const { id } = await params;

  const potId = Number(id);
  if (!Number.isInteger(potId) || potId <= 0) notFound();

  const pot = await getPot(potId);
  if (!pot) notFound();
  // Entirely a write flow, so there is nothing to show without write access — the same answer /admin
  // gives a non-admin, rather than a read-only view of a form that could not be submitted.
  if (!pot.canWrite) notFound();
  /*
   * Unlike the take-out, there is no "unless a date was chosen" escape: with no unit price there is
   * nothing to issue units against and no picker to get back out of, since the date is not a field.
   * An undivided pot lands here too, and that is right — it has the plain move-in, which is the same
   * act with nothing yet to price against.
   */
  if (!canContributeHolding(pot)) notFound();

  const holdings = await getContributableHoldings(potId);
  if (!holdings) notFound();

  return <ContributeWizard pot={pot} holdings={holdings} />;
}
