import { getTranslations } from 'next-intl/server';

import { HelpToc } from '@/app/(public)/_components/help-toc';
import { ProseSection, type ProseSectionData } from '@/app/(public)/_components/prose-section';

// Help sections always carry an anchor id (deep-link + ToC targets), unlike the legal pages'.
type HelpSectionData = ProseSectionData & { id: string };

// Renders the public help/FAQ page from the `help` translation namespace: a title, intro, a
// jump-to table of contents derived from the sections, then the anchored topic sections themselves.
export async function HelpPage() {
  const t = await getTranslations('help');
  const sections = t.raw('sections') as HelpSectionData[];

  return (
    <article className="flex flex-col w-full max-w-3xl self-center px-6 py-16 gap-y-8">
      <header className="flex flex-col gap-y-2">
        <h1 className="text-heading-2 text-neutral-950">{t('title')}</h1>
        <p className="text-paragraph text-muted-foreground">{t('intro')}</p>
      </header>
      <HelpToc
        label={t('tocLabel')}
        sections={sections.map((section) => ({ id: section.id, heading: section.heading }))}
      />
      {sections.map((section) => (
        <ProseSection key={section.id} {...section} />
      ))}
    </article>
  );
}
