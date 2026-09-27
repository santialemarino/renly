import { PageSkeleton } from '@/app/(protected)/_components/page-skeleton';

export default function SnapshotsLoading() {
  return (
    <PageSkeleton
      namespace="snapshots"
      toolbar={{
        filters: [
          {
            kind: 'segmented',
            labels: ['snapshots.toolbar.interval.monthly', 'snapshots.toolbar.interval.weekly'],
          },
          { kind: 'filter', label: 'common.allCategories' },
        ],
        actions: [{ kind: 'outline', label: 'snapshots.toolbar.refresh', smallIcon: true }],
      }}
      body="table"
    />
  );
}
