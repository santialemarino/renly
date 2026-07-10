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

// Highlight-cutout rounding (px, ≈ Renly's --radius 0.625rem) and padding around the target.
const MODAL_OPENING_RADIUS = 10;
const MODAL_OPENING_PADDING = 6;

// Gap (px) between the highlighted region and the dialog. The tour drops Shepherd's arrow (which made
// the dialog read as stuck to the cutout) and instead floats the dialog off the target by this much.
const TOUR_DIALOG_GAP = 14;
// Min viewport margin (px) the dialog keeps when the gap is clamped near an edge.
const TOUR_VIEWPORT_MARGIN = 8;

// A floating-ui offset middleware pushing the dialog away from the target along the placement axis.
// Hand-written (Shepherd bundles floating-ui but doesn't re-export `offset`); the `{name, fn}` shape
// is the stable middleware contract. It runs after Shepherd's flip/shift (which can't re-contain a
// main-axis push), so the pushed coordinate is clamped to keep the dialog on-screen. Centered
// (unattached) steps have no placement — left untouched.
const dialogGapMiddleware = {
  name: 'renlyDialogGap',
  fn(state: {
    placement?: string;
    x: number;
    y: number;
    rects: { floating: { width: number; height: number } };
  }) {
    const side = state.placement?.split('-')[0];
    const m = TOUR_VIEWPORT_MARGIN;
    const { width, height } = state.rects.floating;
    if (side === 'top') return { y: Math.max(m, state.y - TOUR_DIALOG_GAP) };
    if (side === 'bottom')
      return { y: Math.min(window.innerHeight - height - m, state.y + TOUR_DIALOG_GAP) };
    if (side === 'left') return { x: Math.max(m, state.x - TOUR_DIALOG_GAP) };
    if (side === 'right')
      return { x: Math.min(window.innerWidth - width - m, state.x + TOUR_DIALOG_GAP) };
    return {};
  },
};

// Exit-animation duration (ms) — matches the `.renly-tour-leaving` transition in globals.css. On any
// transition we play this on the current dialog, then let Shepherd advance/close (it hides the
// tooltip instantly otherwise), and the incoming step fades+zooms in via `.shepherd-content`.
const TOUR_EXIT_MS = 200;

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
 * Skip, or Esc-disabled) persists completion via `onEnd` so it never auto-shows again; a teardown
 * (unmount, or the rebuild on replay) does NOT persist. Reduced motion collapses Shepherd's
 * transitions (handled in globals.css) and makes its scroll instant.
 */
export function useWelcomeTour({ autoStart, onEnd }: UseWelcomeTourOptions) {
  const translate = useTranslations('dashboard.tour');
  const reduce = useReducedMotion() ?? false;
  const tourRef = useRef<Tour | null>(null);
  // The current tour's un-wrapped `cancel`, used to tear it down instantly (no exit animation, no
  // persist) on a replay rebuild or unmount — the public `cancel` is wrapped to animate + persist.
  const rawCancelRef = useRef<(() => void) | null>(null);
  const exitTimerRef = useRef<number | undefined>(undefined);

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
    // down any lingering instance instantly (raw cancel — no animation, no persist).
    if (exitTimerRef.current) clearTimeout(exitTimerRef.current);
    if (tourRef.current) {
      rawCancelRef.current?.();
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
      // Only the ✕ (or Skip/Finish) ends the tour — not Esc, and the modal blocks outside-clicks.
      exitOnEsc: false,
      keyboardNavigation: true,
      defaultStepOptions: {
        classes: 'renly-tour',
        cancelIcon: { enabled: true, label: t('buttons.close') },
        canClickTarget: false,
        // No arrow — the dialog floats off the target (via the offset middleware below) with a clean
        // gap instead of a pointer stuck to the cutout.
        arrow: false,
        // Round + pad the highlight cutout so it echoes Renly's --radius and doesn't hug the target.
        modalOverlayOpeningRadius: MODAL_OPENING_RADIUS,
        modalOverlayOpeningPadding: MODAL_OPENING_PADDING,
        scrollTo: { behavior: reduce ? 'auto' : 'smooth', block: 'center' },
        floatingUIOptions: { middleware: [dialogGapMiddleware] },
      },
      steps,
    });

    /*
     * Shepherd hides/destroys a step's tooltip instantly (`el.hidden = true`), so there's no native
     * exit animation. Wrap the tour's own navigation so every transition — next/back and the closes
     * (cancel via ✕/Skip, complete via Finish) — first plays the leaving animation on the current
     * dialog, then performs the action; the incoming step then fades+zooms in via `.shepherd-content`.
     */
    const raw = {
      next: tour.next.bind(tour),
      back: tour.back.bind(tour),
      cancel: tour.cancel.bind(tour),
      complete: tour.complete.bind(tour),
    };
    rawCancelRef.current = raw.cancel;
    // After a close tears the tour down, drop the refs so the unmount cleanup doesn't re-cancel an
    // already-finished tour.
    const forget = () => {
      tourRef.current = null;
      rawCancelRef.current = null;
    };
    const withExit = (perform: () => void, closing = false) => {
      if (exitTimerRef.current) clearTimeout(exitTimerRef.current);
      const el = document.querySelector<HTMLElement>('.shepherd-element:not([hidden])');
      if (reduce || !el) {
        perform();
        if (closing) forget();
        return;
      }
      el.classList.add('renly-tour-leaving');
      // On a close (not a step change), fade the dim overlay out alongside the dialog — Shepherd
      // tears it down instantly otherwise.
      const overlay = closing ? document.querySelector('.shepherd-modal-overlay-container') : null;
      overlay?.classList.add('renly-tour-overlay-leaving');
      exitTimerRef.current = window.setTimeout(() => {
        exitTimerRef.current = undefined;
        perform();
        el.classList.remove('renly-tour-leaving'); // reset for a re-show (Shepherd reuses step els)
        overlay?.classList.remove('renly-tour-overlay-leaving');
        if (closing) forget();
      }, TOUR_EXIT_MS);
    };
    /*
     * Persist "tour seen" the moment the user finishes or skips/closes — eagerly, not behind the exit
     * animation — so navigating away within the exit window can't drop it. Idempotent per tour. The
     * raw-cancel teardown paths (replay rebuild, unmount) never call this, so they don't persist. A
     * failed persist is surfaced (the tour will re-offer next load), mirroring the welcome dismiss.
     */
    let persisted = false;
    const persist = () => {
      if (persisted) return;
      persisted = true;
      void Promise.resolve(onEndRef.current()).catch(() => toast.error(t('saveError')));
    };
    tour.next = () => withExit(raw.next);
    tour.back = () => withExit(raw.back);
    tour.cancel = () => {
      persist();
      withExit(raw.cancel, true);
      return Promise.resolve();
    };
    tour.complete = () => {
      persist();
      withExit(raw.complete, true);
    };

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

  // Tear down Shepherd's DOM if the page unmounts mid-tour, instantly and without persisting (raw
  // cancel), and cancel any pending exit timer so no deferred step change fires on a dead tour.
  useEffect(() => {
    return () => {
      if (exitTimerRef.current) clearTimeout(exitTimerRef.current);
      rawCancelRef.current?.();
    };
  }, []);

  return { start };
}
