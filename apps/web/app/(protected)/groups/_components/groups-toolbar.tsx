'use client';

import { useEffect, useRef, useState, useTransition } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Plus } from 'lucide-react';
import { useTranslations } from 'next-intl';

import { Button, SearchInput } from '@repo/ui/components';
import { GroupFormDialog } from '@/app/(protected)/groups/_components/group-form-dialog';
import { WarningHint } from '@/components/warning-hint';
import { ROUTES } from '@/config/routes';
import { DEBOUNCE_MS } from '@/lib/constants/animations';

interface GroupsToolbarProps {
  investments: { id: number; name: string }[];
  groupCount: number;
  maxGroups: number;
}

export function GroupsToolbar({ investments, groupCount, maxGroups }: GroupsToolbarProps) {
  const t = useTranslations('groups');
  const router = useRouter();
  const searchParams = useSearchParams();
  const searchParamsRef = useRef(searchParams);
  searchParamsRef.current = searchParams;

  const [, startTransition] = useTransition();
  const [createOpen, setCreateOpen] = useState(false);
  const [search, setSearch] = useState(searchParams.get('search') ?? '');

  const nearLimit = groupCount >= maxGroups * 0.8;
  const atLimit = groupCount >= maxGroups;

  function navigate(overrides: Record<string, string | null>) {
    const params = new URLSearchParams(searchParamsRef.current.toString());
    Object.entries(overrides).forEach(([key, val]) => {
      if (val === null || val === '') params.delete(key);
      else params.set(key, val);
    });
    startTransition(() => router.push(`${ROUTES.groups}?${params.toString()}`));
  }

  useEffect(() => {
    const timer = setTimeout(() => navigate({ search }), DEBOUNCE_MS);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search]);

  return (
    <div className="flex flex-col gap-y-2">
      <div className="@container flex flex-col gap-y-2 sm:flex-row sm:flex-wrap sm:items-center sm:gap-x-3">
        <SearchInput
          aria-label={t('toolbar.searchPlaceholder')}
          placeholder={t('toolbar.searchPlaceholder')}
          value={search}
          surface
          onChange={(e) => setSearch(e.target.value)}
          onClear={() => setSearch('')}
          containerClassName="w-full sm:flex-1"
        />

        <Button
          blue
          onClick={() => setCreateOpen(true)}
          disabled={atLimit}
          className="w-full sm:w-auto"
        >
          <Plus className="size-4" />
          {t('toolbar.addGroup')}
        </Button>
      </div>

      <WarningHint show={nearLimit}>
        {t('softLimit', { count: groupCount, max: maxGroups })}
      </WarningHint>

      <GroupFormDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        investments={investments}
        onSuccess={() => router.refresh()}
      />
    </div>
  );
}
