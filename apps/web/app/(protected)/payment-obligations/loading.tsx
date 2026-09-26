import { PageSkeleton } from '@/app/(protected)/_components/page-skeleton';

export default function PaymentObligationsLoading() {
  return <PageSkeleton namespace="paymentObligations" toolbar body="table" />;
}
