import { redirect } from 'next/navigation';

import { LandingCta } from '@/app/(public)/_components/landing-cta';
import { LandingFeatures } from '@/app/(public)/_components/landing-features';
import { LandingHero } from '@/app/(public)/_components/landing-hero';
import { LandingHowItWorks } from '@/app/(public)/_components/landing-how-it-works';
import { ROUTES } from '@/config/routes';
import { getSession } from '@/lib/auth';
import { generatePageMetadata } from '@/lib/utils/page-metadata';

export async function generateMetadata() {
  return await generatePageMetadata('landing');
}

export default async function LandingPage() {
  // Logged-in users skip the marketing page and go straight to the app, mirroring the auth pages.
  const session = await getSession();
  if (session?.user && !session.user.error) {
    redirect(ROUTES.home);
  }

  return (
    <>
      <LandingHero />
      <LandingFeatures />
      <LandingHowItWorks />
      <LandingCta />
    </>
  );
}
