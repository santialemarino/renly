import { PageSkeleton } from '@/app/(protected)/_components/page-skeleton';

export default function LocalizationLoading() {
  return <PageSkeleton namespace="localization" body="form" />;
}
