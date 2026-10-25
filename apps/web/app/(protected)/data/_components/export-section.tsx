import { getTranslations } from 'next-intl/server';

import { ExportDataButton } from '@/components/export-data-button';
import { SectionHeader } from '@/components/section-header';

export async function ExportSection() {
  const t = await getTranslations('data');

  return (
    <section className="flex flex-col gap-y-4">
      <SectionHeader title={t('export.title')} description={t('export.description')} />
      <div className="flex items-center justify-between gap-x-4">
        <div className="flex flex-col">
          <span className="text-paragraph-sm-medium">{t('export.json.title')}</span>
          <span className="text-paragraph-xs text-muted-foreground">
            {t('export.json.description')}
          </span>
        </div>
        <ExportDataButton />
      </div>
    </section>
  );
}
