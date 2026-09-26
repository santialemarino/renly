import { PageSkeleton } from '@/app/(protected)/_components/page-skeleton';

export default function InstallmentsLoading() {
  return <PageSkeleton namespace="installments" toolbar body="table" />;
}
