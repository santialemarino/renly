import { Metadata } from 'next';
import { getTranslations } from 'next-intl/server';

export async function generatePageMetadata(translationNamespace: string): Promise<Metadata> {
  const t = await getTranslations(`${translationNamespace}.metadata`);

  return {
    title: t('title'),
    description: t('description'),
  };
}
