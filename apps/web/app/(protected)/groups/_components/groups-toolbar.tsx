'use client';

import { useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Plus } from 'lucide-react';
import { LayoutGroup, motion } from 'motion/react';
import { useTranslations } from 'next-intl';

import { Button, SearchInput } from '@repo/ui/components';
import { GroupFormDialog } from '@/app/(protected)/groups/_components/group-form-dialog';
import { WarningHint } from '@/components/styled-hint';
import { ROUTES } from '@/config/routes';
import { ANIMATION_DEFAULT, DEBOUNCE_MS } from '@/lib/constants/animations';
import { useSearchParamsNavigation } from '@/lib/hooks/use-search-params-navigation';

interface GroupsToolbarProps {
  investments: { id: number; name: string }[];
  groupCount: number;
  maxGroups: number;
  groupWarningPct: number | null;
}

export function GroupsToolbar({
  investments,
  groupCount,
  maxGroups,
  groupWarningPct,
}: GroupsToolbarProps) {
  const t = useTranslations('groups');
  const router = useRouter();
  const searchParams = useSearchParams();
  const { navigate } = useSearchParamsNavigation(ROUTES.groups);
  const [createOpen, setCreateOpen] = useState(false);
  const [search, setSearch] = useState(searchParams.get('search') ?? '');

  const nearLimit = groupWarningPct !== null && groupCount >= maxGroups * (groupWarningPct / 100);
  const atLimit = groupCount >= maxGroups;

  useEffect(() => {
    const timer = setTimeout(() => navigate({ search }), DEBOUNCE_MS);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search]);

  return (
    <div className="flex flex-col gap-y-2">
      <LayoutGroup>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
          <motion.div
            layout
            transition={{ duration: ANIMATION_DEFAULT }}
            className="min-w-0 flex-1"
          >
            <SearchInput
              aria-label="Search groups"
              placeholder={t('toolbar.searchPlaceholder')}
              value={search}
              surface
              onChange={(e) => setSearch(e.target.value)}
              onClear={() => setSearch('')}
            />
          </motion.div>

          <motion.div layout transition={{ duration: ANIMATION_DEFAULT }}>
            <Button blue onClick={() => setCreateOpen(true)} disabled={atLimit}>
              <Plus className="size-4" />
              {t('toolbar.addGroup')}
            </Button>
          </motion.div>
        </div>
      </LayoutGroup>

      <WarningHint show={nearLimit && !atLimit} parentGap={8}>
        {t('softLimit.approaching', { count: groupCount, max: maxGroups })}
      </WarningHint>
      <WarningHint show={atLimit} parentGap={8}>
        {t('softLimit.reached', { max: maxGroups })}
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
