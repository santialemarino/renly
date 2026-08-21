'use client';

import { useRouter, useSearchParams } from 'next/navigation';
import { Building2, FolderOpen, Tag } from 'lucide-react';
import { useLocale, useTranslations } from 'next-intl';

import { SmartSearch, type SmartSearchGroup } from '@/components/smart-search';
import { ROUTES } from '@/config/routes';
import type { InvestmentCollection } from '@/lib/api/collections';
import { sortCategoriesByLabel } from '@/lib/utils/categories';

const ICON_CLASS = 'size-4 shrink-0 text-muted-foreground';

// Group indices used by onSelect to determine the navigation target.
const GROUP_INVESTMENTS = 0;
const GROUP_COLLECTIONS = 1;
const GROUP_CATEGORIES = 2;

interface SearchableInvestment {
  id: number;
  name: string;
}

interface InvestorDashboardSearchProps {
  investments: SearchableInvestment[];
  collections: InvestmentCollection[];
}

export function InvestorDashboardSearch({
  investments,
  collections,
}: InvestorDashboardSearchProps) {
  const locale = useLocale();
  const t = useTranslations('investorDashboard');
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
      heading: t('search.collections'),
      items: collections.map((collection) => ({
        id: String(collection.id),
        label: collection.name,
        icon: <FolderOpen className={ICON_CLASS} />,
      })),
    },
    {
      heading: t('search.categories'),
      items: sortCategoriesByLabel(tCommon, locale).map((cat) => ({
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
    else if (groupIndex === GROUP_COLLECTIONS) qs.set('collection_id', itemId);
    else if (groupIndex === GROUP_CATEGORIES) qs.set('category', itemId);

    router.push(`${ROUTES.investorDashboard}?${qs.toString()}`, { scroll: false });
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
