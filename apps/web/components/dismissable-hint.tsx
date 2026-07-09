'use client';

import { useEffect, useState } from 'react';

import { StyledHint } from '@/components/styled-hint';

interface DismissableHintProps {
  storageKey: string;
  children: React.ReactNode;
  variant?: 'warning' | 'info' | 'error';
  show?: boolean;
  surface?: boolean;
  parentGap?: number;
  className?: string;
}

// A hint the user can dismiss permanently, keyed by `storageKey` in localStorage. Generalizes the
// dismissible-currency-hint pattern so any contextual nudge reuses one dismissal mechanism.
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
    >
      {children}
    </StyledHint>
  );
}
