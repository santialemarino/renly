import { redirect } from 'next/navigation';

import { LoginCard } from '@/app/(auth)/login/_components/login-card';
import { ROUTES } from '@/config/routes';
import { getSession } from '@/lib/auth';
import { generatePageMetadata } from '@/lib/utils/page';

export async function generateMetadata() {
  return await generatePageMetadata('login');
}

export default async function LoginPage() {
  const session = await getSession();
  if (session?.user && !session.user.error) {
    redirect(ROUTES.home);
  }

  return <LoginCard />;
}
