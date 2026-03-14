import { redirect } from 'next/navigation';

import { SidebarInset, SidebarProvider } from '@repo/ui/components';
import { AppSidebar } from '@/app/(protected)/_components/sidebar';
import { LOGIN_ROUTE } from '@/config/routes';
import { getSession } from '@/lib/auth';

export default async function ProtectedLayout({ children }: { children: React.ReactNode }) {
  const session = await getSession();

  if (!session?.user || (session.user as { error?: string }).error) {
    redirect(LOGIN_ROUTE);
  }

  return (
    <SidebarProvider>
      <AppSidebar />
      <SidebarInset>{children}</SidebarInset>
    </SidebarProvider>
  );
}
