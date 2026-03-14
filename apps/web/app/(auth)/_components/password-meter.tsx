'use client';

import { useCallback, useMemo } from 'react';
import { Check } from 'lucide-react';
import { useTranslations } from 'next-intl';

import { cn } from '@repo/ui/lib';

type PasswordCheck = 'characters' | 'uppercase' | 'lowercase' | 'number' | 'special';
type PasswordStrength = 'strong' | 'moderate' | 'weak' | 'empty';

const STRENGTH_COMPLETION_MAP: Record<PasswordStrength, number> = {
  empty: 1,
  weak: 25,
  moderate: 75,
  strong: 100,
};

const CheckItem = ({
  checked,
  label,
  isInvalid,
}: {
  checked: boolean;
  label: string;
  isInvalid: boolean;
}) => (
  <div className="flex items-center gap-x-1.5" aria-invalid={isInvalid}>
    <div className="w-3 h-3 flex items-center justify-center relative shrink-0">
      <Check
        className={cn(
          'size-3! shrink-0! text-green-600 transition-opacity duration-200',
          checked ? 'opacity-100' : 'opacity-0 absolute',
        )}
      />
      <div
        className={cn(
          'size-2 rounded-full shrink-0 transition-opacity duration-200',
          isInvalid ? 'bg-destructive' : 'bg-neutral-400',
          !checked ? 'opacity-100' : 'opacity-0 absolute',
        )}
      />
    </div>
    <span
      className={cn(
        'text-paragraph-mini text-neutral-600',
        isInvalid && !checked && 'text-destructive',
      )}
    >
      {label}
    </span>
  </div>
);

export function PasswordMeter({
  passingChecks,
  showErrors = false,
  className,
}: {
  passingChecks: Record<PasswordCheck, boolean>;
  showErrors?: boolean;
  className?: string;
}) {
  const t = useTranslations('signup.passwordMeter');

  const checkStrength = useCallback((checks: Record<PasswordCheck, boolean>): PasswordStrength => {
    const count = Object.values(checks).filter(Boolean).length;
    if (count === 5) return 'strong';
    if (count >= 3) return 'moderate';
    if (count >= 1) return 'weak';
    return 'empty';
  }, []);

  const strength = useMemo(() => checkStrength(passingChecks), [checkStrength, passingChecks]);
  const percentage = STRENGTH_COMPLETION_MAP[strength];

  const strengthColors: Record<PasswordStrength, string> = {
    empty: 'bg-neutral-300',
    weak: 'bg-orange-400',
    moderate: 'bg-blue-500',
    strong: 'bg-green-500',
  };

  const strengthTextColors: Record<PasswordStrength, string> = {
    empty: 'text-neutral-400',
    weak: 'text-orange-500',
    moderate: 'text-blue-600',
    strong: 'text-green-600',
  };

  return (
    <div className={cn('w-full flex flex-col gap-y-3', className)}>
      <div className="flex items-center gap-x-2 text-paragraph-sm">
        <span className="shrink-0 text-paragraph-mini-medium text-neutral-700">{t('title')}</span>
        <div className="flex-1 h-1.5 rounded-full bg-neutral-200 overflow-hidden">
          <div
            className={cn(
              'h-full rounded-full transition-all duration-300',
              strengthColors[strength],
            )}
            style={{ width: `${percentage}%` }}
          />
        </div>
        {strength !== 'empty' && (
          <span className={cn('shrink-0 text-paragraph-mini-medium', strengthTextColors[strength])}>
            {t(`strength.${strength}`)}
          </span>
        )}
      </div>

      <div className="flex flex-col gap-y-1.5">
        <span className="text-paragraph-mini-medium text-neutral-600">
          {t('requirements.title')}
        </span>
        <div className="flex flex-col gap-y-1">
          {(Object.keys(passingChecks) as PasswordCheck[]).map((check) => (
            <CheckItem
              key={check}
              checked={passingChecks[check]}
              label={t(`requirements.${check}`)}
              isInvalid={showErrors && !passingChecks[check]}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
