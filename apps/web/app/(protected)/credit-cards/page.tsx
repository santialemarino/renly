import { getTranslations } from 'next-intl/server';

import { PageHeader } from '@/app/(protected)/_components/page-header';
import { CreditCardsTable } from '@/app/(protected)/credit-cards/_components/credit-cards-table';
import { CreditCardsToolbar } from '@/app/(protected)/credit-cards/_components/credit-cards-toolbar';
import { getCreditCards } from '@/lib/api/credit-cards';
import { getSettings } from '@/lib/api/settings';
import { generatePageMetadata } from '@/lib/utils/page-metadata';

export async function generateMetadata() {
  return await generatePageMetadata('creditCards');
}

interface CreditCardsPageProps {
  searchParams: Promise<{
    search?: string;
    sort_by?: string;
    sort_order?: string;
    show_archived?: string;
  }>;
}

export default async function CreditCardsPage({ searchParams }: CreditCardsPageProps) {
  const t = await getTranslations('creditCards');
  const params = await searchParams;

  const [cards, settings] = await Promise.all([
    getCreditCards({
      search: params.search,
      sortBy: params.sort_by as 'name' | 'closing_day' | 'due_day' | 'currency' | undefined,
      sortOrder: params.sort_order as 'asc' | 'desc' | undefined,
      showArchived: params.show_archived === 'true',
    }),
    getSettings().catch(() => null),
  ]);

  const preferredCurrencies = settings?.preferredCurrencies ?? undefined;

  // Teach the empty state only during first-run (before onboarding is completed) and only when no
  // filter is hiding existing rows — a returning user or a filtered-empty view gets the plain line.
  const hasActiveFilters = !!params.search || params.show_archived === 'true';
  const firstRun =
    cards.length === 0 && !hasActiveFilters && settings?.onboardingCompleted !== true;

  return (
    <div className="flex flex-col flex-1 p-8 gap-y-4">
      <PageHeader title={t('title')} subtitle={t('subtitle')} />
      <CreditCardsToolbar preferredCurrencies={preferredCurrencies} />
      <CreditCardsTable
        cards={cards}
        preferredCurrencies={preferredCurrencies}
        firstRun={firstRun}
      />
    </div>
  );
}
