import { getTranslations } from 'next-intl/server';

import { ProseSection, type ProseSectionData } from '@/app/(public)/_components/prose-section';

interface LegalPageProps {
  // Translation namespace holding the page's title, lastUpdated, intro, and sections.
  namespace: 'privacy' | 'terms' | 'disclaimer';
}

// Renders a structured legal/policy page (privacy, terms, disclaimer) from its translation
// namespace: a title, last-updated date, intro, then a list of heading + paragraphs/bullets.
export async function LegalPage({ namespace }: LegalPageProps) {
  const t = await getTranslations(namespace);
  const sections = t.raw('sections') as ProseSectionData[];

  return (
    <article className="flex flex-col w-full max-w-3xl self-center px-6 py-16 gap-y-8">
      <header className="flex flex-col gap-y-2">
        <h1 className="text-heading-2 text-neutral-950">{t('title')}</h1>
        <p className="text-paragraph-sm text-muted-foreground">{t('lastUpdated')}</p>
      </header>
      <p className="text-paragraph text-muted-foreground">{t('intro')}</p>
      {sections.map((section) => (
        <ProseSection
          key={section.heading}
          heading={section.heading}
          paragraphs={section.paragraphs}
          items={section.items}
        />
      ))}
    </article>
  );
}
