import { PageSkeleton } from '@/app/(protected)/_components/page-skeleton';

export default function DashboardLoading() {
  return <PageSkeleton namespace="dashboard" periodPicker body="dashboard" />;
}
