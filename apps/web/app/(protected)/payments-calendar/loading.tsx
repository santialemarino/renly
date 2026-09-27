import { PageSkeleton } from '@/app/(protected)/_components/page-skeleton';

export default function PaymentsCalendarLoading() {
  return <PageSkeleton namespace="paymentsCalendar" body="sections" />;
}
