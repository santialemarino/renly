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
import { MOVEMENT_KINDS, type MovementKind } from '@/lib/constants/accounts';
import { generatePageMetadata } from '@/lib/utils/page-metadata';

interface AccountLedgerPageProps {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ kind?: string; page?: string }>;
}

export async function generateMetadata() {
  return await generatePageMetadata('accounts');
}

export default async function AccountLedgerPage({ params, searchParams }: AccountLedgerPageProps) {
  const t = await getTranslations('accounts');
  const { id } = await params;
  const query = await searchParams;

  // A non-numeric segment never reaches the API — `/accounts/nonsense` is a 404, not a 422.
  const accountId = Number(id);
  if (!Number.isInteger(accountId) || accountId <= 0) notFound();

  // Null covers both "no such account" and "someone else's", so the page's answer is identical
  // either way and cannot be used to probe which accounts exist.
  const account = await getAccount(accountId);
  if (!account) notFound();

  // An unknown kind is a hand-edited URL: drop it rather than pass it on, so the page renders the
  // whole ledger instead of an API validation error.
  const kind = MOVEMENT_KINDS.includes(query.kind as MovementKind)
    ? (query.kind as MovementKind)
    : undefined;
  const page = Math.max(1, Number(query.page) || 1);

  const movements = await getAccountMovements(accountId, { kind, page });

  return (
    <div className="flex flex-col flex-1 p-8 gap-y-4">
      <InlineLink href={ROUTES.accounts} color="muted" icon={ArrowLeft}>
        {t('ledger.back')}
      </InlineLink>
      <AccountLedgerHeader account={account} />
      <AccountLedgerToolbar accountId={accountId} />
      <AccountLedgerTable accountId={accountId} data={movements} filtered={!!kind} />
    </div>
  );
}
