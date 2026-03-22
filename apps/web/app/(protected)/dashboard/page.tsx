import { getTranslations } from 'next-intl/server';

import { getSession } from '@/lib/auth';
import { generatePageMetadata } from '@/lib/utils/page-metadata';

export async function generateMetadata() {
  return await generatePageMetadata('dashboard');
}

export default async function DashboardPage() {
  const session = await getSession();
  const t = await getTranslations('dashboard');

  return (
    <div className="flex flex-col flex-1 items-center justify-center p-8 gap-y-2">
      <h1 className="text-heading-3 text-foreground">{t('title')}</h1>
      <p className="text-muted-foreground">
        {session?.user?.name
          ? t('subtitle.withName', { name: session?.user?.name })
          : t('subtitle.anonymous')}
      </p>
    </div>
  );
}
