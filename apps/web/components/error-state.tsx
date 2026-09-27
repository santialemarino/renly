'use client';

import { useTransition } from 'react';
import { useRouter } from 'next/navigation';
import { RotateCw, TriangleAlert } from 'lucide-react';
import { useTranslations } from 'next-intl';

import { Button } from '@repo/ui/components';
import { cn } from '@repo/ui/lib';
import { ROUTES } from '@/config/routes';

interface ErrorStateProps {
  // The boundary's own `reset`, which re-renders the failed segment from what the router holds.
  reset: () => void;
  // Offers a way home too — for the boundaries that render OUTSIDE the app shell, where there is no nav.
  showHomeLink?: boolean;
  className?: string;
}

/*
 * What every error boundary renders: a translated explanation and a retry.
 *
 * The retry has to refresh the SERVER data, not only the boundary. `reset()` alone re-renders the
 * segment from the payload the router already holds — which, for a server component that threw, is
 * the error itself, so the same failure renders again however many times the user presses it.
 * `router.refresh()` asks the server for a fresh payload; `reset()` then clears the boundary so the
 * segment renders from it. Both run in one transition, so the boundary is only cleared once the new
 * payload has arrived, and the button stays disabled until it has.
 */
export function ErrorState({ reset, showHomeLink = false, className }: ErrorStateProps) {
  const t = useTranslations('common.errorBoundary');
  const router = useRouter();
  const [isPending, startTransition] = useTransition();

  const handleRetry = () => {
    startTransition(() => {
      router.refresh();
      reset();
    });
  };

  return (
    <div
      className={cn('flex flex-col flex-1 items-center justify-center p-8 gap-y-6', className)}
      data-testid="error-boundary"
    >
      <span className="grid size-12 shrink-0 place-items-center bg-muted rounded-full text-muted-foreground">
        <TriangleAlert className="size-6" />
      </span>
      <div className="flex flex-col max-w-md items-center gap-y-2 text-center">
        <h1 className="text-heading-3 text-foreground">{t('title')}</h1>
        <p className="text-paragraph text-muted-foreground">{t('description')}</p>
      </div>
      <div className="flex flex-wrap items-center justify-center gap-x-3 gap-y-3">
        <Button
          blue
          size="lg"
          onClick={handleRetry}
          disabled={isPending}
          data-testid="error-boundary-retry"
        >
          <RotateCw
            className={cn('size-4', isPending && 'animate-spin motion-reduce:animate-none')}
          />
          {t('retry')}
        </Button>
        {showHomeLink && (
          <Button asChild variant="outline" size="lg">
            <a href={ROUTES.landing}>{t('home')}</a>
          </Button>
        )}
      </div>
    </div>
  );
}
