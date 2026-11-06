import { PageSkeleton } from '@/app/(protected)/_components/page-skeleton';
import { DataSections } from '@/app/(protected)/data/_components/data-sections';

export default function DataLoading() {
  return <PageSkeleton namespace="data" body="page" content={<DataSections />} />;
}
