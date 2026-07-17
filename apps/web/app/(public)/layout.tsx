import { PublicFooter } from '@/app/(public)/_components/public-footer';
import { PublicHeader } from '@/app/(public)/_components/public-header';

// Shell for the marketing, help, and legal pages (landing, help, privacy, terms, disclaimer).
// These routes are public — reachable logged in or out — so there is no session gate; the header
// adapts its CTAs to the session instead.
export default function PublicLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex flex-col min-h-screen bg-background">
      <PublicHeader />
      <main className="flex-1 flex flex-col w-full">{children}</main>
      <PublicFooter />
    </div>
  );
}
