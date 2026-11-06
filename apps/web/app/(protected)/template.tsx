import { PageEntrance } from '@/app/(protected)/_components/page-entrance';

interface ProtectedTemplateProps {
  children: React.ReactNode;
}

/*
 * Every protected page's entrance (see `PageEntrance`). A template rather than the layout because
 * Next mounts a template afresh on each navigation between sections and renders the route's loading
 * state inside it, so the one box sees both the loading state and the page that replaces it.
 */
export default function ProtectedTemplate({ children }: ProtectedTemplateProps) {
  return <PageEntrance>{children}</PageEntrance>;
}
