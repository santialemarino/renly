'use client';

import * as React from 'react';
import * as PopoverPrimitive from '@radix-ui/react-popover';

import { cn } from '@repo/ui/lib';

/*
 * A Radix popover's content is a `role="dialog"`, and a dialog needs a name (axe's `aria-dialog-name`).
 * No call site should have to supply one, because every popover here already has it: the control that
 * opened it. So the content takes its trigger's name unless the caller names it itself.
 *
 * The name is read off the rendered trigger, as a string, rather than wired with `aria-labelledby`:
 * most triggers here are comboboxes, and a combobox referenced by `aria-labelledby` contributes its
 * VALUE (none, for these) rather than its text, so the dialog came out unnamed. What a reader hears
 * for the trigger is its `aria-label`, else its `<label>`s, else its text — so that is the order here.
 */
const PopoverTriggerNameContext = React.createContext<{
  triggerName: string | undefined;
  setTriggerName: (name: string | undefined) => void;
} | null>(null);

function Popover({ ...props }: React.ComponentProps<typeof PopoverPrimitive.Root>) {
  const [triggerName, setTriggerName] = React.useState<string | undefined>(undefined);
  const value = React.useMemo(() => ({ triggerName, setTriggerName }), [triggerName]);

  return (
    <PopoverTriggerNameContext.Provider value={value}>
      <PopoverPrimitive.Root data-slot="popover" {...props} />
    </PopoverTriggerNameContext.Provider>
  );
}

// The trigger's name as a reader hears it: its aria-label, else its labels' text, else its own text.
function nameOf(node: HTMLButtonElement): string | undefined {
  const label = node.getAttribute('aria-label')?.trim();
  if (label) return label;
  const labels = [...(node.labels ?? [])].map((element) => element.textContent?.trim() ?? '');
  const labelled = labels.filter(Boolean).join(' ');
  if (labelled) return labelled;
  return node.textContent?.trim() || undefined;
}

function PopoverTrigger({ ref, ...props }: React.ComponentProps<typeof PopoverPrimitive.Trigger>) {
  const setTriggerName = React.useContext(PopoverTriggerNameContext)?.setTriggerName;
  const nodeRef = React.useRef<HTMLButtonElement | null>(null);
  const composedRef = React.useCallback(
    (node: HTMLButtonElement | null) => {
      nodeRef.current = node;
      if (typeof ref === 'function') ref(node);
      else if (ref) ref.current = node;
    },
    [ref],
  );
  // Read after every render, not once: the trigger's text follows the selection and its label the
  // locale. React skips the update when the name is unchanged, so this costs a comparison.
  React.useLayoutEffect(() => {
    setTriggerName?.(nodeRef.current ? nameOf(nodeRef.current) : undefined);
  });

  return <PopoverPrimitive.Trigger data-slot="popover-trigger" {...props} ref={composedRef} />;
}
function PopoverContent({
  className,
  align = 'center',
  sideOffset = 4,
  ...props
}: React.ComponentProps<typeof PopoverPrimitive.Content>) {
  const triggerName = React.useContext(PopoverTriggerNameContext)?.triggerName;
  const named = props['aria-label'] !== undefined || props['aria-labelledby'] !== undefined;

  return (
    <PopoverPrimitive.Portal>
      <PopoverPrimitive.Content
        data-slot="popover-content"
        aria-label={named ? undefined : triggerName}
        align={align}
        sideOffset={sideOffset}
        className={cn(
          'bg-popover text-popover-foreground data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95 data-[side=bottom]:slide-in-from-top-2 data-[side=left]:slide-in-from-right-2 data-[side=right]:slide-in-from-left-2 data-[side=top]:slide-in-from-bottom-2 ring-foreground/10 flex flex-col gap-2.5 rounded-lg p-2.5 text-sm shadow-md ring-1 duration-200 z-200 w-72 origin-(--radix-popover-content-transform-origin) outline-hidden',
          className,
        )}
        {...props}
      />
    </PopoverPrimitive.Portal>
  );
}
function PopoverAnchor({ ...props }: React.ComponentProps<typeof PopoverPrimitive.Anchor>) {
  return <PopoverPrimitive.Anchor data-slot="popover-anchor" {...props} />;
}
function PopoverHeader({ className, ...props }: React.ComponentProps<'div'>) {
  return (
    <div
      data-slot="popover-header"
      className={cn('flex flex-col gap-0.5 text-sm', className)}
      {...props}
    />
  );
}
function PopoverTitle({ className, ...props }: React.ComponentProps<'h2'>) {
  return <div data-slot="popover-title" className={cn('font-medium', className)} {...props} />;
}
function PopoverDescription({ className, ...props }: React.ComponentProps<'p'>) {
  return (
    <p
      data-slot="popover-description"
      className={cn('text-muted-foreground', className)}
      {...props}
    />
  );
}
export {
  Popover,
  PopoverAnchor,
  PopoverContent,
  PopoverDescription,
  PopoverHeader,
  PopoverTitle,
  PopoverTrigger,
};
