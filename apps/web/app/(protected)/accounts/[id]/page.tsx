import { notFound } from 'next/navigation';
import { ArrowLeft } from 'lucide-react';
import { getTranslations } from 'next-intl/server';

import { AccountLedgerHeader } from '@/app/(protected)/accounts/[id]/_components/account-ledger-header';
import { AccountLedgerTable } from '@/app/(protected)/accounts/[id]/_components/account-ledger-table';
import { AccountLedgerToolbar } from '@/app/(protected)/accounts/[id]/_components/account-ledger-toolbar';
import { InlineLink } from '@/components/inline-link';
import { ROUTES } from '@/config/routes';
import { getAccountMovements } from '@/lib/api/account-movements';
import { getAccount } from '@/lib/api/accounts';
import { getPageSettings } from '@/lib/api/settings';
import { MOVEMENT_KINDS, type MovementKind } from '@/lib/constants/accounts';
import { isFirstRunEmptyState } from '@/lib/onboarding';
import { generatePageMetadata } from '@/lib/utils/page-metadata';

// Its own namespace rather than the accounts list's, so a ledger tab isn't titled "Accounts".
export async function generateMetadata() {
  return await generatePageMetadata('accounts.ledger');
}

interface AccountLedgerPageProps {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ kind?: string; page?: string }>;
}

export default async function AccountLedgerPage({ params, searchParams }: AccountLedgerPageProps) {
  const t = await getTranslations('accounts');
  const { id } = await params;
  const query = await searchParams;

  // A non-numeric segment never reaches the API — `/accounts/nonsense` is a 404, not a 422.
  const accountId = Number(id);
  if (!Number.isInteger(accountId) || accountId <= 0) notFound();

  /*
   * Both query params are sanitized rather than forwarded: a hand-edited URL should render the
   * ledger, not an API validation error this page has no error boundary to catch. An unknown kind
   * falls back to the whole ledger; a fractional or infinite page falls back to the first (a page
   * past the end needs nothing here — the API clamps it to the last page that has rows).
   */
  const kind = MOVEMENT_KINDS.includes(query.kind as MovementKind)
    ? (query.kind as MovementKind)
    : undefined;
  const requestedPage = Math.trunc(Number(query.page));
  const page = Number.isFinite(requestedPage) && requestedPage > 1 ? requestedPage : 1;

  /*
   * Fetched together rather than in sequence — nothing here depends on the account row, so awaiting it
   * first only adds a round trip. The movements request is allowed to fail: for an id that isn't the
   * caller's it 404s alongside the account, and the null account below is what decides the page.
   */
  const [account, movements, { settings }] = await Promise.all([
    getAccount(accountId),
    getAccountMovements(accountId, { kind, page }).catch(() => null),
    getPageSettings(),
  ]);
  // Null covers both "no such account" and "someone else's", so the page's answer is identical either
  // way and cannot be used to probe which accounts exist.
  if (!account || !movements) notFound();

  // Teach the empty state only during first-run and only when no filter is hiding existing rows —
  // the same rule every other list surface uses.
  const firstRun = isFirstRunEmptyState(movements.total === 0, !!kind, settings);

  return (
    <div className="flex flex-col flex-1 p-8 gap-y-4">
      <InlineLink href={ROUTES.accounts} color="muted" icon={ArrowLeft}>
        {t('ledger.back')}
      </InlineLink>
      <AccountLedgerHeader account={account} />
      <AccountLedgerToolbar accountId={accountId} kind={kind} />
      <AccountLedgerTable
        accountId={accountId}
        data={movements}
        filtered={!!kind}
        firstRun={firstRun}
      />
    </div>
  );
}
