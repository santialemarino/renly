import { PageSkeleton } from '@/app/(protected)/_components/page-skeleton';

export default function AccountsLoading() {
  return (
    <PageSkeleton
      namespace="accounts"
      toolbar={{
        actions: [
          { kind: 'pill', label: 'accounts.toolbar.showArchived' },
          { kind: 'add', label: 'accounts.toolbar.add' },
        ],
      }}
      body="table"
    />
  );
}
