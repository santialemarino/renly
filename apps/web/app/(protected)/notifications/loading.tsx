import { PageSkeleton } from '@/app/(protected)/_components/page-skeleton';

export default function NotificationsLoading() {
  return <PageSkeleton namespace="notifications" body="table" />;
}
