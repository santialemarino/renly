'use client';

import { useEffect, useRef, useState, type FocusEvent } from 'react';

import { Tooltip, TooltipContent, TooltipTrigger } from '@repo/ui/components';
import { cn } from '@repo/ui/lib';
import { CONTROL_SELECTOR } from '@/lib/constants/controls';

// Whether the text is cut right now — read off the layout, never from state that may be stale.
function isCut(el: HTMLElement): boolean {
  return el.scrollWidth > el.clientWidth;
}

// The control the text sits inside (a nav link, a filter's trigger button), if any.
function controlAround(el: HTMLElement): HTMLElement | null {
  return el.parentElement?.closest<HTMLElement>(CONTROL_SELECTOR) ?? null;
}

interface TruncatingTooltipProps {
  text: string;
  className?: string;
  // Side relative to the trigger element. Defaults to `top` (Radix default);
  // sidebar usage overrides to `right` so the popup sits next to the item.
  side?: 'top' | 'right' | 'bottom' | 'left';
}

/*
 * Renders text with CSS truncation and a tooltip with the full value, only while the text is actually
 * cut (a ResizeObserver compares scrollWidth to clientWidth); text that fits gets no tooltip and no
 * tab stop.
 *
 * The tooltip is open only while the text is cut: an open is stored only if the text is cut at that
 * moment, and the text ceasing to be cut closes it. (Radix reports a change only when it differs from
 * the `open` it was given, so a gate applied when READING the state would let a hover over fitting
 * text store an open that no close ever clears, and the tooltip would pop up by itself once a resize
 * cut the text.)
 *
 * Keyboard users reach the tooltip too (WCAG 2.1.1). While cut, the text is focusable (`tabIndex=0`)
 * and Radix opens the tooltip on focus; Escape dismisses it and it stays open while hovered or focused
 * (1.4.13). Text that stops being cut while it holds focus stays a stop until focus leaves, so focus is
 * never dropped to the page. Inside a control (`CONTROL_SELECTOR`: a link, a button, a field) the text
 * stays out of the tab order and the tooltip opens when that control gets KEYBOARD focus instead, so a
 * nav link with a cut label is still one stop; a focusable scroll region around the text is not a
 * control. Which control, if any, is read when it matters — on each measure and each focus — not once.
 *
 * On a touch screen a tap opens nothing: Radix ignores touch hovers, and the focus a tap gives (which
 * arrives after Radix has forgotten the press) is kept from opening the tooltip. That is decided by the
 * focus itself — only a KEYBOARD focus (`:focus-visible`) may open it, the rule the nested path already
 * follows — rather than by remembering the last press: a touch press that never focuses the text (a pan,
 * a long press) would otherwise leave its type behind and block the next keyboard focus.
 *
 * The trigger carries no `aria-describedby`: CSS truncation leaves the whole text in the DOM, so
 * assistive tech already reads all of it, and a description repeating it would be announced twice.
 */
export function TruncatingTooltip({ text, className, side = 'top' }: TruncatingTooltipProps) {
  const ref = useRef<HTMLSpanElement>(null);
  const [truncated, setTruncated] = useState(false);
  const [nested, setNested] = useState(false);
  const [focused, setFocused] = useState(false);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const check = () => {
      const cut = isCut(el);
      setTruncated(cut);
      setNested(controlAround(el) !== null);
      if (!cut) setOpen(false);
    };
    check();
    const observer = new ResizeObserver(check);
    observer.observe(el);
    return () => observer.disconnect();
  }, [text]);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    // Whether an event's target is the control around the text, read at the time of the event.
    const isControl = (target: EventTarget | null) =>
      target instanceof HTMLElement && target.contains(el) && target === controlAround(el);
    // Only a keyboard focus: a click on a nav link should not pop a tooltip over it.
    const handleFocusIn = (event: globalThis.FocusEvent) => {
      if (isControl(event.target) && (event.target as HTMLElement).matches(':focus-visible'))
        setOpen(isCut(el));
    };
    const handleFocusOut = (event: globalThis.FocusEvent) => {
      if (isControl(event.target)) setOpen(false);
    };
    document.addEventListener('focusin', handleFocusIn);
    document.addEventListener('focusout', handleFocusOut);
    return () => {
      document.removeEventListener('focusin', handleFocusIn);
      document.removeEventListener('focusout', handleFocusOut);
    };
  }, []);

  const handleOpenChange = (next: boolean) => {
    setOpen(next && ref.current !== null && isCut(ref.current));
  };

  // Only a keyboard focus opens the tooltip; a default-prevented focus is one Radix does not open on.
  const handleFocus = (event: FocusEvent<HTMLSpanElement>) => {
    setFocused(true);
    if (!event.currentTarget.matches(':focus-visible')) event.preventDefault();
  };

  const handleBlur = () => {
    setFocused(false);
  };

  return (
    <Tooltip open={open} onOpenChange={handleOpenChange}>
      <TooltipTrigger asChild onFocus={handleFocus} onBlur={handleBlur}>
        <span
          ref={ref}
          tabIndex={focused || (truncated && !nested) ? 0 : undefined}
          aria-describedby={undefined}
          data-truncating-tooltip=""
          className={cn(
            'truncate rounded-xs outline-none focus-visible:ring-3 focus-visible:ring-ring',
            className,
          )}
        >
          {text}
        </span>
      </TooltipTrigger>
      <TooltipContent side={side} sideOffset={8}>
        {text}
      </TooltipContent>
    </Tooltip>
  );
}
