import { PageSkeleton } from '@/app/(protected)/_components/page-skeleton';

export default function PreferencesLoading() {
  return <PageSkeleton namespace="preferences" body="form" />;
}
