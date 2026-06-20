'use client';

import * as React from 'react';
import { Slot } from '@radix-ui/react-slot';
import { AnimatePresence, motion } from 'motion/react';
import {
  Controller,
  FormProvider,
  useFormContext,
  useFormState,
  type ControllerProps,
  type FieldPath,
  type FieldValues,
} from 'react-hook-form';

import { Label } from '@repo/ui/components';
import { cn } from '@repo/ui/lib';
import { ANIMATION_DEFAULT } from '@/lib/constants/animations';

const Form = FormProvider;

type FormFieldContextValue<
  TFieldValues extends FieldValues = FieldValues,
  TName extends FieldPath<TFieldValues> = FieldPath<TFieldValues>,
> = {
  name: TName;
};

const FormFieldContext = React.createContext<FormFieldContextValue>({} as FormFieldContextValue);

function FormField<
  TFieldValues extends FieldValues = FieldValues,
  TName extends FieldPath<TFieldValues> = FieldPath<TFieldValues>,
>({ ...props }: ControllerProps<TFieldValues, TName>) {
  return (
    <FormFieldContext.Provider value={{ name: props.name }}>
      <Controller {...props} />
    </FormFieldContext.Provider>
  );
}

type FormItemContextValue = {
  id: string;
};

const FormItemContext = React.createContext<FormItemContextValue>({} as FormItemContextValue);

const useFormField = () => {
  const fieldContext = React.useContext(FormFieldContext);
  const itemContext = React.useContext(FormItemContext);
  const { getFieldState } = useFormContext();
  const formState = useFormState({ name: fieldContext.name });
  const fieldState = getFieldState(fieldContext.name, formState);

  if (!fieldContext) {
    throw new Error('useFormField should be used within <FormField>');
  }

  const { id } = itemContext;

  return {
    id,
    name: fieldContext.name,
    formItemId: `${id}-form-item`,
    formDescriptionId: `${id}-form-item-description`,
    formMessageId: `${id}-form-item-message`,
    ...fieldState,
  };
};

function FormItem({ className, ...props }: React.ComponentProps<'div'>) {
  const id = React.useId();
  return (
    <FormItemContext.Provider value={{ id }}>
      <div data-slot="form-item" className={cn('flex flex-col gap-y-2', className)} {...props} />
    </FormItemContext.Provider>
  );
}

function FormLabel({
  className,
  blue = false,
  required,
  children,
  ...props
}: React.ComponentProps<typeof Label> & { required?: boolean }) {
  const { error, formItemId } = useFormField();
  return (
    <Label
      blue={blue}
      data-slot="form-label"
      data-error={!!error}
      className={className}
      htmlFor={formItemId}
      {...props}
    >
      {children}
      {required && (
        <span aria-hidden="true" className="text-blue-800 -ml-1">
          *
        </span>
      )}
    </Label>
  );
}

function FormControl({ ...props }: React.ComponentProps<typeof Slot>) {
  const { error, formItemId, formDescriptionId, formMessageId } = useFormField();
  return (
    <Slot
      data-slot="form-control"
      id={formItemId}
      aria-describedby={!error ? formDescriptionId : `${formDescriptionId} ${formMessageId}`}
      aria-invalid={!!error}
      {...props}
    />
  );
}

function FormDescription({ className, ...props }: React.ComponentProps<'p'>) {
  const { formDescriptionId } = useFormField();
  return (
    <p
      data-slot="form-description"
      id={formDescriptionId}
      className={cn('text-muted-foreground text-paragraph-sm', className)}
      {...props}
    />
  );
}

function FormMessage({ className, children }: { className?: string; children?: React.ReactNode }) {
  const { error, formMessageId } = useFormField();
  const body = error ? String(error?.message ?? '') : children;
  // Key by content so a changed message animates as a separate element. `mode="wait"` keeps the
  // exiting message in normal flow while its height collapses to 0, so clearing an error smoothly
  // pushes the fields below up instead of snapping (which popLayout caused by popping it out of
  // flow); message-to-message swaps play sequentially (old collapses, then new expands).
  const key = typeof body === 'string' ? body : 'message';
  return (
    <AnimatePresence mode="wait" initial={false}>
      {body && (
        <motion.div
          key={key}
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: 'auto' }}
          exit={{ opacity: 0, height: 0 }}
          transition={{ duration: ANIMATION_DEFAULT }}
          // marginTop: -8 cancels the FormItem's flex gap-y-2 (8px); the inner pt-2 restores that gap
          // as padding *inside* the height-animated, overflow-hidden box — so clearing the error
          // collapses with no residual gap or first-frame snap (matches the snapshot/payment dialogs).
          style={{ overflow: 'hidden', marginTop: -8 }}
        >
          <p
            data-slot="form-message"
            id={formMessageId}
            className={cn('pt-2 text-destructive text-paragraph-xs', className)}
          >
            {body}
          </p>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

// Form-level (root) error, animated identically to FormMessage so submit/server errors enter and
// clear with the same smooth height collapse — no layout snap. For errors not tied to one field.
// Expects a `flex flex-col gap-y-5` (20px) parent — the marginTop/pt cancel that gap (see FormMessage).
function FormError({ message, className }: { message?: string; className?: string }) {
  return (
    <AnimatePresence mode="wait" initial={false}>
      {message && (
        <motion.div
          key={message}
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: 'auto' }}
          exit={{ opacity: 0, height: 0 }}
          transition={{ duration: ANIMATION_DEFAULT }}
          style={{ overflow: 'hidden', marginTop: -20 }}
        >
          <p
            data-slot="form-error"
            className={cn('pt-5 text-destructive text-paragraph-sm text-center', className)}
          >
            {message}
          </p>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

export {
  useFormField,
  Form,
  FormItem,
  FormLabel,
  FormControl,
  FormDescription,
  FormError,
  FormMessage,
  FormField,
};
