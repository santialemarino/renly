import { VerifyEmailCard } from '@/app/(auth)/verify-email/_components/verify-email-card';
import { generatePageMetadata } from '@/lib/utils/page-metadata';

export async function generateMetadata() {
  return await generatePageMetadata('verifyEmail');
}

// Landing page for the emailed verification / email-change link. Does not redirect logged-in users:
// confirming an email change happens while still authenticated. The card confirms the token client-side.
export default async function VerifyEmailPage({
  searchParams,
}: {
  searchParams: Promise<{ token?: string }>;
}) {
  const { token } = await searchParams;
  return <VerifyEmailCard token={token ?? null} />;
}
