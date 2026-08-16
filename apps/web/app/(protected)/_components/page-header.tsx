interface PageHeaderProps {
  title: string;
  subtitle: React.ReactNode;
  // Rendered beside the title — for a status the title alone can't carry (e.g. an archived badge).
  trailing?: React.ReactNode;
}

export function PageHeader({ title, subtitle, trailing }: PageHeaderProps) {
  return (
    <div className="flex flex-col gap-y-1">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <h1 className="text-heading-2 text-foreground">{title}</h1>
        {trailing}
      </div>
      <h2 className="text-paragraph text-muted-foreground">{subtitle}</h2>
    </div>
  );
}
