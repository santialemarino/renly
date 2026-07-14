'use client';

import { useEffect, useRef } from 'react';
import type { FieldValues, UseFormReturn } from 'react-hook-form';
import { toast } from 'sonner';

interface UseEntityFormDialogOptions<TValues extends FieldValues, TEntity> {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  form: UseFormReturn<TValues>;
  // Entity being edited (undefined in create mode). A change re-resets the form while open.
  entity: TEntity | undefined;
  // Maps the entity (or undefined) to the form's reset values. Read through a ref so the
  // inline closure doesn't retrigger the reset effect every render (which would wipe input).
  toValues: (entity: TEntity | undefined) => TValues;
  onSuccess: () => void;
}

/*
 * Shared create/edit form-dialog lifecycle: resets the form to the entity's values when
 * the dialog opens (or the entity changes while open), and wraps a save call with the
 * success-toast → onSuccess → close / error-toast sequence the aligned dialogs repeat.
 */
export function useEntityFormDialog<TValues extends FieldValues, TEntity>({
  open,
  onOpenChange,
  form,
  entity,
  toValues,
  onSuccess,
}: UseEntityFormDialogOptions<TValues, TEntity>) {
  const toValuesRef = useRef(toValues);
  toValuesRef.current = toValues;

  // Reset form when dialog opens or the edited entity changes.
  useEffect(() => {
    if (open) form.reset(toValuesRef.current(entity));
  }, [open, entity, form]);

  // Wraps the entity-specific save call with the shared toast/refresh/close sequence.
  async function submitWithLifecycle(
    save: () => Promise<unknown>,
    successMessage: string,
    errorMessage: string,
  ) {
    try {
      await save();
      toast.success(successMessage);
      onSuccess();
      onOpenChange(false);
    } catch {
      toast.error(errorMessage);
    }
  }

  return { submitWithLifecycle };
}
