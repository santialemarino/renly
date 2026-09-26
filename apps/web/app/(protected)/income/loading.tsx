import { PageSkeleton } from '@/app/(protected)/_components/page-skeleton';

export default function IncomeLoading() {
  return <PageSkeleton namespace="income" toolbar body="table" />;
}
