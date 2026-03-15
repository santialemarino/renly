export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <main className="flex w-full min-h-screen items-center justify-center px-4">{children}</main>
  );
}
