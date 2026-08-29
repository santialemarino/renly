import { Check } from 'lucide-react';

interface WizardSummaryRow {
  /*
   * Stable identity, and NOT the label. `group_members.display_name` carries no uniqueness constraint
   * — only `(group_id, user_id)` is unique — so one group can legitimately hold two seats called the
   * same thing (two placeholders both named for a parent, say). Keying on the label would collide
   * them, which is the same defect two same-named investments once caused in a cmdk list.
   */
  id: string | number;
  label: string;
  // The headline figure for that row — a percentage, or an amount.
  value: string;
  // A second figure beneath it, when one row genuinely answers two questions.
  note?: string;
}

interface WizardSummaryProps {
  title: string;
  /*
   * What happened, in sentences. Each entry is one whole translated string rather than a template a
   * caller fills piecemeal: a Spanish sentence built by interpolating a label needs a determiner that
   * agrees with it, which is how "en esta grupo" got shipped once already.
   */
  lines: string[];
  // The resulting split, when the flow changed one. Read from the pot AFTER the write, so these are
  // what is now recorded rather than what was asked for.
  rows?: WizardSummaryRow[];
  actions: React.ReactNode;
}

/*
 * How a guided flow ends: what actually happened, in plain sentences, and where to go next.
 *
 * This is the point of the flows being flows (U6). A toast is a receipt — it says the write succeeded
 * and disappears — whereas the thing a person needs at the end of dividing money with someone else is
 * the resulting position and the consequences that are not visible in it. So the figures come from
 * the refreshed pot rather than from the form, and every honest caveat (the value has not moved yet;
 * the cash between two people is not recorded) is a line here rather than a hint on a field nobody is
 * looking at any more.
 */
export function WizardSummary({ title, lines, rows, actions }: WizardSummaryProps) {
  return (
    <div className="flex flex-col p-6 gap-y-5 bg-muted/30 border border-border rounded-1.5xl">
      <div className="flex items-center gap-x-3">
        <span className="grid size-9 shrink-0 place-items-center bg-blue-800/10 rounded-full text-blue-800">
          <Check className="size-5" />
        </span>
        <h3 className="text-heading-4 text-foreground">{title}</h3>
      </div>

      {rows && rows.length > 0 && (
        <dl className="flex flex-col gap-y-2">
          {rows.map((row) => (
            <div
              key={row.id}
              className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1"
            >
              <dt className="text-paragraph-sm text-foreground">{row.label}</dt>
              <dd className="flex items-baseline gap-x-2 text-paragraph-sm-medium tabular-nums text-foreground">
                {row.value}
                {row.note && (
                  <span className="text-paragraph-xs text-muted-foreground">{row.note}</span>
                )}
              </dd>
            </div>
          ))}
        </dl>
      )}

      <div className="flex flex-col gap-y-2">
        {/* Index keys: a fixed, ordered list that is rebuilt whole, never reordered or spliced. */}
        {lines.map((line, index) => (
          <p key={index} className="text-paragraph-sm text-muted-foreground">
            {line}
          </p>
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-x-2 gap-y-2">{actions}</div>
    </div>
  );
}
