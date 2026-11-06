import { getTranslations } from 'next-intl/server';

import { PageHeader } from '@/app/(protected)/_components/page-header';
import { AccountSections } from '@/app/(protected)/account/_components/account-sections';
import { getSession } from '@/lib/auth';
import { generatePageMetadata } from '@/lib/utils/page-metadata';

export async function generateMetadata() {
  return await generatePageMetadata('account');
}

export default async function AccountPage() {
  const t = await getTranslations('account');
  const session = await getSession();
  const email = session?.user?.email ?? '';

  return (
    <div className="flex flex-col flex-1 items-start p-8 gap-y-4">
      <PageHeader title={t('title')} subtitle={t('subtitle')} />
      <AccountSections email={email} />
    </div>
  );
}
