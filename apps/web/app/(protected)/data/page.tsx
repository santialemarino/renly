import { getTranslations } from 'next-intl/server';

import { Separator } from '@repo/ui/components';
import { PageHeader } from '@/app/(protected)/_components/page-header';
import { ExportSection } from '@/app/(protected)/data/_components/export-section';
import { ImportSection } from '@/app/(protected)/data/_components/import-section';
import { generatePageMetadata } from '@/lib/utils/page-metadata';

export async function generateMetadata() {
  return await generatePageMetadata('data');
}

export default async function DataPage() {
  const t = await getTranslations('data');

  return (
    <div className="flex flex-col flex-1 items-start p-8 gap-y-4">
      <PageHeader title={t('title')} subtitle={t('subtitle')} />
      <div className="flex flex-col w-full max-w-5xl gap-y-8">
        <ImportSection />
        <Separator />
        <ExportSection />
      </div>
    </div>
  );
}
