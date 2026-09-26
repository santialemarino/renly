import { PageSkeleton } from '@/app/(protected)/_components/page-skeleton';

export default function SubscriptionsLoading() {
  return <PageSkeleton namespace="subscriptions" toolbar body="table" />;
}
