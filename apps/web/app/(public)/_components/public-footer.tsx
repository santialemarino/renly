import { getTranslations } from 'next-intl/server';

import { Separator } from '@repo/ui/components';
import { Brand } from '@/components/brand';
import { InlineLink } from '@/components/inline-link';
import { ROUTES } from '@/config/routes';

// Footer shared by the landing and legal pages: tagline, the "not financial advice" note,
// legal links, and the copyright line. A subtle tint plus the shared Separator set it apart from
// the page body.
export async function PublicFooter() {
  const t = await getTranslations('common.publicFooter');
  const tCommon = await getTranslations('common');

  const year = new Date().getFullYear();

  const links = [
    { href: ROUTES.help, label: t('links.help') },
    { href: ROUTES.privacy, label: t('links.privacy') },
    { href: ROUTES.terms, label: t('links.terms') },
    { href: ROUTES.disclaimer, label: t('links.disclaimer') },
  ];

  return (
    <footer className="flex flex-col w-full bg-muted/30">
      <Separator />
      <div className="flex flex-col w-full items-center px-6 py-8 gap-y-4">
        <div className="flex flex-col items-center gap-y-1 text-center">
          <Brand name={tCommon('appName')} size="sm" />
          <span className="text-paragraph-sm text-muted-foreground">{t('tagline')}</span>
        </div>
        <nav className="flex flex-wrap items-center justify-center gap-x-4 gap-y-2">
          {links.map((link) => (
            <InlineLink key={link.href} href={link.href} color="muted">
              {link.label}
            </InlineLink>
          ))}
        </nav>
        <p className="max-w-prose text-center text-paragraph-xs text-muted-foreground">
          {t('disclaimerShort')}
        </p>
        <p className="text-paragraph-xs text-muted-foreground">
          © {year} {tCommon('appName')}. {t('rights')}
        </p>
      </div>
    </footer>
  );
}
