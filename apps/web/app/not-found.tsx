'use client';

import { useTransition } from 'react';
import { useRouter } from 'next/navigation';
import { motion } from 'motion/react';
import { useTranslations } from 'next-intl';
import NotFoundBlob from 'public/icons/not-found-blob.svg';

import { Button } from '@repo/ui/components';
import { ROUTES } from '@/config/routes';

const BLOB_ANIMATION_PROPS = {
  initial: { opacity: 0, y: 16 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: 0.5, ease: 'easeOut' as const },
};

const CONTENT_ANIMATION_PROPS = {
  initial: { opacity: 0 },
  animate: { opacity: 1 },
  transition: { duration: 0.25 },
};

export default function NotFound() {
  const t = useTranslations('common.notFound');
  const router = useRouter();
  const [isPending, startTransition] = useTransition();

  return (
    <div className="flex flex-col min-h-screen items-center justify-center px-6 gap-y-8 bg-muted/30">
      <div className="flex flex-col items-center gap-y-8">
        <motion.div {...BLOB_ANIMATION_PROPS}>
          <NotFoundBlob />
        </motion.div>
        <motion.div className="flex flex-col items-center gap-y-6" {...CONTENT_ANIMATION_PROPS}>
          <div className="flex flex-col items-center gap-y-3 text-center">
            <h1 className="text-3xl font-bold leading-tight text-foreground">{t('title')}</h1>
            <p className="whitespace-pre-line text-base text-muted-foreground">
              {t('description')}
            </p>
          </div>
          <Button blue size="lg" onClick={() => startTransition(() => router.replace(ROUTES.home))}>
            {isPending ? t('goHomepage.loading') : t('goHomepage.cta')}
          </Button>
        </motion.div>
      </div>
    </div>
  );
}
