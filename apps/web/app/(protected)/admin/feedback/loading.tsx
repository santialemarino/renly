import { PageSkeleton } from '@/app/(protected)/_components/page-skeleton';

export default function AdminFeedbackLoading() {
  return <PageSkeleton namespace="adminFeedback" body="table" />;
}
