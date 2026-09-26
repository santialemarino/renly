import { PageSkeleton } from '@/app/(protected)/_components/page-skeleton';

export default function FinanceDashboardLoading() {
  return <PageSkeleton namespace="financeDashboard" body="dashboard" />;
}
