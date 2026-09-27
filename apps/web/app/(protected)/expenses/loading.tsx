import { PageSkeleton } from '@/app/(protected)/_components/page-skeleton';

export default function ExpensesLoading() {
  return (
    <PageSkeleton
      namespace="expenses"
      toolbar={{
        filters: [
          { kind: 'filter', label: 'common.allCategories' },
          { kind: 'filter', label: 'expenses.toolbar.allPaymentMethods' },
        ],
        actions: [{ kind: 'add', label: 'expenses.toolbar.addExpense' }],
      }}
      body="table"
    />
  );
}
