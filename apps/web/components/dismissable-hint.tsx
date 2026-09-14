'use client';

import { useEffect, useState } from 'react';

import { StyledHint, type HintVariant } from '@/components/styled-hint';

interface DismissableHintProps {
  storageKey: string;
  children: React.ReactNode;
  variant?: HintVariant;
  show?: boolean;
  surface?: boolean;
  parentGap?: number;
  className?: string;
}

/*
 * A hint the user can dismiss permanently, keyed by `storageKey` in localStorage. Generalizes the
 * dismissible-currency-hint pattern so any contextual nudge reuses one dismissal mechanism. Defaults
 * (info + surface + parentGap=16) match the standard `gap-y-4` protected-page column, the only place
 * these nudges render today; override per call site if the surrounding layout differs.
 *
 * Its test id is DERIVED from the storage key rather than passed per call site, so every dismissable
 * hint in the app is reachable from one definition — the shared-primitive rule the e2e conventions
 * state, applied to the one prop that already distinguishes these hints from each other.
 */
export function DismissableHint({
  storageKey,
  children,
  variant = 'info',
  show = true,
  surface = true,
  parentGap = 16,
  className,
}: DismissableHintProps) {
  // Start dismissed so the hint never flashes before localStorage is read on mount.
  const [dismissed, setDismissed] = useState(true);

  useEffect(() => {
    setDismissed(localStorage.getItem(storageKey) === 'true');
  }, [storageKey]);

  const handleDismiss = () => {
    localStorage.setItem(storageKey, 'true');
    setDismissed(true);
  };

  return (
    <StyledHint
      variant={variant}
      show={show && !dismissed}
      surface={surface}
      parentGap={parentGap}
      onDismiss={handleDismiss}
      className={className}
      testId={`hint-${storageKey}`}
    >
      {children}
    </StyledHint>
  );
}
