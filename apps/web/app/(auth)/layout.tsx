interface AuthLayoutProps {
  children: React.ReactNode;
}

export default function AuthLayout({ children }: AuthLayoutProps) {
  return (
    <main className="flex w-full min-h-screen items-center justify-center px-4">{children}</main>
  );
}
