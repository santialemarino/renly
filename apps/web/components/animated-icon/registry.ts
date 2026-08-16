import {
  ArrowDown,
  ArrowDownUp,
  ArrowLeft,
  ArrowUp,
  BadgeDollarSign,
  Ban,
  Bell,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronsUpDown,
  CircleDollarSign,
  CircleDot,
  Compass,
  ExternalLink,
  Globe,
  HelpCircle,
  Info,
  KeyRound,
  Loader2,
  Lock,
  LogOut,
  Minus,
  Plus,
  RefreshCw,
  RotateCcw,
  Send,
  Settings,
  ShieldCheck,
  Sparkles,
  Tag,
  TrendingDown,
  TrendingUp,
  TriangleAlert,
  X,
  XCircle,
  Zap,
  type LucideIcon,
} from 'lucide-react';

import { AnimatedLogOut, AnimatedSettings, AnimatedShieldCheck } from './bespoke';

// A whole-glyph motion family — a class applied to the Lucide <svg> that animates the whole icon.
export type MotionFamily =
  | 'spin'
  | 'ring'
  | 'pulse'
  | 'pop'
  | 'bob'
  | 'nudge-up'
  | 'nudge-down'
  | 'nudge-right'
  | 'nudge-left';

// Family → the @repo/ui class that carries its keyframe / pose.
export const FAMILY_CLASS: Record<MotionFamily, string> = {
  spin: 'aicon-spin',
  ring: 'aicon-ring',
  pulse: 'aicon-pulse',
  pop: 'aicon-pop',
  bob: 'aicon-bob',
  'nudge-up': 'aicon-nudge-up',
  'nudge-down': 'aicon-nudge-down',
  'nudge-right': 'aicon-nudge-right',
  'nudge-left': 'aicon-nudge-left',
};

/*
 * Icons that get a specific whole-glyph motion, keyed by the component reference (not displayName,
 * which Lucide aliases via re-exports). Anything not listed here and not in BESPOKE_ICONS falls back
 * to the universal "draw itself in" — so every icon animates its own parts, none on a generic rotate.
 */
export const ICON_MOTION = new Map<LucideIcon, MotionFamily>([
  // Rotation — things that spin or refresh.
  [RefreshCw, 'spin'],
  [RotateCcw, 'spin'],
  [Loader2, 'spin'],
  [Compass, 'spin'],
  [Globe, 'spin'],
  // Notification — the bell swings from its crown.
  [Bell, 'ring'],
  // Attention — alerts and locks give a quick pulse.
  [TriangleAlert, 'pulse'],
  [Info, 'pulse'],
  [HelpCircle, 'pulse'],
  [CircleDot, 'pulse'],
  [Ban, 'pulse'],
  [Lock, 'pulse'],
  [KeyRound, 'pulse'],
  // Emphasis — small celebratory pop.
  [Plus, 'pop'],
  [Minus, 'pop'],
  [X, 'pop'],
  [XCircle, 'pop'],
  [Sparkles, 'pop'],
  [Zap, 'pop'],
  [Tag, 'pop'],
  [BadgeDollarSign, 'pop'],
  [CircleDollarSign, 'pop'],
  // Direction — nudge the way the icon points.
  [ArrowDownUp, 'bob'],
  [ChevronsUpDown, 'bob'],
  [ArrowUp, 'nudge-up'],
  [TrendingUp, 'nudge-up'],
  [ArrowDown, 'nudge-down'],
  [TrendingDown, 'nudge-down'],
  [ChevronDown, 'nudge-down'],
  [ChevronRight, 'nudge-right'],
  [ExternalLink, 'nudge-right'],
  [Send, 'nudge-right'],
  [ArrowLeft, 'nudge-left'],
  [ChevronLeft, 'nudge-left'],
]);

// Icons whose motion is part-level (a cog turns, an arrow slides, a check draws) — dedicated components.
export const BESPOKE_ICONS = new Map<
  LucideIcon,
  (props: { className?: string }) => React.ReactNode
>([
  [Settings, AnimatedSettings],
  [LogOut, AnimatedLogOut],
  [ShieldCheck, AnimatedShieldCheck],
]);
