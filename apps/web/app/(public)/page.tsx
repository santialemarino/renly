import { LandingCta } from '@/app/(public)/_components/landing-cta';
import { LandingFeatures } from '@/app/(public)/_components/landing-features';
import { LandingHero } from '@/app/(public)/_components/landing-hero';
import { LandingHowItWorks } from '@/app/(public)/_components/landing-how-it-works';
import { getSignupContext } from '@/lib/api/signup-context';
import { getSession, isAuthenticatedSession } from '@/lib/auth';
import { generatePageMetadata } from '@/lib/utils/page-metadata';

export async function generateMetadata() {
  return await generatePageMetadata('landing');
}

export default async function LandingPage() {
  // The marketing page is public — viewable whether logged in or out (unlike the auth forms, which
  // redirect logged-in users to the app). When authenticated, the hero CTA points to the app and
  // the closing signup-conversion block is hidden; the public header swaps its CTAs the same way.
  // The signup mode keeps the signup CTAs honest: in invite-only mode they read "Request access".
  const [session, { mode }] = await Promise.all([getSession(), getSignupContext()]);
  const isAuthenticated = isAuthenticatedSession(session);

  return (
    <>
      <LandingHero isAuthenticated={isAuthenticated} signupMode={mode} />
      <LandingFeatures />
      <LandingHowItWorks />
      {!isAuthenticated && <LandingCta signupMode={mode} />}
    </>
  );
}
