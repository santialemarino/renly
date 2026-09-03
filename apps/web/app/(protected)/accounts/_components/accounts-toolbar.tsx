'use client';

import { useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useTranslations } from 'next-intl';

import { AccountFormDialog } from '@/app/(protected)/accounts/_components/account-form-dialog';
import { EntityListToolbar } from '@/components/entity-list-toolbar';
import { ScopePill } from '@/components/scope-pill';
import { ROUTES } from '@/config/routes';
import type { ListScope } from '@/lib/api/types';
import { useSearchParamsNavigation } from '@/lib/hooks/use-search-params-navigation';
import { resolveListScope } from '@/lib/list-scope';

interface AccountsToolbarProps {
  preferredCurrencies?: string[];
  // Whether the caller belongs to any group at all — the one signal that turns the scope filter on,
  // so a solo user (every public user at launch) sees no added control.
  showScope?: boolean;
}

export function AccountsToolbar({ preferredCurrencies, showScope }: AccountsToolbarProps) {
  const t = useTranslations('accounts');
  const router = useRouter();
  const searchParams = useSearchParams();
  const { navigate } = useSearchParamsNavigation(ROUTES.accounts);
  const [createOpen, setCreateOpen] = useState(false);

  const scope = resolveListScope(searchParams.get('scope') ?? undefined);

  // 'all' clears the param rather than writing it, so the default view has a clean URL and a shared
  // link cannot pin somebody into a narrower list than they meant to send.
  function handleScopeChange(next: ListScope) {
    navigate({ scope: next === 'all' ? null : next });
  }

  return (
    <EntityListToolbar
      route={ROUTES.accounts}
      searchAriaLabel="Search accounts"
      searchPlaceholder={t('toolbar.searchPlaceholder')}
      showArchivedLabel={t('toolbar.showArchived')}
      addLabel={t('toolbar.add')}
      onAdd={() => setCreateOpen(true)}
      filters={showScope ? <ScopePill value={scope} onChange={handleScopeChange} /> : undefined}
    >
      <AccountFormDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        preferredCurrencies={preferredCurrencies}
        onSuccess={() => router.refresh()}
      />
    </EntityListToolbar>
  );
}
