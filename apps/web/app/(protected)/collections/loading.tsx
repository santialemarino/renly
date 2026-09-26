import { PageSkeleton } from '@/app/(protected)/_components/page-skeleton';

export default function CollectionsLoading() {
  return <PageSkeleton namespace="collections" toolbar body="table" />;
}
