import { getSession } from '@/lib/auth';

export const metadata = {
  title: 'Dashboard — Renly',
};

export default async function DashboardPage() {
  const session = await getSession();

  return (
    <main className="flex min-h-full flex-col items-center justify-center p-8 gap-2">
      <h1 className="text-2xl font-semibold text-foreground">Dashboard</h1>
      <p className="text-muted-foreground">Welcome, {session?.user?.name}</p>
    </main>
  );
}
