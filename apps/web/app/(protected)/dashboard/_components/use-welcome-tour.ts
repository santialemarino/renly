'use client';

import { useCallback, useEffect, useRef } from 'react';
import { useReducedMotion } from 'motion/react';
import { useTranslations } from 'next-intl';
import Shepherd from 'shepherd.js';
import type { StepOptions, Tour } from 'shepherd.js';
import { toast } from 'sonner';

// Shepherd's base CSS + the Renly theme overrides are loaded/scoped in app/globals.css (imported
// there so the base rules always precede the overrides — a client-component import would load after
// the root stylesheet and lose the cascade). Nothing to import here.

/*
 * Ordered step blueprint. `element` is the anchor's data-testid selector (shared with the E2E
 * convention); the welcome step is unattached (centered). A step whose anchor isn't in the DOM when
 * the tour starts is dropped — on mobile the sidebar lives in a closed, unmounted Radix Sheet, so
 * its `navigation`/`currency` steps would otherwise render as centered dialogs pointing at nothing.
 * Buttons are assigned by final position after filtering, so the last surviving step always finishes.
 */
const STEP_BLUEPRINT = [
  { id: 'welcome' },
  { id: 'metrics', element: '[data-testid="dashboard-metrics"]', on: 'bottom' },
  { id: 'checklist', element: '[data-testid="onboarding-welcome"]', on: 'bottom' },
  { id: 'navigation', element: '[data-testid="sidebar-nav"]', on: 'right' },
  { id: 'currency', element: '[data-testid="currency-switcher"]', on: 'right' },
] as const;

interface UseWelcomeTourOptions {
  // Auto-start once on mount for a first-run newcomer.
  autoStart: boolean;
  // Persist "tour seen" (finish or skip). Never called for a teardown (unmount or replay rebuild).
  onEnd: () => void | Promise<void>;
}

/*
 * Owns the Shepherd welcome-tour lifecycle: builds the themed tour (up to 5 steps; steps whose anchor
 * isn't rendered — e.g. the sidebar on mobile — are dropped), auto-starts it once for a first-run
 * newcomer, and exposes `start` for the manual replay link. Finishing OR skipping/closing (the ✕,
 * Skip, or Esc) persists completion via `onEnd` so it never auto-shows again; a teardown (unmount, or
 * the rebuild on replay) does NOT persist. Reduced motion collapses Shepherd's transitions (handled
 * in globals.css) and makes its scroll instant.
 */
export function useWelcomeTour({ autoStart, onEnd }: UseWelcomeTourOptions) {
  const translate = useTranslations('dashboard.tour');
  const reduce = useReducedMotion() ?? false;
  const tourRef = useRef<Tour | null>(null);
  // Suppresses the persist that Shepherd's `cancel` event fires when WE tear a tour down (on unmount,
  // or when a replay rebuilds a lingering one) — as opposed to a genuine user finish/skip.
  const suppressPersistRef = useRef(false);

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
    // down any lingering instance first, suppressing its cancel-triggered persist.
    if (tourRef.current) {
      suppressPersistRef.current = true;
      tourRef.current.cancel();
      suppressPersistRef.current = false;
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

    // Keep only steps whose anchor is actually rendered, then assign buttons by final position
    // (first: Skip/Next · middle: Back/Next · last: Back/Finish · sole: Finish).
    const present = STEP_BLUEPRINT.filter(
      (s) => !('element' in s) || document.querySelector(s.element),
    );
    const lastIndex = present.length - 1;
    const steps: StepOptions[] = present.map((s, i) => {
      const lead = i === 0 ? skip : back;
      const trail = i === lastIndex ? finish : next;
      return {
        id: s.id,
        title: t(`steps.${s.id}.title`),
        text: t(`steps.${s.id}.text`),
        ...('element' in s ? { attachTo: { element: s.element, on: s.on } } : {}),
        buttons: i === 0 && i === lastIndex ? [finish] : [lead, trail],
      };
    });

    const tour = new Shepherd.Tour({
      useModalOverlay: true,
      exitOnEsc: true,
      keyboardNavigation: true,
      defaultStepOptions: {
        classes: 'renly-tour',
        cancelIcon: { enabled: true, label: t('buttons.close') },
        canClickTarget: false,
        scrollTo: { behavior: reduce ? 'auto' : 'smooth', block: 'center' },
      },
      steps,
    });

    // Both a finish and a skip/close end the tour for good; the suppress guard skips our own teardown
    // cancels. A failed persist is surfaced (and the tour will re-offer next load), mirroring the
    // welcome card's dismiss.
    const handleEnd = () => {
      if (suppressPersistRef.current) return;
      void Promise.resolve(onEndRef.current()).catch(() => toast.error(t('saveError')));
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
  // suppress flag on (re)mount so React's dev Strict-Mode mount→cleanup→mount cycle doesn't leave it
  // stuck true — which would make every real finish/skip bail out of persisting.
  useEffect(() => {
    suppressPersistRef.current = false;
    return () => {
      suppressPersistRef.current = true;
      tourRef.current?.cancel();
    };
  }, []);

  return { start };
}
