import { PageSkeleton } from '@/app/(protected)/_components/page-skeleton';

export default function CollectionsLoading() {
  return (
    <PageSkeleton
      namespace="collections"
      toolbar={{ actions: [{ kind: 'add', label: 'collections.toolbar.addCollection' }] }}
      body="table"
    />
  );
}
