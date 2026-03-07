import { redirect } from 'next/navigation';

import { LOGIN_ROUTE } from '@/config/routes';
import { getSession } from '@/lib/auth';

export default async function ProtectedLayout({ children }: { children: React.ReactNode }) {
  const session = await getSession();

  if (!session?.user || (session.user as { error?: string }).error) {
    redirect(LOGIN_ROUTE);
  }

  return (
    <div className="min-h-screen flex flex-col">
      <main className="flex-1">{children}</main>
    </div>
  );
}
