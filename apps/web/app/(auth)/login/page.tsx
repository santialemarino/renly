import { redirect } from 'next/navigation';
import { getTranslations } from 'next-intl/server';

import { Card, CardContent, CardHeader, CardTitle } from '@repo/ui/components';
import { LoginForm } from '@/app/(auth)/login/_components/login-form';
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

  const t = await getTranslations('login');

  return (
    <Card className="w-full max-w-auth-form">
      <CardHeader>
        <CardTitle className="text-heading-4 text-center text-blue-800">{t('title')}</CardTitle>
      </CardHeader>
      <CardContent>
        <LoginForm />
      </CardContent>
    </Card>
  );
}
