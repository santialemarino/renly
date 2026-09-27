'use client';

import { createContext, useContext } from 'react';

/*
 * The one thing the quick-add's trigger needs from the component that owns its forms: a way to ask
 * for them, and whether that request is still loading.
 *
 * The two ends live in different trees on purpose. The owner (`QuickAddProvider`) is rendered by the
 * protected layout and holds the dialogs; the trigger sits in the sidebar, which below `md` is a Sheet
 * that UNMOUNTS when it closes — and opening a form closes it, so a dialog owned in there went with
 * it about 300ms after appearing.
 *
 * Its own module rather than an export of either end, so the sidebar's import graph stops at this
 * file: were the trigger to import the context from the owner's module, the sidebar would reach the
 * five form chunks the owner loads, which is the structure `tests/unit/quick-add-ownership.test.ts`
 * refuses.
 */
export interface QuickAddControls {
  // Reads the pickers, closes the mobile sheet, then opens the expense form.
  open: () => void;
  // True while `open` is still awaiting its reads, so the trigger can show it and refuse a second tap.
  loading: boolean;
}

export const QuickAddControlsContext = createContext<QuickAddControls | null>(null);

// The controls, or a loud failure: a trigger rendered with no owner above it would otherwise be a
// button that silently does nothing.
export function useQuickAddControls(): QuickAddControls {
  const controls = useContext(QuickAddControlsContext);
  if (!controls) throw new Error('useQuickAddControls must be used inside a QuickAddProvider');
  return controls;
}
