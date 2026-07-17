import { HelpPage } from '@/app/(public)/_components/help-page';
import { generatePageMetadata } from '@/lib/utils/page-metadata';

export async function generateMetadata() {
  return await generatePageMetadata('help');
}

export default function Help() {
  return <HelpPage />;
}
