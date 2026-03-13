import { getTranslations } from 'next-intl/server';

import { generatePageMetadata } from '@/lib/utils/page';

export async function generateMetadata() {
  return await generatePageMetadata('investments');
}

export default async function InvestmentsPage() {
  const t = await getTranslations('investments');

  return (
    <main className="flex flex-col min-h-full items-center justify-center p-8 gap-y-2">
      <h1 className="text-2xl font-semibold text-foreground">{t('title')}</h1>
      <p className="text-muted-foreground">{t('subtitle')}</p>
    </main>
  );
}
