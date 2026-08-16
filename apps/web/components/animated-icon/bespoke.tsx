import { cn } from '@repo/ui/lib';

/*
 * Bespoke part-level icons — the few where a specific part should move while the rest stays put, which
 * a whole-glyph family can't express. Each inlines the exact lucide-react geometry (pixel-identical at
 * rest) and tags the moving part with an `aipart-*` / `aicon-draw` class; the motion itself lives in
 * @repo/ui and fires from the nearest `data-animate-icon` ancestor's hover / focus. Everything else
 * routes through a whole-glyph family or the universal draw (see registry.ts).
 */

// Shared <svg> shell matching lucide-react's output so a bespoke icon drops in wherever a Lucide one sits.
function BespokeSvg({ className, children }: { className?: string; children: React.ReactNode }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="24"
      height="24"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={cn('size-6 shrink-0', className)}
    >
      {children}
    </svg>
  );
}

// Settings — the cog turns in place while the centre pivot stays fixed.
export function AnimatedSettings({ className }: { className?: string }) {
  return (
    <BespokeSvg className={className}>
      <path
        className="aipart-turn"
        d="M9.671 4.136a2.34 2.34 0 0 1 4.659 0 2.34 2.34 0 0 0 3.319 1.915 2.34 2.34 0 0 1 2.33 4.033 2.34 2.34 0 0 0 0 3.831 2.34 2.34 0 0 1-2.33 4.033 2.34 2.34 0 0 0-3.319 1.915 2.34 2.34 0 0 1-4.659 0 2.34 2.34 0 0 0-3.32-1.915 2.34 2.34 0 0 1-2.33-4.033 2.34 2.34 0 0 0 0-3.831A2.34 2.34 0 0 1 6.35 6.051a2.34 2.34 0 0 0 3.319-1.915"
      />
      <circle cx="12" cy="12" r="3" />
    </BespokeSvg>
  );
}

// LogOut — the door frame holds; the arrow slides out through it.
export function AnimatedLogOut({ className }: { className?: string }) {
  return (
    <BespokeSvg className={className}>
      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
      <g className="aipart-slide-x">
        <path d="m16 17 5-5-5-5" />
        <path d="M21 12H9" />
      </g>
    </BespokeSvg>
  );
}

// ShieldCheck — the shield stays; the check draws itself in.
export function AnimatedShieldCheck({ className }: { className?: string }) {
  return (
    <BespokeSvg className={className}>
      <path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z" />
      <path className="aicon-draw" pathLength={1} d="m9 12 2 2 4-4" />
    </BespokeSvg>
  );
}
