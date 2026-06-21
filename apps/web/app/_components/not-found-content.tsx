'use client';

import { motion, useReducedMotion } from 'motion/react';
import { useTranslations } from 'next-intl';

import { Button } from '@repo/ui/components';
import { ROUTES } from '@/config/routes';
import { ANIMATION_DEFAULT, ANIMATION_SLOW } from '@/lib/constants/animations';
import NotFoundBlob from '@/public/icons/not-found-blob.svg';

const BLOB_ANIMATION_PROPS = {
  initial: { opacity: 0, y: 16 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: ANIMATION_SLOW, ease: 'easeOut' as const },
};

const CONTENT_ANIMATION_PROPS = {
  initial: { opacity: 0 },
  animate: { opacity: 1 },
  transition: { duration: ANIMATION_DEFAULT },
};

// Reduced motion: no entrance. We still render motion elements (not plain tags) so motion clears
// the opacity:0 it inlines during SSR — a plain element would leave the content hidden.
const STATIC_ANIMATION_PROPS = {
  initial: { opacity: 1, y: 0 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: 0 },
};

// Presentational 404 screen (animated blob + copy + CTAs). Logged-in visitors get a primary "Go to
// Dashboard" plus a secondary "Go to Homepage"; logged-out visitors get only "Go to Homepage" (the
// dashboard CTA would just bounce them to login). `isAuthenticated` is resolved on the server in
// not-found.tsx — this client component only needs it to pick the CTAs.
export function NotFoundContent({ isAuthenticated }: { isAuthenticated: boolean }) {
  const t = useTranslations('common.notFound');
  const tCommon = useTranslations('common');
  const reduced = useReducedMotion();
  const blobProps = reduced ? STATIC_ANIMATION_PROPS : BLOB_ANIMATION_PROPS;
  const contentProps = reduced ? STATIC_ANIMATION_PROPS : CONTENT_ANIMATION_PROPS;

  return (
    <div
      className="flex flex-col min-h-screen items-center justify-center px-6 gap-y-8"
      data-testid="not-found"
    >
      <div className="flex flex-col items-center gap-y-8">
        <motion.div {...blobProps}>
          <NotFoundBlob />
        </motion.div>
        <motion.div className="flex flex-col items-center gap-y-6" {...contentProps}>
          <div className="flex flex-col items-center gap-y-3 text-center">
            <h1 className="text-heading-2 text-foreground">{t('title')}</h1>
            <p className="whitespace-pre-line text-paragraph text-muted-foreground">
              {t('description')}
            </p>
          </div>
          <div className="flex flex-wrap items-center justify-center gap-x-3 gap-y-3">
            {isAuthenticated && (
              <Button asChild blue size="lg" data-testid="not-found-dashboard-cta">
                <a href={ROUTES.home}>{tCommon('goToDashboard')}</a>
              </Button>
            )}
            <Button
              asChild
              size="lg"
              data-testid="not-found-home-cta"
              {...(isAuthenticated ? { variant: 'outline' as const } : { blue: true })}
            >
              <a href={ROUTES.landing}>{t('cta.label')}</a>
            </Button>
          </div>
        </motion.div>
      </div>
    </div>
  );
}
