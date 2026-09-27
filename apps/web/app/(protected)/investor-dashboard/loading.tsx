import { PageSkeleton } from '@/app/(protected)/_components/page-skeleton';

export default function InvestorDashboardLoading() {
  return (
    <PageSkeleton
      namespace="investorDashboard"
      subtitleIsData
      periodPicker="toolbar"
      currencyFallback="investorDashboard.currencyFallback"
      body="dashboard"
    />
  );
}
