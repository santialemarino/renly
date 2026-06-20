import { getTranslations } from 'next-intl/server';

interface LegalSection {
  heading: string;
  paragraphs?: string[];
  items?: string[];
}

interface LegalPageProps {
  // Translation namespace holding the page's title, lastUpdated, intro, and sections.
  namespace: 'privacy' | 'terms' | 'disclaimer';
}

// Renders a structured legal/policy page (privacy, terms, disclaimer) from its translation
// namespace: a title, last-updated date, intro, then a list of heading + paragraphs/bullets.
export async function LegalPage({ namespace }: LegalPageProps) {
  const t = await getTranslations(namespace);
  const sections = t.raw('sections') as LegalSection[];

  return (
    <article className="flex flex-col w-full max-w-3xl self-center px-6 py-16 gap-y-8">
      <header className="flex flex-col gap-y-2">
        <h1 className="text-heading-2 text-neutral-950">{t('title')}</h1>
        <p className="text-paragraph-sm text-muted-foreground">{t('lastUpdated')}</p>
      </header>
      <p className="text-paragraph text-muted-foreground">{t('intro')}</p>
      {sections.map((section) => (
        <section key={section.heading} className="flex flex-col gap-y-3">
          <h2 className="text-heading-4 text-neutral-950">{section.heading}</h2>
          {section.paragraphs?.map((paragraph) => (
            <p key={paragraph.slice(0, 32)} className="text-paragraph-sm text-muted-foreground">
              {paragraph}
            </p>
          ))}
          {section.items && (
            <ul className="flex flex-col pl-5 gap-y-1 list-disc">
              {section.items.map((item) => (
                <li key={item.slice(0, 32)} className="text-paragraph-sm text-muted-foreground">
                  {item}
                </li>
              ))}
            </ul>
          )}
        </section>
      ))}
    </article>
  );
}
