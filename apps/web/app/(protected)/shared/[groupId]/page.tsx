import { cookies } from 'next/headers';
import { notFound } from 'next/navigation';
import { ArrowLeft } from 'lucide-react';
import { getTranslations } from 'next-intl/server';

import { GroupBalancesSection } from '@/app/(protected)/shared/[groupId]/_components/group-balances-section';
import { GroupExpensesSection } from '@/app/(protected)/shared/[groupId]/_components/group-expenses-section';
import { GroupHubHeader } from '@/app/(protected)/shared/[groupId]/_components/group-hub-header';
import { GroupIncomeSection } from '@/app/(protected)/shared/[groupId]/_components/group-income-section';
import { GroupMembersSection } from '@/app/(protected)/shared/[groupId]/_components/group-members-section';
import { GroupPotsSection } from '@/app/(protected)/shared/[groupId]/_components/group-pots-section';
import { GroupSettlementsSection } from '@/app/(protected)/shared/[groupId]/_components/group-settlements-section';
import { hasAnySharedFlow } from '@/app/(protected)/shared/settlement-rules';
import { InlineLink } from '@/components/inline-link';
import { ROUTES } from '@/config/routes';
import { getAccounts } from '@/lib/api/accounts';
import { getSupportedCurrencies } from '@/lib/api/exchange-rates';
import {
  getGroupBalances,
  getGroupMoneySettings,
  getGroupSettlements,
} from '@/lib/api/group-settlements';
import { getGroup } from '@/lib/api/groups';
import { getPots } from '@/lib/api/pots';
import { getPageSettings } from '@/lib/api/settings';
import { getSharedExpenses } from '@/lib/api/shared-expenses';
import { getSharedIncome } from '@/lib/api/shared-income';
import { FALLBACK_PRIMARY_CURRENCY } from '@/lib/constants/currency';
import { resolveActiveCurrency } from '@/lib/stores/currency-store';
import { generatePageMetadata } from '@/lib/utils/page-metadata';

// Its own namespace rather than the list's, so a hub tab isn't titled "Groups".
export async function generateMetadata() {
  return await generatePageMetadata('shared.hub');
}

interface GroupHubPageProps {
  params: Promise<{ groupId: string }>;
}

export default async function GroupHubPage({ params }: GroupHubPageProps) {
  const t = await getTranslations('shared');
  const { groupId } = await params;
  const cookieStore = await cookies();

  // A non-numeric segment never reaches the API — `/shared/nonsense` is a 404, not a 422.
  const id = Number(groupId);
  if (!Number.isInteger(id) || id <= 0) notFound();

  // Null covers both "no such group" and "one you are not a member of", so the page's answer is
  // identical either way and cannot be used to probe which groups exist.
  const group = await getGroup(id);
  if (!group) notFound();

  const { settings, creditCards } = await getPageSettings();
  const primary = settings?.primaryCurrency ?? FALLBACK_PRIMARY_CURRENCY;
  /*
   * The display currency the user is browsing in, used ONLY for the glance figure beside each
   * balance bucket. The buckets themselves are never converted: each currency is its own settle line,
   * and a converted one would be a figure nobody can actually pay.
   */
  const displayCurrency = resolveActiveCurrency(cookieStore, primary);

  /*
   * Only this group's pots, and only the ones the viewer may see — RLS decides that, so the list
   * simply comes back shorter for a member the pot is hidden from rather than erroring.
   *
   * The four money reads are the flow half: what has been spent, what has been earned, where
   * everyone stands, and what has cleared a balance. None of them is caught, deliberately — an empty
   * list rendered from a failed read would say "nothing shared yet" about a group that has shared
   * plenty, which is worse than the page failing. That is the posture `getPots` already takes here.
   *
   * The money SETTINGS are the exception, and only because nothing on screen depends on them: they
   * gate one admin convenience control, which is simply not offered when they cannot be read.
   *
   * `getAccounts` is the caller's OWN accounts, and that is the whole point: the other members' are
   * hidden by the row-level policies, which is why each side of a settlement records its own cash
   * leg. Archived ones are included so a settlement that named one still reads back by name; the
   * pickers only ever offer active accounts.
   */
  const [
    pots,
    expenses,
    income,
    balances,
    settlements,
    moneySettings,
    accounts,
    supportedCurrencies,
  ] = await Promise.all([
    getPots(group.id),
    getSharedExpenses(group.id),
    getSharedIncome(group.id),
    getGroupBalances(group.id, displayCurrency),
    getGroupSettlements(group.id),
    getGroupMoneySettings(group.id).catch(() => null),
    getAccounts({ showArchived: true }),
    // The currency picker degrades to the full ISO list on a fetch error, and the API's 422 guards.
    getSupportedCurrencies().catch(() => undefined),
  ]);

  const groupExpenses = expenses ?? [];
  const groupIncome = income ?? [];

  return (
    <div className="flex flex-col flex-1 p-8 gap-y-6">
      <InlineLink href={ROUTES.shared} color="muted" icon={ArrowLeft}>
        {t('hub.back')}
      </InlineLink>
      <GroupHubHeader group={group} />
      {/*
       * The money block, in the order D29 sets: where everyone stands, what was spent, what came in,
       * and what has already cleared. Balances lead because they are the question a household opens
       * the page with, and income sits under expenses because a household records far more of one
       * than the other.
       */}
      {balances && (
        <GroupBalancesSection
          group={group}
          balances={balances}
          hasAnyFlow={hasAnySharedFlow(groupExpenses, groupIncome)}
          moneySettings={moneySettings}
          accounts={accounts}
          timeZone={settings?.timezone ?? undefined}
        />
      )}
      <GroupExpensesSection
        group={group}
        expenses={groupExpenses}
        accounts={accounts}
        creditCards={creditCards}
        preferredCurrencies={settings?.preferredCurrencies ?? undefined}
        supportedCurrencies={supportedCurrencies}
        timeZone={settings?.timezone ?? undefined}
      />
      <GroupIncomeSection
        group={group}
        income={groupIncome}
        accounts={accounts}
        preferredCurrencies={settings?.preferredCurrencies ?? undefined}
        supportedCurrencies={supportedCurrencies}
        timeZone={settings?.timezone ?? undefined}
      />
      <GroupSettlementsSection group={group} settlements={settlements ?? []} accounts={accounts} />
      <GroupPotsSection
        group={group}
        pots={pots}
        preferredCurrencies={settings?.preferredCurrencies ?? undefined}
      />
      <GroupMembersSection group={group} />
    </div>
  );
}
