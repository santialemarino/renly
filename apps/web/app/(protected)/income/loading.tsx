import { PageSkeleton } from '@/app/(protected)/_components/page-skeleton';

export default function IncomeLoading() {
  return (
    <PageSkeleton
      namespace="income"
      toolbar={{
        filters: [{ kind: 'filter', label: 'common.allCategories' }],
        actions: [{ kind: 'add', label: 'income.toolbar.addIncome' }],
      }}
      body="table"
    />
  );
}
