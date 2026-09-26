import { PageSkeleton } from '@/app/(protected)/_components/page-skeleton';

export default function AccountsLoading() {
  return <PageSkeleton namespace="accounts" toolbar body="table" />;
}
