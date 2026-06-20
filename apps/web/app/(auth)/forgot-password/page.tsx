import { redirect } from 'next/navigation';

import { ForgotPasswordCard } from '@/app/(auth)/forgot-password/_components/forgot-password-card';
import { ROUTES } from '@/config/routes';
import { getSession } from '@/lib/auth';
import { generatePageMetadata } from '@/lib/utils/page-metadata';

export async function generateMetadata() {
  return await generatePageMetadata('forgotPassword');
}

export default async function ForgotPasswordPage() {
  const session = await getSession();
  if (session?.user && !session.user.error) {
    redirect(ROUTES.home);
  }

  return <ForgotPasswordCard />;
}
