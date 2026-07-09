'use client';

import { AlertTriangle, Info, X, XCircle } from 'lucide-react';
import { AnimatePresence, motion } from 'motion/react';

import { Hint, Separator } from '@repo/ui/components';
import { cn } from '@repo/ui/lib';
import { ANIMATION_DEFAULT } from '@/lib/constants/animations';

export type HintVariant = 'warning' | 'info' | 'error';

const VARIANT_CONFIG = {
  warning: {
    icon: AlertTriangle,
    iconColor: 'text-amber-500',
    textColor: 'text-amber-600',
    bg: 'bg-amber-50 border-amber-200',
  },
  info: {
    icon: Info,
    iconColor: 'text-blue-500',
    textColor: 'text-blue-600',
    bg: 'bg-blue-50 border-blue-200',
  },
  error: {
    icon: XCircle,
    iconColor: 'text-red-500',
    textColor: 'text-red-600',
    bg: 'bg-red-50 border-red-200',
  },
} as const;

interface StyledHintProps {
  variant?: HintVariant;
  show?: boolean;
  children: React.ReactNode;
  separator?: boolean;
  surface?: boolean;
  onDismiss?: () => void;
  parentGap?: number;
  className?: string;
}

// Animated hint with icon. Supports info (blue), warning (amber) and error (red) variants.
// When `show` is omitted or true, renders statically (no animation). Pass `show` to animate in/out.
export function StyledHint({
  variant = 'warning',
  show,
  children,
  separator = false,
  surface = false,
  onDismiss,
  parentGap = 4,
  className,
}: StyledHintProps) {
  const { icon: Icon, iconColor, textColor, bg } = VARIANT_CONFIG[variant];

  const content = (
    <div
      className="flex flex-col"
      style={{
        paddingTop: show !== undefined ? parentGap : 0,
        gap: show !== undefined ? parentGap : 0,
      }}
    >
      {separator && <Separator />}
      <div
        className={cn(
          'flex items-center gap-x-2',
          surface && `px-3 py-2 border ${bg} rounded-lg`,
          className,
        )}
      >
        <Icon className={cn('size-4 shrink-0', iconColor)} />
        <Hint className={cn(textColor, 'whitespace-pre-line')}>{children}</Hint>
        {onDismiss && (
          <button
            onClick={onDismiss}
            className={cn(
              'shrink-0 ml-auto p-0.5 rounded opacity-50 transition-[opacity,transform] duration-150 hover:opacity-100 hover:scale-110 focus-visible:outline-none focus-visible:opacity-100 focus-visible:scale-110',
              textColor,
            )}
            aria-label="Dismiss"
          >
            <X className="size-3.5" />
          </button>
        )}
      </div>
    </div>
  );

  // Static rendering (no animation) when `show` is not provided.
  if (show === undefined) return content;

  return (
    <AnimatePresence initial={false}>
      {show && (
        <motion.div
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: 'auto' }}
          exit={{ opacity: 0, height: 0 }}
          transition={{ duration: ANIMATION_DEFAULT }}
          style={{ overflow: 'hidden', marginTop: -parentGap }}
        >
          {content}
        </motion.div>
      )}
    </AnimatePresence>
  );
}

// Convenience wrappers.

type HintWrapperProps = Omit<StyledHintProps, 'variant'>;

export function InfoHint(props: HintWrapperProps) {
  return <StyledHint variant="info" {...props} />;
}

export function WarningHint(props: HintWrapperProps) {
  return <StyledHint variant="warning" {...props} />;
}

export function ErrorHint(props: HintWrapperProps) {
  return <StyledHint variant="error" {...props} />;
}
