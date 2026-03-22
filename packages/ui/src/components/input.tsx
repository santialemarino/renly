import * as React from 'react';
import { Calendar, Eye, EyeOff } from 'lucide-react';

import { cn } from '@repo/ui/lib';

interface InputProps extends Omit<React.ComponentProps<'input'>, 'prefix'> {
  startIcon?: React.ReactNode;
  endIcon?: React.ReactNode;
  prefix?: React.ReactNode;
  suffix?: React.ReactNode;
  containerClassName?: string;
  blue?: boolean;
  blueEye?: boolean;
  surface?: boolean;
}

const Input = React.forwardRef<HTMLInputElement, InputProps>(
  (
    {
      className,
      containerClassName,
      startIcon,
      endIcon,
      prefix,
      suffix,
      type,
      blue = false,
      blueEye = false,
      surface = false,
      ...props
    },
    ref,
  ) => {
    const hasError = props['aria-invalid'];
    const [showPassword, setShowPassword] = React.useState(false);
    const internalRef = React.useRef<HTMLInputElement | null>(null);

    const isPassword = type === 'password';
    const isDate = type === 'date';
    const inputType = isPassword && showPassword ? 'text' : type;

    // Merge forwarded ref with internal ref for date picker access.
    const setRefs = React.useCallback(
      (node: HTMLInputElement | null) => {
        internalRef.current = node;
        if (typeof ref === 'function') ref(node);
        else if (ref) (ref as React.MutableRefObject<HTMLInputElement | null>).current = node;
      },
      [ref],
    );

    return (
      <div
        className={cn(
          'relative flex h-9 w-full items-center rounded-lg border shadow-xs',
          surface ? 'bg-background' : 'bg-input',
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
          ref={setRefs}
          type={inputType}
          data-slot="input"
          className={cn(
            'h-full w-full min-w-0 rounded-lg border-0 bg-transparent px-3 py-1 text-ellipsis',
            'text-paragraph-sm text-foreground placeholder:text-muted-foreground',
            'outline-none transition-[color,box-shadow]',
            'file:inline-flex file:h-7 file:border-0 file:bg-transparent file:text-sm file:font-medium file:text-foreground',
            'disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50',
            'focus-visible:outline-none focus-visible:ring-0',
            '[&:-webkit-autofill]:[-webkit-box-shadow:0_0_0_1000px_var(--color-input)_inset] [&:-webkit-autofill]:[transition:background-color_9999s_ease-in-out_0s]',
            'aria-invalid:ring-destructive/20',
            isDate && '[&::-webkit-calendar-picker-indicator]:hidden',
            startIcon && !prefix && 'pl-9',
            prefix && 'pl-0',
            (isPassword || isDate) && 'pr-9',
            endIcon && !isPassword && !isDate && 'pr-9',
            suffix && 'pr-0',
            className,
          )}
          {...props}
        />

        {endIcon && !isPassword && !isDate && (
          <div className="absolute right-2.5 top-1/2 -translate-y-1/2">{endIcon}</div>
        )}

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
                  'col-start-1 row-start-1 size-4 transition-all duration-200',
                  showPassword ? 'scale-0 opacity-0' : 'scale-100 opacity-100',
                )}
              />
              <EyeOff
                className={cn(
                  'col-start-1 row-start-1 size-4 transition-all duration-200',
                  showPassword ? 'scale-100 opacity-100' : 'scale-0 opacity-0',
                )}
              />
            </span>
          </button>
        )}

        {isDate && (
          <button
            type="button"
            tabIndex={-1}
            onClick={() => internalRef.current?.showPicker()}
            className={cn(
              'absolute right-2.5 top-1/2 -translate-y-1/2 cursor-pointer transition-all hover:scale-105',
              hasError ? 'text-destructive' : 'text-blue-800',
            )}
          >
            <Calendar className="size-4" />
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
