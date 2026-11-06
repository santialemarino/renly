interface SettingsFormFrameProps {
  children: React.ReactNode;
}

/*
 * The row a single-form settings page (preferences, localization, alerts) sets its form in: centred
 * until `lg`, then aligned to the header. The page and its loading state both render it, so the
 * placeholder form sits exactly where the real one will.
 */
export function SettingsFormFrame({ children }: SettingsFormFrameProps) {
  return <div className="flex w-full justify-center lg:justify-start">{children}</div>;
}
