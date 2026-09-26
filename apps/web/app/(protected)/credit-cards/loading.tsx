import { PageSkeleton } from '@/app/(protected)/_components/page-skeleton';

export default function CreditCardsLoading() {
  return <PageSkeleton namespace="creditCards" toolbar body="table" />;
}
