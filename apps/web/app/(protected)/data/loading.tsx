import { PageSkeleton } from '@/app/(protected)/_components/page-skeleton';

export default function DataLoading() {
  return <PageSkeleton namespace="data" body="form" />;
}
