import { getTranslations } from 'next-intl/server';

import { Skeleton } from '@repo/ui/components';
import { cn } from '@repo/ui/lib';
import { PageHeader } from '@/app/(protected)/_components/page-header';

// How many placeholder rows a table body shows — enough to fill a laptop viewport, no more.
const TABLE_ROWS = 8;
// Stat tiles across the top of a dashboard, and field rows in a settings panel.
const DASHBOARD_TILES = 4;
const FORM_FIELDS = 4;

export type PageSkeletonBody = 'table' | 'dashboard' | 'form' | 'sections';

interface PageSkeletonLayoutProps {
  // The muted "back to …" link a detail page opens with.
  backLink?: boolean;
  // The search + filters + add-button row a list page carries under its header.
  toolbar?: boolean;
  // The detail and wizard pages space their blocks `gap-y-6` rather than the list pages' `gap-y-4`.
  loose?: boolean;
  body: PageSkeletonBody;
}

interface PageSkeletonProps extends PageSkeletonLayoutProps {
  // The page's translation namespace, whose `title` and `subtitle` ARE its header. Omit it when the
  // page's title is DATA (an account's or a group's name), which a loading state cannot know.
  namespace?: string;
  // The page's title is static but its subtitle depends on data (a filter's name): paint the title
  // and a placeholder where the subtitle goes, rather than a default subtitle the page contradicts.
  subtitleIsData?: boolean;
}

// What each route's `loading.tsx` renders: resolves the copy, then draws the view below.
export async function PageSkeleton({
  namespace,
  subtitleIsData = false,
  ...layout
}: PageSkeletonProps) {
  const tCommon = await getTranslations('common.loading');
  const t = namespace ? await getTranslations(namespace) : null;

  return (
    <PageSkeletonView
      status={tCommon('status')}
      title={t?.('title')}
      subtitle={subtitleIsData ? undefined : t?.('subtitle')}
      {...layout}
    />
  );
}

interface PageSkeletonViewProps extends PageSkeletonLayoutProps {
  // The loading page's screen-reader status.
  status: string;
  // The page's real header. Omitted when the page's title is DATA (an account's or a group's name),
  // which a loading state cannot know — the header is then a placeholder of the same size.
  title?: string;
  subtitle?: string;
}

/*
 * The one loading state every protected route renders, through `PageSkeleton` in its `loading.tsx`.
 *
 * It paints the page's frame at the page's own sizes — the same `p-8` column, the real `PageHeader`
 * when the title is known, and placeholders the height of the toolbar and rows that replace them — so
 * the swap to the loaded page moves nothing. The header is the one part rendered for real: it is the
 * part a user reads to know the navigation worked.
 *
 * The placeholder block fades in after a short delay rather than appearing at once, so a page that
 * loads quickly swaps straight from its header to its content instead of flashing grey bars. The fade
 * is opacity only, which the reduced-motion rule allows; the Skeleton's own pulse is gated in the base.
 *
 * `aria-busy` marks the region that is still coming; the status line is what a screen reader
 * announces, since the placeholders themselves say nothing.
 */
export function PageSkeletonView({
  status,
  title,
  subtitle,
  backLink = false,
  toolbar = false,
  loose = false,
  body,
}: PageSkeletonViewProps) {
  return (
    <div
      className={cn('flex flex-col flex-1 p-8', loose ? 'gap-y-6' : 'gap-y-4')}
      data-testid="page-skeleton"
    >
      <p role="status" className="sr-only">
        {status}
      </p>
      {backLink && <Skeleton className="w-40 h-5 rounded-md" />}
      {title !== undefined && subtitle !== undefined ? (
        <PageHeader title={title} subtitle={subtitle} />
      ) : title !== undefined ? (
        <div className="flex flex-col gap-y-1">
          <h1 className="text-heading-2 text-foreground">{title}</h1>
          <Skeleton className="w-80 max-w-full h-6 rounded-md" />
        </div>
      ) : (
        <div className="flex flex-col gap-y-1">
          <Skeleton className="w-64 max-w-full h-10 rounded-lg" />
          <Skeleton className="w-80 max-w-full h-6 rounded-md" />
        </div>
      )}
      <div
        aria-busy="true"
        className="flex flex-col gap-y-4 animate-in fade-in fill-mode-backwards delay-150 duration-300"
      >
        {toolbar && <ToolbarSkeleton />}
        {body === 'table' && <TableSkeleton />}
        {body === 'dashboard' && <DashboardSkeleton />}
        {body === 'form' && <FormSkeleton />}
        {body === 'sections' && <SectionsSkeleton />}
      </div>
    </div>
  );
}

// Search field (grows), then the pills and the add button — wrapping below `md` like the real row.
function ToolbarSkeleton() {
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
      <Skeleton className="flex-1 min-w-48 h-9 rounded-lg" />
      <div className="flex basis-full md:basis-auto items-center gap-x-3">
        <Skeleton className="flex-1 md:w-28 h-8 rounded-lg" />
        <Skeleton className="flex-1 md:w-32 h-8 rounded-lg" />
      </div>
    </div>
  );
}

// A header row and body rows at the table primitive's heights (`h-10` head, 49px rows).
function TableSkeleton() {
  return (
    <div className="flex flex-col w-full">
      <div className="flex h-10 items-center px-2 gap-x-6 border-b border-border-3">
        <Skeleton className="w-24 h-4 rounded-md" />
        <Skeleton className="w-32 h-4 rounded-md" />
        <Skeleton className="hidden sm:block w-28 h-4 rounded-md" />
        <Skeleton className="hidden md:block w-24 h-4 rounded-md" />
      </div>
      {Array.from({ length: TABLE_ROWS }, (_, i) => (
        <div key={i} className="flex h-[49px] items-center px-2 gap-x-6 border-b border-border-3">
          <Skeleton className="w-24 h-4 rounded-md" />
          <Skeleton className="w-32 h-4 rounded-md" />
          <Skeleton className="hidden sm:block w-28 h-4 rounded-md" />
          <Skeleton className="hidden md:block w-24 h-4 rounded-md" />
        </div>
      ))}
    </div>
  );
}

// Stat tiles, then the wide chart and the two panels under it.
function DashboardSkeleton() {
  return (
    <div className="flex flex-col gap-y-4">
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
        {Array.from({ length: DASHBOARD_TILES }, (_, i) => (
          <Skeleton key={i} className="h-28 rounded-1.5xl" />
        ))}
      </div>
      <Skeleton className="h-80 rounded-1.5xl" />
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Skeleton className="h-72 rounded-1.5xl" />
        <Skeleton className="h-72 rounded-1.5xl" />
      </div>
    </div>
  );
}

// A settings panel: label + field pairs in a bounded column.
function FormSkeleton() {
  return (
    <div className="flex flex-col w-full max-w-2xl gap-y-6">
      {Array.from({ length: FORM_FIELDS }, (_, i) => (
        <div key={i} className="flex flex-col gap-y-2">
          <Skeleton className="w-32 h-4 rounded-md" />
          <Skeleton className="h-9 rounded-lg" />
        </div>
      ))}
    </div>
  );
}

// A detail page's stacked sections: a summary panel, then section blocks.
function SectionsSkeleton() {
  return (
    <div className="flex flex-col gap-y-6">
      <Skeleton className="h-32 rounded-1.5xl" />
      <Skeleton className="h-64 rounded-1.5xl" />
      <Skeleton className="h-64 rounded-1.5xl" />
    </div>
  );
}
