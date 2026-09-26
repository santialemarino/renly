import { PageSkeleton } from '@/app/(protected)/_components/page-skeleton';

export default function SharedLoading() {
  return <PageSkeleton namespace="shared" toolbar body="table" />;
}
