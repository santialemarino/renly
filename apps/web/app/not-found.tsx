'use client';

import { useTransition } from 'react';
import { useRouter } from 'next/navigation';
import { motion } from 'motion/react';
import { useTranslations } from 'next-intl';
import NotFoundBlob from 'public/icons/not-found-blob.svg';

import { Button } from '@repo/ui/components';
import { ROUTES } from '@/config/routes';
import { ANIMATION_DEFAULT, ANIMATION_SLOW } from '@/lib/constants/animations';

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
  const router = useRouter();
  const [isPending, startTransition] = useTransition();

  return (
    <div className="flex flex-col min-h-screen items-center justify-center px-6 gap-y-8">
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
          <Button blue size="lg" onClick={() => startTransition(() => router.replace(ROUTES.home))}>
            {isPending ? t('cta.loading') : t('cta.label')}
          </Button>
        </motion.div>
      </div>
    </div>
  );
}
