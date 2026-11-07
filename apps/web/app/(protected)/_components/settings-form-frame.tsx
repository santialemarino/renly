interface SettingsFormFrameProps {
  children: React.ReactNode;
}

// The row a single-form settings page (preferences, localization, alerts) sets its form in: centred
// until `lg`, then aligned to the header.
export function SettingsFormFrame({ children }: SettingsFormFrameProps) {
  return <div className="flex w-full justify-center lg:justify-start">{children}</div>;
}
