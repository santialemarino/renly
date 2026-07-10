'use client';

import { useCallback, useEffect, useRef } from 'react';
import { useReducedMotion } from 'motion/react';
import { useTranslations } from 'next-intl';
import Shepherd from 'shepherd.js';
import type { StepOptions, Tour } from 'shepherd.js';

// Shepherd's base CSS + the Renly theme overrides are loaded/scoped in app/globals.css (imported
// there so the base rules always precede the overrides — a client-component import would load after
// the root stylesheet and lose the cascade). Nothing to import here.

// data-testid anchors the tour attaches to (shared with the E2E convention) — kept in one place so a
// renamed testid updates both the tour and any spec. The welcome step is unattached (centered).
const TOUR_ANCHORS = {
  metrics: '[data-testid="dashboard-metrics"]',
  checklist: '[data-testid="onboarding-welcome"]',
  navigation: '[data-testid="sidebar-nav"]',
  currency: '[data-testid="currency-switcher"]',
} as const;

interface UseWelcomeTourOptions {
  // Auto-start once on mount for a first-run newcomer.
  autoStart: boolean;
  // Persist "tour seen" (finish or skip). Never called for a teardown on unmount.
  onEnd: () => void | Promise<void>;
}

/*
 * Owns the Shepherd welcome-tour lifecycle: builds the themed 5-step tour, auto-starts it once for a
 * first-run newcomer, and exposes `start` for the manual replay link. Finishing OR skipping/closing
 * (the ✕, Skip, or Esc) persists completion via `onEnd` so it never auto-shows again; tearing down on
 * unmount (e.g. navigating away mid-tour) does NOT persist. Reduced motion collapses Shepherd's
 * transitions (handled in globals.css) and makes its scroll instant.
 */
export function useWelcomeTour({ autoStart, onEnd }: UseWelcomeTourOptions) {
  const translate = useTranslations('dashboard.tour');
  const reduce = useReducedMotion() ?? false;
  const tourRef = useRef<Tour | null>(null);
  const unmountingRef = useRef(false);

  // Latest values held in refs so `start` stays referentially stable (deps []). That keeps the
  // auto-start effect from re-running — and re-launching the tour — when a render changes the
  // translation/callback identity mid-session.
  const tRef = useRef(translate);
  const reduceRef = useRef(reduce);
  const onEndRef = useRef(onEnd);
  tRef.current = translate;
  reduceRef.current = reduce;
  onEndRef.current = onEnd;

  const start = useCallback(() => {
    const t = tRef.current;
    const reduce = reduceRef.current;
    // A completed Shepherd tour can't be replayed in place, so build a fresh one each start; tear
    // down any lingering instance first, silently (the guard keeps that teardown from persisting).
    if (tourRef.current) {
      tourRef.current.cancel();
      tourRef.current = null;
    }

    const back = {
      text: t('buttons.back'),
      secondary: true,
      action(this: Tour) {
        this.back();
      },
    };
    const next = {
      text: t('buttons.next'),
      action(this: Tour) {
        this.next();
      },
    };
    const skip = {
      text: t('buttons.skip'),
      secondary: true,
      action(this: Tour) {
        this.cancel();
      },
    };
    const finish = {
      text: t('buttons.finish'),
      action(this: Tour) {
        this.complete();
      },
    };

    const steps: StepOptions[] = [
      {
        id: 'welcome',
        title: t('steps.welcome.title'),
        text: t('steps.welcome.text'),
        buttons: [skip, next],
      },
      {
        id: 'metrics',
        title: t('steps.metrics.title'),
        text: t('steps.metrics.text'),
        attachTo: { element: TOUR_ANCHORS.metrics, on: 'bottom' },
        buttons: [back, next],
      },
      {
        id: 'checklist',
        title: t('steps.checklist.title'),
        text: t('steps.checklist.text'),
        attachTo: { element: TOUR_ANCHORS.checklist, on: 'bottom' },
        buttons: [back, next],
      },
      {
        id: 'navigation',
        title: t('steps.navigation.title'),
        text: t('steps.navigation.text'),
        attachTo: { element: TOUR_ANCHORS.navigation, on: 'right' },
        buttons: [back, next],
      },
      {
        id: 'currency',
        title: t('steps.currency.title'),
        text: t('steps.currency.text'),
        attachTo: { element: TOUR_ANCHORS.currency, on: 'right' },
        buttons: [back, finish],
      },
    ];

    const tour = new Shepherd.Tour({
      useModalOverlay: true,
      exitOnEsc: true,
      keyboardNavigation: true,
      defaultStepOptions: {
        classes: 'renly-tour',
        cancelIcon: { enabled: true, label: t('buttons.skip') },
        canClickTarget: false,
        scrollTo: { behavior: reduce ? 'auto' : 'smooth', block: 'center' },
      },
      steps,
    });

    // Both a finish and a skip/close end the tour for good; the unmount guard suppresses the
    // teardown-triggered cancel so leaving the page mid-tour doesn't mark it seen.
    const handleEnd = () => {
      if (unmountingRef.current) return;
      void Promise.resolve(onEndRef.current()).catch(() => {});
    };
    tour.on('complete', handleEnd);
    tour.on('cancel', handleEnd);

    tourRef.current = tour;
    void tour.start();
  }, []);

  // Auto-start on the next frame (so the anchors are laid out) for a first-run newcomer. The rAF is
  // cancelled on cleanup, so React's dev Strict-Mode mount→cleanup→mount simply reschedules and
  // fires once; `start` is stable so this never re-fires mid-session. `start()` cancels any live
  // tour first, so a manual replay can't double up either.
  useEffect(() => {
    if (!autoStart) return;
    const raf = requestAnimationFrame(() => start());
    return () => cancelAnimationFrame(raf);
  }, [autoStart, start]);

  // Tear down Shepherd's DOM if the page unmounts mid-tour, without persisting completion. Reset the
  // flag on (re)mount so React's dev Strict-Mode mount→cleanup→mount cycle doesn't leave it stuck
  // true — which would make every real finish/skip bail out of persisting.
  useEffect(() => {
    unmountingRef.current = false;
    return () => {
      unmountingRef.current = true;
      tourRef.current?.cancel();
    };
  }, []);

  return { start };
}
