'use client';

import { useEffect, useRef, useState } from 'react';

import { Tooltip, TooltipContent, TooltipTrigger } from '@repo/ui/components';
import { cn } from '@repo/ui/lib';

interface TruncatingTooltipProps {
  text: string;
  className?: string;
  // Side relative to the trigger element. Defaults to `top` (Radix default);
  // sidebar usage overrides to `right` so the popup sits next to the item.
  side?: 'top' | 'right' | 'bottom' | 'left';
}

// Renders text with CSS truncation and shows a hover tooltip with the full
// value only when the text is actually overflowing (detected via ResizeObserver
// comparing scrollWidth to clientWidth). Non-truncated text gets no tooltip,
// so we don't add redundant noise on items that already fit.
export function TruncatingTooltip({ text, className, side = 'top' }: TruncatingTooltipProps) {
  const ref = useRef<HTMLSpanElement>(null);
  const [truncated, setTruncated] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const check = () => setTruncated(el.scrollWidth > el.clientWidth);
    check();
    const observer = new ResizeObserver(check);
    observer.observe(el);
    return () => observer.disconnect();
  }, [text]);

  return (
    <Tooltip open={truncated ? undefined : false}>
      <TooltipTrigger asChild>
        <span ref={ref} className={cn('truncate', className)}>
          {text}
        </span>
      </TooltipTrigger>
      <TooltipContent side={side} sideOffset={8}>
        {text}
      </TooltipContent>
    </Tooltip>
  );
}
