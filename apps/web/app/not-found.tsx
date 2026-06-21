'use client';

import { useState } from 'react';
import { motion } from 'motion/react';
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

export default function NotFound() {
  const t = useTranslations('common.notFound');
  const [isRedirecting, setIsRedirecting] = useState(false);

  // Full navigation (not client-side routing) so the server resolves "/" itself: a logged-out
  // visitor lands on the marketing page, a logged-in visitor gets the landing's redirect to the app
  // as a 307 — no flash of the public shell that a soft `/` → `/dashboard` hop would paint.
  const goHome = () => {
    setIsRedirecting(true);
    window.location.assign(ROUTES.landing);
  };

  return (
    <div
      className="flex flex-col min-h-screen items-center justify-center px-6 gap-y-8"
      data-testid="not-found"
    >
      <div className="flex flex-col items-center gap-y-8">
        <motion.div {...BLOB_ANIMATION_PROPS}>
          <NotFoundBlob />
        </motion.div>
        <motion.div className="flex flex-col items-center gap-y-6" {...CONTENT_ANIMATION_PROPS}>
          <div className="flex flex-col items-center gap-y-3 text-center">
            <h1 className="text-heading-2 text-foreground">{t('title')}</h1>
            <p className="whitespace-pre-line text-paragraph text-muted-foreground">
              {t('description')}
            </p>
          </div>
          <Button blue size="lg" data-testid="not-found-home-cta" onClick={goHome}>
            {isRedirecting ? t('cta.loading') : t('cta.label')}
          </Button>
        </motion.div>
      </div>
    </div>
  );
}
