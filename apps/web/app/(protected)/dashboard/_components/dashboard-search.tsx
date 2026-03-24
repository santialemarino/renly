'use client';

import { useRouter, useSearchParams } from 'next/navigation';
import { Building2, FolderOpen, Tag } from 'lucide-react';
import { useTranslations } from 'next-intl';

import { INVESTMENT_CATEGORIES } from '@/app/(protected)/investments/investments-form-schema';
import { SmartSearch, type SmartSearchGroup } from '@/components/smart-search';
import { ROUTES } from '@/config/routes';
import type { InvestmentGroup } from '@/lib/api/investments';

const ICON_CLASS = 'size-4 shrink-0 text-muted-foreground';

// Group indices used by onSelect to determine the navigation target.
const GROUP_INVESTMENTS = 0;
const GROUP_GROUPS = 1;
const GROUP_CATEGORIES = 2;

interface SearchableInvestment {
  id: number;
  name: string;
}

interface DashboardSearchProps {
  investments: SearchableInvestment[];
  groups: InvestmentGroup[];
}

export function DashboardSearch({ investments, groups }: DashboardSearchProps) {
  const t = useTranslations('dashboard');
  const tCommon = useTranslations('common');
  const router = useRouter();

  const searchGroups: SmartSearchGroup[] = [
    {
      heading: t('search.investments'),
      items: investments.map((inv) => ({
        id: String(inv.id),
        label: inv.name,
        icon: <Building2 className={ICON_CLASS} />,
      })),
    },
    {
      heading: t('search.groups'),
      items: groups.map((group) => ({
        id: String(group.id),
        label: group.name,
        icon: <FolderOpen className={ICON_CLASS} />,
      })),
    },
    {
      heading: t('search.categories'),
      items: INVESTMENT_CATEGORIES.map((cat) => ({
        id: cat,
        label: tCommon(`categories.${cat}`),
        icon: <Tag className={ICON_CLASS} />,
      })),
    },
  ];

  const searchParams = useSearchParams();

  function handleSelect(groupIndex: number, itemId: string) {
    // Preserve existing date range params when navigating to a filter.
    const qs = new URLSearchParams();
    const period = searchParams.get('period');
    const startDate = searchParams.get('start_date');
    const endDate = searchParams.get('end_date');
    if (period) qs.set('period', period);
    if (startDate) qs.set('start_date', startDate);
    if (endDate) qs.set('end_date', endDate);

    if (groupIndex === GROUP_INVESTMENTS) qs.set('investment_id', itemId);
    else if (groupIndex === GROUP_GROUPS) qs.set('group_id', itemId);
    else if (groupIndex === GROUP_CATEGORIES) qs.set('category', itemId);

    router.push(`${ROUTES.dashboard}?${qs.toString()}`, { scroll: false });
  }

  return (
    <SmartSearch
      groups={searchGroups}
      placeholder={t('search.placeholder')}
      inputPlaceholder={t('search.inputPlaceholder')}
      emptyMessage={t('search.noResults')}
      onSelect={handleSelect}
      surface
    />
  );
}
