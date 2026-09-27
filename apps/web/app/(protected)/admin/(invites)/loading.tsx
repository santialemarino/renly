import { PageSkeleton } from '@/app/(protected)/_components/page-skeleton';

export default function AdminLoading() {
  return <PageSkeleton namespace="admin" body="table" />;
}
