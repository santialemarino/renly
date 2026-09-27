import { PageSkeleton } from '@/app/(protected)/_components/page-skeleton';

export default function SubscriptionsLoading() {
  return (
    <PageSkeleton
      namespace="subscriptions"
      toolbar={{
        actions: [
          { kind: 'pill', label: 'subscriptions.toolbar.showArchived' },
          { kind: 'add', label: 'subscriptions.toolbar.add' },
        ],
      }}
      body="table"
    />
  );
}
