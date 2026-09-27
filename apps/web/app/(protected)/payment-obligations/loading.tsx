import { PageSkeleton } from '@/app/(protected)/_components/page-skeleton';

export default function PaymentObligationsLoading() {
  return (
    <PageSkeleton
      namespace="paymentObligations"
      toolbar={{
        actions: [
          { kind: 'pill', label: 'paymentObligations.toolbar.showArchived' },
          { kind: 'add', label: 'paymentObligations.toolbar.add' },
        ],
      }}
      body="table"
    />
  );
}
