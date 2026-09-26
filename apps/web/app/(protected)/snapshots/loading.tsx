import { PageSkeleton } from '@/app/(protected)/_components/page-skeleton';

export default function SnapshotsLoading() {
  return <PageSkeleton namespace="snapshots" toolbar body="table" />;
}
