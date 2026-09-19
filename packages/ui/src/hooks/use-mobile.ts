import * as React from 'react';

/*
 * The width below which the sidebar becomes a Sheet, expressed in the SAME unit and value as
 * Tailwind's `md` — which is what every `md:` utility in the app compiles to.
 *
 * That agreement is the whole point, and it did not hold: this hook used to decide with
 * `window.innerWidth < 768` (pixels) while Tailwind's `md` compiles to `@media (min-width: 48rem)`,
 * resolved against the browser's default font size. Those are the same number only at the default
 * 16px root. A reader who sets Chrome's font size to Large (20px) moves Tailwind's `md` to 960px
 * while the hook stayed at 768 — so between 768px and 960px the desktop sidebar was hidden by CSS,
 * the mobile bar was shown by CSS, and the hook still said "not mobile", which made `toggleSidebar()`
 * a no-op. The result was a visible navigation button that did nothing and no other way in.
 *
 * Reading the media query itself, in rem, removes the second declaration rather than restating it.
 */
const MOBILE_QUERY = 'not all and (min-width: 48rem)';

export function useIsMobile() {
  const [isMobile, setIsMobile] = React.useState<boolean | undefined>(undefined);

  React.useEffect(() => {
    const mql = window.matchMedia(MOBILE_QUERY);
    const onChange = () => {
      setIsMobile(mql.matches);
    };
    mql.addEventListener('change', onChange);
    setIsMobile(mql.matches);
    return () => mql.removeEventListener('change', onChange);
  }, []);

  return !!isMobile;
}
