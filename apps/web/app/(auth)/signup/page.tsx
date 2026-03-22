import { redirect } from 'next/navigation';

import { SignupCard } from '@/app/(auth)/signup/_components/signup-card';
import { ROUTES } from '@/config/routes';
import { getSession } from '@/lib/auth';
import { generatePageMetadata } from '@/lib/utils/page-metadata';

export async function generateMetadata() {
  return await generatePageMetadata('signup');
}

export default async function SignupPage() {
  const session = await getSession();
  if (session?.user && !session.user.error) {
    redirect(ROUTES.home);
  }

  return <SignupCard />;
}
