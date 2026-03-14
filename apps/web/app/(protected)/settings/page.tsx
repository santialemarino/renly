import { getTranslations } from 'next-intl/server';

import { generatePageMetadata } from '@/lib/utils/page';

export async function generateMetadata() {
  return await generatePageMetadata('settings');
}

export default async function SettingsPage() {
  const t = await getTranslations('settings');

  return (
    <main className="flex flex-col min-h-full items-center justify-center p-8 gap-y-2">
      <h1 className="text-heading-3 text-foreground">{t('title')}</h1>
      <p className="text-muted-foreground">{t('subtitle')}</p>
    </main>
  );
}
