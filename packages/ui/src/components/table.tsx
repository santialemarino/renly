'use client';

import * as React from 'react';

import { cn } from '@repo/ui/lib';

/*
 * The table's name, required: it names the `<table>` and, while the table is wider than its column,
 * the scroll container around it.
 *
 * A container that scrolls sideways hides the columns past its edge, and a mouse or a trackpad
 * reaches them but a keyboard cannot unless the container itself takes focus (WCAG 2.1.1; axe's
 * `scrollable-region-focusable`). So while it overflows, and only then, it is a focusable, named
 * region: a stop in the Tab order that arrows scroll, announced by what it holds. A table that fits
 * adds no Tab stop — one that led nowhere would only lengthen the way through the page. The name is
 * the caller's, not a generic "table", because a page holding several (a group's hub has five) would
 * otherwise offer several regions of the same name, which is its own violation (`landmark-unique`).
 */
function Table({ className, label, ...props }: React.ComponentProps<'table'> & { label: string }) {
  const containerRef = React.useRef<HTMLDivElement>(null);
  const [overflowing, setOverflowing] = React.useState(false);

  React.useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const measure = () => setOverflowing(container.scrollWidth > container.clientWidth);
    measure();
    // The container resizes with the page; the table resizes with its rows (a page of data arriving,
    // a column appearing). Either can start or stop the overflow.
    const observer = new ResizeObserver(measure);
    observer.observe(container);
    if (container.firstElementChild) observer.observe(container.firstElementChild);
    return () => observer.disconnect();
  }, []);

  return (
    <div
      ref={containerRef}
      data-slot="table-container"
      data-overflowing={overflowing}
      role={overflowing ? 'region' : undefined}
      aria-label={overflowing ? label : undefined}
      tabIndex={overflowing ? 0 : undefined}
      className="relative w-full overflow-x-auto outline-none focus-visible:ring-3 focus-visible:ring-inset focus-visible:ring-ring"
    >
      <table
        data-slot="table"
        aria-label={label}
        className={cn('w-full caption-bottom text-paragraph-sm', className)}
        {...props}
      />
    </div>
  );
}

function TableHeader({ className, ...props }: React.ComponentProps<'thead'>) {
  return (
    <thead
      data-slot="table-header"
      className={cn('[&_tr]:border-b border-border-3', className)}
      {...props}
    />
  );
}

function TableBody({ className, ...props }: React.ComponentProps<'tbody'>) {
  return (
    <tbody
      data-slot="table-body"
      className={cn('[&_tr:last-child]:border-0 border-border-3', className)}
      {...props}
    />
  );
}

function TableFooter({ className, ...props }: React.ComponentProps<'tfoot'>) {
  return (
    <tfoot
      data-slot="table-footer"
      className={cn(
        'bg-muted/50 border-t border-border-3 font-medium [&>tr]:last:border-b-0',
        className,
      )}
      {...props}
    />
  );
}

function TableRow({ className, ...props }: React.ComponentProps<'tr'>) {
  return (
    <tr
      data-slot="table-row"
      className={cn(
        'hover:bg-muted/50 data-[state=selected]:bg-muted border-b border-border-3 transition-colors',
        className,
      )}
      {...props}
    />
  );
}

function TableHead({ className, ...props }: React.ComponentProps<'th'>) {
  return (
    <th
      data-slot="table-head"
      className={cn(
        'text-foreground h-10 px-2 text-left align-middle font-medium whitespace-nowrap [&:has([role=checkbox])]:pr-0 *:[[role=checkbox]]:translate-y-[2px]',
        className,
      )}
      {...props}
    />
  );
}

function TableCell({ className, ...props }: React.ComponentProps<'td'>) {
  return (
    <td
      data-slot="table-cell"
      className={cn(
        'p-2 align-middle whitespace-nowrap [&:has([role=checkbox])]:pr-0 *:[[role=checkbox]]:translate-y-[2px] border-border-3',
        className,
      )}
      {...props}
    />
  );
}

function TableCaption({ className, ...props }: React.ComponentProps<'caption'>) {
  return (
    <caption
      data-slot="table-caption"
      className={cn('text-muted-foreground mt-4 text-sm', className)}
      {...props}
    />
  );
}

export { Table, TableHeader, TableBody, TableFooter, TableHead, TableRow, TableCell, TableCaption };
