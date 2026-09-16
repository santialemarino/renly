import { notFound } from 'next/navigation';
import { getTranslations } from 'next-intl/server';

import { PageHeader } from '@/app/(protected)/_components/page-header';
import { AdminFeedback } from '@/app/(protected)/admin/feedback/_components/admin-feedback';
import { getFeedback } from '@/lib/api/feedback';
import { AdminForbiddenError } from '@/lib/api/types';
import { resolvePageParam } from '@/lib/list-scope';
import { generatePageMetadata } from '@/lib/utils/page-metadata';

export async function generateMetadata() {
  return await generatePageMetadata('adminFeedback');
}

interface AdminFeedbackPageProps {
  searchParams: Promise<{ page?: string }>;
}

export default async function AdminFeedbackPage({ searchParams }: AdminFeedbackPageProps) {
  const t = await getTranslations('adminFeedback');
  const query = await searchParams;

  // Admin-only (the API gates feedback reads on is_admin). A logged-in non-admin who reaches this
  // route gets a real 404 — hiding the page — rather than a 403; other errors surface normally.
  const feedback = await getFeedback(resolvePageParam(query.page)).catch((error) => {
    if (error instanceof AdminForbiddenError) return null;
    throw error;
  });
  if (feedback === null) notFound();

  return (
    <div className="flex flex-col flex-1 items-start p-8 gap-y-4">
      <PageHeader title={t('title')} subtitle={t('subtitle')} />
      <AdminFeedback
        feedback={feedback.items}
        total={feedback.total}
        page={resolvePageParam(query.page)}
        pageSize={feedback.pageSize}
      />
    </div>
  );
}
