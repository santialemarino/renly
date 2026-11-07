'use client';

import { useEffect, useRef, useTransition } from 'react';
import { useRouter } from 'next/navigation';

import { useNavigationPending } from '@/lib/hooks/use-navigation-pending';

type NavigateOptions = Parameters<ReturnType<typeof useRouter>['push']>[1];

/*
 * `router.push` / `router.replace` for code that navigates without a link click (a wizard's next step,
 * a delete that leaves the page, a filter or period written to the URL). A link click is seen by the
 * shell itself; a programmatic navigation is not, so it goes through here to get the same feedback: the
 * destination active in the nav at once and, past the delay, the progress bar (and the dimmed page,
 * when it changes page). It runs in a transition, and `isPending` is that transition, for a control
 * that should also show it.
 *
 * A navigation whose transition ends without moving the URL is settled here, so its feedback never
 * outlives it.
 */
export function usePendingRouter() {
  const router = useRouter();
  const { begin, settle } = useNavigationPending();
  const [isPending, startTransition] = useTransition();
  const started = useRef<number[]>([]);

  useEffect(() => {
    if (isPending || started.current.length === 0) return;
    for (const id of started.current) settle(id);
    started.current = [];
  }, [isPending, settle]);

  function navigate(method: 'push' | 'replace', href: string, options?: NavigateOptions) {
    started.current.push(begin(href));
    startTransition(() => router[method](href, options));
  }

  return {
    push: (href: string, options?: NavigateOptions) => navigate('push', href, options),
    replace: (href: string, options?: NavigateOptions) => navigate('replace', href, options),
    isPending,
  };
}
