import { FileText, ShieldCheck, TriangleAlert } from 'lucide-react';
import { getTranslations } from 'next-intl/server';

import { InlineLink } from '@/components/inline-link';
import { SectionHeader } from '@/components/section-header';
import { ROUTES } from '@/config/routes';

// A secondary, in-app entry point to the legal pages — the public footer stays their canonical home.
// The links go to the public /privacy, /terms, /disclaimer routes (which render their own layout).
export async function AccountLegalSection() {
  const t = await getTranslations('account.legal');

  const links = [
    { href: ROUTES.privacy, label: t('privacy'), icon: ShieldCheck },
    { href: ROUTES.terms, label: t('terms'), icon: FileText },
    { href: ROUTES.disclaimer, label: t('disclaimer'), icon: TriangleAlert },
  ];

  return (
    <section className="flex flex-col gap-y-4">
      <SectionHeader title={t('title')} description={t('description')} />
      <nav aria-label={t('title')} className="flex flex-col items-start gap-y-3">
        {links.map((link) => (
          <InlineLink key={link.href} href={link.href} color="muted" icon={link.icon}>
            {link.label}
          </InlineLink>
        ))}
      </nav>
    </section>
  );
}
