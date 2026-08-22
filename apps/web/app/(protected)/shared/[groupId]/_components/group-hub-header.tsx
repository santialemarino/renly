import { getTranslations } from 'next-intl/server';

import { Badge } from '@repo/ui/components';
import { PageHeader } from '@/app/(protected)/_components/page-header';
import type { Group } from '@/lib/api/groups';
import { getFormatters } from '@/lib/i18n/formatters-server';

interface GroupHubHeaderProps {
  group: Group;
}

/*
 * The group's identity and standing: what it is, how many people are in it, and what the viewer's own
 * standing is. The role badge is deliberately in the header rather than only in the roster, because it
 * is what decides which controls below are even rendered — the user should be able to see why.
 *
 * There are no figures here yet. Value, ownership percentages and per-currency balances arrive with the
 * pots and the flow half; the stats grid is the shape they will land in.
 */
export async function GroupHubHeader({ group }: GroupHubHeaderProps) {
  const fmt = await getFormatters();
  const t = await getTranslations('shared');
  const tCommon = await getTranslations('common');

  const placeholderCount = group.members.filter((m) => m.isActive && !m.isLinked).length;
  const stats = [
    { label: t('hub.stats.members'), value: String(group.activeMemberCount) },
    {
      label: t('hub.stats.placeholders'),
      value: placeholderCount > 0 ? String(placeholderCount) : t('hub.stats.none'),
    },
    { label: t('hub.stats.created'), value: fmt.timestampDate(group.createdAt) },
  ];

  return (
    <div className="flex flex-col gap-y-4">
      <PageHeader
        title={group.name}
        subtitle={tCommon(`groupKinds.${group.kind}`)}
        trailing={
          <Badge variant={group.myRole === 'admin' ? 'default' : 'secondary'}>
            {t(`roles.${group.myRole}`)}
          </Badge>
        }
      />

      <dl className="grid grid-cols-1 sm:grid-cols-3 p-4 gap-x-6 gap-y-4 bg-muted/30 border border-border rounded-1.5xl">
        {stats.map((stat) => (
          <div key={stat.label} className="flex flex-col gap-y-1">
            <dt className="text-paragraph-xs text-muted-foreground">{stat.label}</dt>
            <dd className="text-paragraph-medium tabular-nums text-foreground">{stat.value}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
