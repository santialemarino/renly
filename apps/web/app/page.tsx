import { getTranslations } from 'next-intl/server';

export default async function Home() {
  const t = await getTranslations('home');

  return (
    <main className="flex min-h-full flex-col items-center justify-center p-8">
      <h1 className="text-2xl font-semibold text-foreground">{t('title')}</h1>
      <p className="mt-2 text-muted-foreground">{t('subtitle')}</p>
    </main>
  );
}
