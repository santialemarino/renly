import { PublicFooter } from '@/app/(public)/_components/public-footer';
import { PublicHeader } from '@/app/(public)/_components/public-header';

// Shell for unauthenticated marketing and legal pages (landing, privacy, terms, disclaimer).
// No session check — these routes are public; the landing page redirects logged-in users itself.
export default function PublicLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex flex-col min-h-screen bg-background">
      <PublicHeader />
      <main className="flex-1 flex flex-col w-full">{children}</main>
      <PublicFooter />
    </div>
  );
}
