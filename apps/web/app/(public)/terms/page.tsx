import { LegalPage } from '@/app/(public)/_components/legal-page';
import { generatePageMetadata } from '@/lib/utils/page-metadata';

export async function generateMetadata() {
  return await generatePageMetadata('terms');
}

export default function TermsPage() {
  return <LegalPage namespace="terms" />;
}
