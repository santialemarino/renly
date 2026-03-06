import * as React from 'react';
import { Eye, EyeOff } from 'lucide-react';

import { cn } from '@repo/ui/lib';

interface InputProps extends Omit<React.ComponentProps<'input'>, 'prefix'> {
  startIcon?: React.ReactNode;
  prefix?: React.ReactNode;
  suffix?: React.ReactNode;
  containerClassName?: string;
  blue?: boolean;
  blueEye?: boolean;
}

const Input = React.forwardRef<HTMLInputElement, InputProps>(
  (
    {
      className,
      containerClassName,
      startIcon,
      prefix,
      suffix,
      type,
      blue = false,
      blueEye = false,
      ...props
    },
    ref,
  ) => {
    const hasError = props['aria-invalid'];
    const [showPassword, setShowPassword] = React.useState(false);

    const isPassword = type === 'password';
    const inputType = isPassword && showPassword ? 'text' : type;

    return (
      <div
        className={cn(
          'relative flex h-9 w-full items-center rounded-lg border bg-input',
          blue ? 'border-blue-700/50' : 'border-border',
          'transition-[border-color,box-shadow] duration-200 ease-in-out',
          blue
            ? 'focus-within:border-blue-700 focus-within:ring-[3px] focus-within:ring-blue-700/30'
            : 'focus-within:border-ring focus-within:ring-[3px] focus-within:ring-ring/50',
          hasError &&
            'border-destructive focus-within:border-destructive focus-within:ring-destructive/30',
          containerClassName,
        )}
      >
        {prefix && (
          <div className="pointer-events-none shrink-0 px-3 text-paragraph-sm uppercase text-muted-foreground">
            {prefix}
          </div>
        )}

        {startIcon && !prefix && (
          <div className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2">
            {startIcon}
          </div>
        )}

        <input
          ref={ref}
          type={inputType}
          data-slot="input"
          className={cn(
            'h-full w-full min-w-0 rounded-lg border-0 bg-transparent px-3 py-1',
            'text-paragraph-sm text-foreground placeholder:text-muted-foreground',
            'outline-none transition-[color,box-shadow]',
            'file:inline-flex file:h-7 file:border-0 file:bg-transparent file:text-sm file:font-medium file:text-foreground',
            'disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50',
            'focus-visible:outline-none focus-visible:ring-0',
            'aria-invalid:ring-destructive/20',
            startIcon && !prefix && 'pl-9',
            prefix && 'pl-0',
            isPassword && 'pr-9',
            suffix && 'pr-0',
            className,
          )}
          {...props}
        />

        {isPassword && (
          <button
            type="button"
            onClick={() => setShowPassword((prev) => !prev)}
            className={cn(
              'absolute right-2.5 top-1/2 -translate-y-1/2 cursor-pointer transition-all hover:scale-105',
              hasError
                ? 'text-destructive'
                : blue || blueEye
                  ? 'text-blue-800'
                  : 'text-muted-foreground hover:text-foreground',
            )}
          >
            <span className="grid">
              <Eye
                className={cn(
                  'col-start-1 row-start-1 h-4 w-4 transition-all duration-200',
                  showPassword ? 'scale-0 opacity-0' : 'scale-100 opacity-100',
                )}
              />
              <EyeOff
                className={cn(
                  'col-start-1 row-start-1 h-4 w-4 transition-all duration-200',
                  showPassword ? 'scale-100 opacity-100' : 'scale-0 opacity-0',
                )}
              />
            </span>
          </button>
        )}

        {suffix && (
          <div className="pointer-events-none shrink-0 px-3 text-paragraph-sm text-muted-foreground">
            {suffix}
          </div>
        )}
      </div>
    );
  },
);

Input.displayName = 'Input';

export { Input };
