import { notFound } from 'next/navigation';

import { ShareWizard } from '@/app/(protected)/shared/[groupId]/share/_components/share-wizard';
import { shareWizardEntry } from '@/app/(protected)/shared/pot-rules';
import { getAccounts } from '@/lib/api/accounts';
import { getGroup } from '@/lib/api/groups';
import { getInvestments } from '@/lib/api/investments';
import { getPot, getPotHoldings, getPotOwnershipEvents } from '@/lib/api/pots';
import { getSettings } from '@/lib/api/settings';
import { API_MAX_PAGE_SIZE } from '@/lib/constants/api-constants';
import { generatePageMetadata } from '@/lib/utils/page-metadata';

export async function generateMetadata() {
  return await generatePageMetadata('shared.pots.share');
}

interface SharePageProps {
  params: Promise<{ groupId: string }>;
  // `?pot=` targets shared money that already exists — how the pot page hands this flow off, and how
  // an interrupted run resumes.
  searchParams: Promise<{ pot?: string }>;
}

/*
 * "Share something you own" (U6): the guided way co-owned money comes into existence.
 *
 * It orchestrates three writes that no transaction spans — create the pot, move the holdings in,
 * record the baseline — so the step it opens on is DERIVED from what the server already has rather
 * than remembered. That is what makes a failed step, or a closed tab, recoverable: come back to the
 * same URL and it continues from the first thing still missing. See `shareWizardEntry`.
 *
 * Both ways in are gated the way the API gates them, so a control is never offered and then refused:
 * creating shared money is group-admin only, and filling one that already exists needs write access to
 * it. Neither has anything to show without that permission — this page is entirely a write flow — so
 * both answer with the app's 404, the same posture /admin takes.
 */
export default async function SharePage({ params, searchParams }: SharePageProps) {
  const { groupId } = await params;
  const { pot: potParam } = await searchParams;

  // A non-numeric segment never reaches the API — `/shared/nonsense/share` is a 404, not a 422.
  const id = Number(groupId);
  if (!Number.isInteger(id) || id <= 0) notFound();

  const group = await getGroup(id);
  if (!group) notFound();

  const potId = potParam === undefined ? null : Number(potParam);
  if (potId !== null && (!Number.isInteger(potId) || potId <= 0)) notFound();

  /*
   * The two private lists are the eligible set, and they are the right lists rather than filtered
   * ones: both endpoints are owner-scoped by construction, so something already shared cannot appear
   * in either. Active-only because an archived holding contributes nothing to the pot's value, so
   * sharing one and then dividing that value would divide a figure it is not part of.
   */
  const [accounts, investments, settings] = await Promise.all([
    getAccounts(),
    getInvestments({ activeOnly: true, pageSize: API_MAX_PAGE_SIZE }),
    getSettings().catch(() => null),
  ]);

  if (potId === null) {
    // Nothing to fill yet, so this run has to create it — which the API allows group admins only.
    if (group.myRole !== 'admin') notFound();
    return (
      <ShareWizard
        group={group}
        pot={null}
        sharedCount={0}
        entryStage={shareWizardEntry(null)}
        privateAccounts={accounts}
        privateInvestments={investments.items}
        preferredCurrencies={settings?.preferredCurrencies ?? undefined}
        timeZone={settings?.timezone ?? undefined}
      />
    );
  }

  const [pot, holdings, events] = await Promise.all([
    getPot(potId),
    getPotHoldings(potId),
    getPotOwnershipEvents(potId),
  ]);
  // Null covers both "no such pot" and "one you may not see". The group check matters just as much: a
  // pot id from ANOTHER group in this group's URL would otherwise be filled from this group's roster.
  if (!pot || !holdings || !events || pot.groupId !== group.id) notFound();
  if (!pot.canWrite) notFound();

  return (
    <ShareWizard
      group={group}
      pot={pot}
      sharedCount={holdings.investments.length + holdings.accounts.length}
      entryStage={shareWizardEntry({ holdings, events })}
      privateAccounts={accounts}
      privateInvestments={investments.items}
      preferredCurrencies={settings?.preferredCurrencies ?? undefined}
      timeZone={settings?.timezone ?? undefined}
    />
  );
}
