import { PageSkeleton } from '@/app/(protected)/_components/page-skeleton';

export default function CreditCardsLoading() {
  return (
    <PageSkeleton
      namespace="creditCards"
      toolbar={{
        actions: [
          { kind: 'pill', label: 'creditCards.toolbar.showArchived' },
          { kind: 'add', label: 'creditCards.toolbar.addCard' },
        ],
      }}
      body="table"
    />
  );
}
