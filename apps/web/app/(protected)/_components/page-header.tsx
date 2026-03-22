interface PageHeaderProps {
  title: string;
  subtitle: React.ReactNode;
}

export function PageHeader({ title, subtitle }: PageHeaderProps) {
  return (
    <div className="flex flex-col gap-y-1">
      <h1 className="text-heading-2 text-foreground">{title}</h1>
      <h2 className="text-paragraph text-muted-foreground">{subtitle}</h2>
    </div>
  );
}
