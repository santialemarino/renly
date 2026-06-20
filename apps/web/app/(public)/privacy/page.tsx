import { LegalPage } from '@/app/(public)/_components/legal-page';
import { generatePageMetadata } from '@/lib/utils/page-metadata';

export async function generateMetadata() {
  return await generatePageMetadata('privacy');
}

export default function PrivacyPage() {
  return <LegalPage namespace="privacy" />;
}
