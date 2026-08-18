import { Metadata } from 'next';
import { getTranslations } from 'next-intl/server';

import { OG_SITE_DEFAULTS, TWITTER_SITE_DEFAULTS } from '@/config/site';

/*
 * Per-page metadata from the page's `<namespace>.metadata` translations.
 *
 * `openGraph` and `twitter` are restated rather than left to inherit: Next merges only the keys a
 * page actually returns, and it REPLACES those two objects rather than merging them. Returning just
 * a description would leave the root layout's untranslated one on the social card — so the preview
 * would state something different, in a different language, from the page it previews — while
 * returning only a title and description would drop the site-level parts entirely.
 */
export async function generatePageMetadata(translationNamespace: string): Promise<Metadata> {
  const t = await getTranslations(`${translationNamespace}.metadata`);
  const title = t('title');
  const description = t('description');

  return {
    title,
    description,
    openGraph: { ...OG_SITE_DEFAULTS, title, description },
    twitter: { ...TWITTER_SITE_DEFAULTS, title, description },
  };
}
