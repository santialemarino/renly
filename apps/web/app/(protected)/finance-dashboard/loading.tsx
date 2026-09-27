import { PageSkeleton } from '@/app/(protected)/_components/page-skeleton';

export default function FinanceDashboardLoading() {
  return <PageSkeleton namespace="financeDashboard" periodPicker="header" body="dashboard" />;
}
