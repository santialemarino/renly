import { getTranslations } from 'next-intl/server';

import { PageHeader } from '@/app/(protected)/_components/page-header';
import { DataSections } from '@/app/(protected)/data/_components/data-sections';
import { generatePageMetadata } from '@/lib/utils/page-metadata';

export async function generateMetadata() {
  return await generatePageMetadata('data');
}

interface DataPageProps {
  searchParams: Promise<{ type?: string }>;
}

export default async function DataPage({ searchParams }: DataPageProps) {
  const t = await getTranslations('data');
  const { type } = await searchParams;

  return (
    <div className="flex flex-col flex-1 items-start p-8 gap-y-4">
      <PageHeader title={t('title')} subtitle={t('subtitle')} />
      <DataSections initialType={type} />
    </div>
  );
}
