import { PageSkeleton } from '@/app/(protected)/_components/page-skeleton';

export default function InvestmentsLoading() {
  return <PageSkeleton namespace="investments" toolbar body="table" />;
}
