'use client';

import { ArrowLeft, Check } from 'lucide-react';
import { AnimatePresence, motion } from 'motion/react';

import { Button } from '@repo/ui/components';
import { cn } from '@repo/ui/lib';
import { PageHeader } from '@/app/(protected)/_components/page-header';
import { InlineLink } from '@/components/inline-link';
import { ANIMATION_DEFAULT } from '@/lib/constants/animations';

interface WizardShellProps {
  title: string;
  subtitle: string;
  // Where leaving the flow goes back to, and what that place is called.
  exitHref: string;
  exitLabel: string;
  // The step labels in order, and which one is active. Null hides the indicator, which is what the
  // closing panel wants: it is not a step to be part-way through.
  steps: string[];
  current: number | null;
  // Keys the crossfade. Distinct from `current` because the closing panel is not one of the steps.
  stageKey: string;
  onBack?: () => void;
  backLabel: string;
  primary?: { label: string; loadingLabel: string; onClick: () => void; disabled?: boolean };
  pending?: boolean;
  children: React.ReactNode;
}

/*
 * The frame every guided flow in the Shared module renders inside: where you are, one panel at a
 * time, and the way forward and back.
 *
 * These are ROUTES rather than dialogs, which is what makes them resumable — each flow derives which
 * step it opens on from what the server says already exists, so closing the tab half-way through
 * loses nothing but the current keystrokes. A dialog would have nowhere to land after a step that had
 * already written.
 *
 * The panels crossfade on opacity only, per the app surface's calm-motion rule and matching the
 * import flow's step swap. Nothing translates or scales: a panel that slid would draw attention to
 * the mechanism rather than to what changed.
 */
export function WizardShell({
  title,
  subtitle,
  exitHref,
  exitLabel,
  steps,
  current,
  stageKey,
  onBack,
  backLabel,
  primary,
  pending = false,
  children,
}: WizardShellProps) {
  return (
    <div className="flex flex-col flex-1 p-8 gap-y-6">
      <InlineLink href={exitHref} color="muted" icon={ArrowLeft}>
        {exitLabel}
      </InlineLink>
      <PageHeader title={title} subtitle={subtitle} />

      {current !== null && <StepIndicator steps={steps} current={current} />}

      {/*
       * `mode="wait"` so the outgoing panel finishes before the next arrives — two panels of
       * different heights fading through each other would make the page jump twice.
       */}
      <AnimatePresence mode="wait" initial={false}>
        <motion.div
          key={stageKey}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: ANIMATION_DEFAULT }}
          className="flex flex-col min-w-0 max-w-2xl gap-y-6"
        >
          {children}
        </motion.div>
      </AnimatePresence>

      {(onBack || primary) && (
        <div className="flex flex-wrap max-w-2xl items-center justify-between gap-x-3 gap-y-2">
          {/* The span keeps the primary hard right on the first step, where there is no back. */}
          {onBack ? (
            <Button variant="outline" onClick={onBack} disabled={pending}>
              {backLabel}
            </Button>
          ) : (
            <span />
          )}
          {primary && (
            <Button blue onClick={primary.onClick} disabled={pending || primary.disabled}>
              {pending ? primary.loadingLabel : primary.label}
            </Button>
          )}
        </div>
      )}
    </div>
  );
}

/*
 * One step's panel: its heading, what the step is for, and the controls. Every flow's every step is
 * one of these, so the heading level and the spacing cannot drift between them.
 */
export function WizardPanel({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col min-w-0 gap-y-4">
      <div className="flex flex-col gap-y-1">
        <h3 className="text-heading-4 text-foreground">{title}</h3>
        <p className="text-paragraph-sm text-muted-foreground">{description}</p>
      </div>
      {children}
    </div>
  );
}

/*
 * One line of a confirmation: a label and its figure. A definition pair rather than a table row —
 * there is no second column of the same kind, and each line answers its own question.
 */
export function WizardConfirmRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
      <dt className="text-paragraph-sm text-muted-foreground">{label}</dt>
      <dd className="text-paragraph-sm-medium tabular-nums text-foreground">{value}</dd>
    </div>
  );
}

/*
 * Where you are in the flow. An ordered list because that is what it is, with `aria-current="step"`
 * so it reads as a position rather than as decoration.
 *
 * Every label is rendered at every step and only its colours change, so advancing never reflows the
 * row — the hard no-layout-shift rule. A completed step swaps its number for a tick in the same
 * fixed-size circle for the same reason.
 */
function StepIndicator({ steps, current }: { steps: string[]; current: number }) {
  return (
    <ol className="flex flex-wrap max-w-2xl items-center gap-x-2 gap-y-2">
      {steps.map((label, index) => {
        const done = index < current;
        const active = index === current;
        return (
          <li
            key={index}
            aria-current={active ? 'step' : undefined}
            className="flex items-center gap-x-2"
          >
            <span
              className={cn(
                'grid size-6 shrink-0 place-items-center rounded-full text-paragraph-xs-medium tabular-nums',
                done && 'bg-blue-800/10 text-blue-800',
                active && 'bg-blue-800 text-white',
                !done && !active && 'bg-muted text-muted-foreground',
              )}
            >
              {done ? <Check className="size-3.5" /> : index + 1}
            </span>
            <span
              className={cn(
                'text-paragraph-xs',
                active ? 'text-foreground' : 'text-muted-foreground',
              )}
            >
              {label}
            </span>
            {index < steps.length - 1 && (
              <span aria-hidden className="w-6 h-px shrink-0 bg-border" />
            )}
          </li>
        );
      })}
    </ol>
  );
}
