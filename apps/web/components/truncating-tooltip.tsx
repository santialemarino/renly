'use client';

import { useEffect, useRef, useState } from 'react';

import { Tooltip, TooltipContent, TooltipTrigger } from '@repo/ui/components';
import { cn } from '@repo/ui/lib';

/*
 * What a keyboard already stops on. Text inside one of these (a nav link, a filter's trigger button)
 * must not become a second tab stop: a focusable element nested in an interactive one is announced
 * badly and leaves an empty extra stop (axe's `nested-interactive`).
 */
const INTERACTIVE_ANCESTOR = [
  'a[href]',
  'button',
  'input',
  'select',
  'textarea',
  'summary',
  '[tabindex]:not([tabindex="-1"])',
  '[contenteditable]:not([contenteditable="false"])',
  '[role="button"]',
  '[role="link"]',
  '[role="menuitem"]',
  '[role="option"]',
  '[role="tab"]',
  '[role="combobox"]',
].join(', ');

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
 * Keyboard users reach the tooltip too (WCAG 2.1.1). While cut, the text is focusable (`tabIndex=0`)
 * and Radix opens the tooltip on focus; Escape dismisses it and it stays open while hovered or focused
 * (1.4.13). Inside an interactive element the text stays out of the tab order and the tooltip opens
 * when that element gets KEYBOARD focus instead, so a nav link with a cut label is still one stop. Touch
 * is unchanged: Radix ignores touch hovers and a focus that follows a press.
 *
 * The trigger carries no `aria-describedby`: CSS truncation leaves the whole text in the DOM, so
 * assistive tech already reads all of it, and a description repeating it would be announced twice.
 */
export function TruncatingTooltip({ text, className, side = 'top' }: TruncatingTooltipProps) {
  const ref = useRef<HTMLSpanElement>(null);
  const [truncated, setTruncated] = useState(false);
  const [nested, setNested] = useState(false);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const check = () => setTruncated(el.scrollWidth > el.clientWidth);
    check();
    const observer = new ResizeObserver(check);
    observer.observe(el);
    return () => observer.disconnect();
  }, [text]);

  useEffect(() => {
    const el = ref.current;
    const host = el?.parentElement?.closest<HTMLElement>(INTERACTIVE_ANCESTOR);
    setNested(Boolean(host));
    if (!el || !host) return;
    // Only a keyboard focus: a click on a nav link should not pop a tooltip over it.
    const handleFocusIn = () => {
      if (host.matches(':focus-visible') && el.scrollWidth > el.clientWidth) setOpen(true);
    };
    const handleFocusOut = () => setOpen(false);
    host.addEventListener('focusin', handleFocusIn);
    host.addEventListener('focusout', handleFocusOut);
    return () => {
      host.removeEventListener('focusin', handleFocusIn);
      host.removeEventListener('focusout', handleFocusOut);
    };
  }, []);

  return (
    <Tooltip open={truncated && open} onOpenChange={setOpen}>
      <TooltipTrigger asChild>
        <span
          ref={ref}
          tabIndex={truncated && !nested ? 0 : undefined}
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
