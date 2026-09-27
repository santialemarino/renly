import { PageSkeleton } from '@/app/(protected)/_components/page-skeleton';

export default function InstallmentsLoading() {
  return (
    <PageSkeleton
      namespace="installments"
      toolbar={{
        actions: [
          { kind: 'pill', label: 'installments.toolbar.showArchived' },
          { kind: 'add', label: 'installments.toolbar.add' },
        ],
      }}
      body="table"
    />
  );
}
