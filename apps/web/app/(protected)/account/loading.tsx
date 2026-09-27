import { PageSkeleton } from '@/app/(protected)/_components/page-skeleton';

export default function AccountLoading() {
  return <PageSkeleton namespace="account" body="form" />;
}
