import { PageSkeleton } from '@/app/(protected)/_components/page-skeleton';

export default function ExpensesLoading() {
  return <PageSkeleton namespace="expenses" toolbar body="table" />;
}
