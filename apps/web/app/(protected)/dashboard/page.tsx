import { getSession } from '@/lib/auth';

export const metadata = {
  title: 'Dashboard — Renly',
};

export default async function DashboardPage() {
  const session = await getSession();

  return (
    <main className="flex flex-col min-h-full items-center justify-center p-8 gap-y-2">
      <h1 className="text-2xl font-semibold text-foreground">Dashboard</h1>
      <p className="text-muted-foreground">Welcome, {session?.user?.name}</p>
    </main>
  );
}
