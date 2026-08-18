'use client';

import { useState } from 'react';
import Link from 'next/link';
import {
  Check,
  CheckCircle2,
  CircleDollarSign,
  Compass,
  Landmark,
  Sparkles,
  TrendingUp,
  Wallet,
  X,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { AnimatePresence, motion } from 'motion/react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';

import { Button, Card } from '@repo/ui/components';
import { cn } from '@repo/ui/lib';
import {
  completeOnboarding,
  completeTour,
} from '@/app/(protected)/dashboard/_components/onboarding-welcome-actions';
import { useWelcomeTour } from '@/app/(protected)/dashboard/_components/use-welcome-tour';
import { InlineLink } from '@/components/inline-link';
import { ROUTES } from '@/config/routes';
import type { OnboardingStatus } from '@/lib/api/onboarding';
import { ANIMATION_DEFAULT } from '@/lib/constants/animations';
import { hasCompletedCoreSteps } from '@/lib/onboarding';

interface OnboardingStepProps {
  icon: LucideIcon;
  label: string;
  hint: string;
  done: boolean;
  actionLabel: string;
  href: string;
  optional?: boolean;
  altLabel?: string;
  altHref?: string;
}

// A single checklist row: the step's own icon becomes a check once done (the row derives its
// done-state from real data upstream, so it stays truthful and self-heals). Done rows drop their
// action and dim; open rows surface the primary action, plus an optional secondary link (import a
// portfolio, add income) where the step has a natural second entry point.
function OnboardingStep({
  icon: Icon,
  label,
  hint,
  done,
  actionLabel,
  href,
  optional,
  altLabel,
  altHref,
}: OnboardingStepProps) {
  const t = useTranslations('dashboard.onboarding');
  return (
    <li className="flex items-center gap-x-3">
      <span
        className={cn(
          'grid size-9 shrink-0 place-items-center rounded-full transition-colors duration-200',
          done ? 'bg-blue-800/10 text-blue-800' : 'bg-muted text-muted-foreground',
        )}
      >
        {done ? <Check className="size-5" /> : <Icon className="size-5" />}
      </span>

      <div className="flex flex-col flex-1 min-w-0 gap-y-0.5">
        <span
          className={cn(
            'flex items-center gap-x-2 text-paragraph-sm-medium',
            done && 'text-muted-foreground',
          )}
        >
          {label}
          {done && <span className="sr-only">{t('stepDone')}</span>}
          {optional && (
            <span className="text-paragraph-xs text-muted-foreground">{t('optional')}</span>
          )}
        </span>
        <span className="text-paragraph-xs text-muted-foreground">{hint}</span>
      </div>

      {!done && (
        <div className="flex flex-col shrink-0 items-end gap-y-1">
          <Button asChild size="sm" variant="outline">
            <Link href={href}>{actionLabel}</Link>
          </Button>
          {altLabel && altHref && (
            <InlineLink href={altHref} color="muted" className="text-paragraph-xs">
              {altLabel}
            </InlineLink>
          )}
        </div>
      )}
    </li>
  );
}

interface OnboardingWelcomeProps {
  // Checklist step completion derived from real data (null when the status read failed — the
  // checklist then degrades to plain shortcuts with nothing pre-checked).
  status: OnboardingStatus | null;
  // Auto-launch the guided welcome tour once (a first-run newcomer who hasn't seen it). The replay
  // link is always available regardless.
  autoStartTour: boolean;
}

// First-run welcome shown on the dashboard until onboarding is completed. It's a reactive
// checklist: each step reflects the account's real data, so acting on a step (adding an
// investment, an expense, an account, choosing currencies) checks it off on the next dashboard load
// with no per-card flag. Dismissing — via the ✕ or the "all set" confirmation once both gating steps
// are done — persists the completion flag server-side so the welcome never returns.
export function OnboardingWelcome({ status, autoStartTour }: OnboardingWelcomeProps) {
  const t = useTranslations('dashboard.onboarding');
  const tTour = useTranslations('dashboard.tour');
  const [dismissed, setDismissed] = useState(false);
  const { start: startTour } = useWelcomeTour({ autoStart: autoStartTour, onEnd: completeTour });

  const hasInvestments = status?.hasInvestments ?? false;
  const hasFinances = status?.hasFinances ?? false;
  const hasAccounts = status?.hasAccounts ?? false;
  const primaryCurrencySet = status?.primaryCurrencySet ?? false;

  // Which steps gate the positive finish lives in one place next to the sidebar/tour's newcomer
  // signal, so the two cannot drift on what counts as core data. Pinned by a vitest.
  const gatingDone = hasCompletedCoreSteps(status);

  const steps: Array<OnboardingStepProps & { key: string }> = [
    {
      key: 'finances',
      icon: Wallet,
      done: hasFinances,
      label: t('steps.finances.label'),
      hint: t('steps.finances.hint'),
      actionLabel: t('steps.finances.action'),
      href: ROUTES.expenses,
      altLabel: t('steps.finances.income'),
      altHref: ROUTES.income,
    },
    {
      key: 'investment',
      icon: TrendingUp,
      done: hasInvestments,
      label: t('steps.investment.label'),
      hint: t('steps.investment.hint'),
      actionLabel: t('steps.investment.action'),
      href: ROUTES.investments,
      altLabel: t('steps.investment.import'),
      altHref: `${ROUTES.data}?type=investments`,
    },
    {
      key: 'accounts',
      icon: Landmark,
      done: hasAccounts,
      label: t('steps.accounts.label'),
      hint: t('steps.accounts.hint'),
      actionLabel: t('steps.accounts.action'),
      href: ROUTES.accounts,
      optional: true,
    },
    {
      key: 'currencies',
      icon: CircleDollarSign,
      done: primaryCurrencySet,
      label: t('steps.currencies.label'),
      hint: t('steps.currencies.hint'),
      actionLabel: t('steps.currencies.action'),
      href: ROUTES.preferences,
      optional: true,
    },
  ];

  async function handleDismiss() {
    if (dismissed) return; // guard against a double-click during the exit animation
    setDismissed(true); // optimistic — hide immediately; the server flag keeps it hidden on reload
    try {
      await completeOnboarding();
    } catch {
      setDismissed(false); // restore on failure so the user can retry
      toast.error(t('dismissError'));
    }
  }

  return (
    <AnimatePresence initial={false}>
      {!dismissed && (
        <motion.section
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: ANIMATION_DEFAULT }}
        >
          <Card compact className="p-6 gap-y-5 relative" data-testid="onboarding-welcome">
            <button
              type="button"
              onClick={handleDismiss}
              disabled={dismissed}
              aria-label={t('dismiss')}
              className="group/dismiss flex p-1 rounded-md outline-none hover:text-foreground focus-visible:text-foreground absolute top-3 right-3 text-muted-foreground transition-colors duration-200 cursor-pointer"
            >
              <X className="size-4 group-focus-visible/dismiss:animate-focus-bump" />
            </button>

            <div className="flex flex-col pr-8 gap-y-1">
              <span className="flex items-center gap-x-2 text-heading-5">
                <Sparkles className="size-5 text-blue-800" />
                {t('title')}
              </span>
              <span className="text-paragraph-sm text-muted-foreground">{t('subtitle')}</span>
              <InlineLink onClick={startTour} icon={Compass} className="self-start">
                {tTour('replay')}
              </InlineLink>
            </div>

            <ul className="flex flex-col gap-y-4">
              {steps.map((step) => (
                <OnboardingStep
                  key={step.key}
                  icon={step.icon}
                  label={step.label}
                  hint={step.hint}
                  done={step.done}
                  actionLabel={step.actionLabel}
                  href={step.href}
                  optional={step.optional}
                  altLabel={step.altLabel}
                  altHref={step.altHref}
                />
              ))}
            </ul>

            {gatingDone && (
              <div className="flex flex-col pt-1 gap-y-3 sm:flex-row sm:items-center sm:justify-between">
                <div className="flex flex-col gap-y-0.5">
                  <span className="flex items-center gap-x-2 text-paragraph-sm-medium text-blue-800">
                    <CheckCircle2 className="size-5" />
                    {t('allSet.title')}
                  </span>
                  <span className="text-paragraph-xs text-muted-foreground">
                    {t('allSet.subtitle')}
                  </span>
                </div>
                <Button
                  blue
                  size="sm"
                  onClick={handleDismiss}
                  disabled={dismissed}
                  className="shrink-0"
                >
                  {t('allSet.action')}
                </Button>
              </div>
            )}
          </Card>
        </motion.section>
      )}
    </AnimatePresence>
  );
}
