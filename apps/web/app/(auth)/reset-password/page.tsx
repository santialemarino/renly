import { redirect } from 'next/navigation';

import { ResetPasswordCard } from '@/app/(auth)/reset-password/_components/reset-password-card';
import { ROUTES } from '@/config/routes';
import { getSession } from '@/lib/auth';
import { generatePageMetadata } from '@/lib/utils/page-metadata';

export async function generateMetadata() {
  return await generatePageMetadata('resetPassword');
}

export default async function ResetPasswordPage({
  searchParams,
}: {
  searchParams: Promise<{ token?: string }>;
}) {
  const session = await getSession();
  if (session?.user && !session.user.error) {
    redirect(ROUTES.home);
  }

  const { token } = await searchParams;
  return <ResetPasswordCard token={token ?? null} />;
}
