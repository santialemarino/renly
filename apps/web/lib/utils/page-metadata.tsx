import { Metadata } from 'next';
import { getTranslations } from 'next-intl/server';

/*
 * Per-page metadata from the page's `<namespace>.metadata` translations.
 *
 * `openGraph` and `twitter` are restated rather than left to inherit: Next merges only the keys a
 * page actually returns, so a page that set `description` alone would keep the root layout's
 * untranslated OG/Twitter description — and its link preview would then state something different,
 * in a different language, from the page it previews.
 */
export async function generatePageMetadata(translationNamespace: string): Promise<Metadata> {
  const t = await getTranslations(`${translationNamespace}.metadata`);
  const title = t('title');
  const description = t('description');

  return {
    title,
    description,
    openGraph: { title, description },
    twitter: { title, description },
  };
}
