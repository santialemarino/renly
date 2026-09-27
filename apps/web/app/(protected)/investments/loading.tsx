import { PageSkeleton } from '@/app/(protected)/_components/page-skeleton';

export default function InvestmentsLoading() {
  return (
    <PageSkeleton
      namespace="investments"
      toolbar={{
        filters: [{ kind: 'filter', label: 'common.allCategories' }],
        actions: [
          { kind: 'pill', label: 'investments.toolbar.showArchived' },
          { kind: 'outline', label: 'investments.toolbar.import' },
          { kind: 'add', label: 'investments.toolbar.addInvestment' },
        ],
      }}
      body="table"
    />
  );
}
