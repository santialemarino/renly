import { cn } from '@repo/ui/lib';

function Skeleton({ className, children, ...props }: React.ComponentProps<'div'>) {
  return (
    <div
      data-slot="skeleton"
      className={cn('relative bg-accent animate-pulse rounded-full', className)}
      {...props}
    >
      <span className="invisible whitespace-pre-wrap">{children}</span>
    </div>
  );
}

export { Skeleton };
