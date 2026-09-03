// Chart configuration constants.
// All visual properties for Recharts-based charts live here so they can be
// tweaked in one place and verified instantly via hot-reload.

// --- Colors ---

// oklch values — Recharts needs resolved CSS colors, not Tailwind classes.
export const CHART_COLOR_PRIMARY = 'oklch(0.424 0.199 265.638)'; // blue-800
/*
 * The second series where two of them are the SAME measure at two scopes — a total and a part of it,
 * like a pot's value and one member's share. Deliberately the same hue several steps lighter rather
 * than a different one: a part-of-whole pair reads as related, and separating them by lightness is
 * also the most colour-vision-robust axis there is (measured: deuteranopia ΔE 25.9, normal 28.5,
 * against a target of 8). Two genuinely independent categories should not use this pair.
 */
export const CHART_COLOR_SECONDARY = 'oklch(0.707 0.165 254.624)'; // blue-400
export const CHART_COLOR_POSITIVE = 'oklch(0.596 0.145 163.225)'; // emerald-600
/*
 * A second asset segment that belongs WITH cash rather than beside it — money owed to you is money on
 * its way to your account, not a holding. Same hue two steps lighter, for the reason CHART_COLOR_SECONDARY
 * gives: relatedness reads, and lightness is the colour-vision-robust axis.
 *
 * It is deliberately NOT CHART_COLOR_SECONDARY, which is blue-400 and therefore identical to
 * DONUT_COLORS[3] — a donut with four investment categories would have drawn two different things in
 * exactly the same colour, and identity is never colour alone.
 */
export const CHART_COLOR_POSITIVE_SOFT = 'oklch(0.765 0.177 163.223)'; // emerald-400
export const CHART_COLOR_NEGATIVE = 'oklch(0.637 0.237 25.331)'; // red-500

// --- Layout ---

export const CHART_HEIGHT = 300;
export const CHART_MARGIN = { top: 4, right: 4, bottom: 0, left: 4 } as const;

// --- Axis ---

export const AXIS_TICK_MARGIN = 8;
export const AXIS_FONT_SIZE = 12;
export const AXIS_TICK_LINE = false;
export const AXIS_LINE = false;
export const Y_AXIS_WIDTH = 50;

// --- Grid ---

export const GRID_VERTICAL = false;
export const GRID_STROKE_DASHARRAY = '3 3';

// --- Area / Line ---

export const AREA_STROKE_WIDTH = 2;
export const AREA_CURVE_TYPE = 'monotone' as const;
export const AREA_FILL_GRADIENT_ID = 'fillValue';
export const AREA_GRADIENT_START_OPACITY = 0.3;
export const AREA_GRADIENT_END_OPACITY = 0.05;
export const AREA_GRADIENT_START_OFFSET = '5%';
export const AREA_GRADIENT_END_OFFSET = '95%';

// Point markers. Needed wherever a series may legitimately have GAPS: a lone valued point between two
// unknowns draws no line segment at all, so without a dot it is simply invisible.
export const POINT_DOT_RADIUS = 4;
export const POINT_DOT_RADIUS_ACTIVE = 6;

// --- Legend ---

export const LEGEND_FONT_SIZE = 12;
/*
 * Stated rather than measured. An unsized recharts <Legend> is laid out first and measured after, so
 * the plot area above it reflows once the legend's real height is known — a layout shift on every
 * chart that has one. Naming the height reserves the space up front instead.
 */
export const LEGEND_HEIGHT = 28;

// --- Tooltip ---

export const TOOLTIP_BG = 'var(--color-foreground)';
export const TOOLTIP_TEXT = 'var(--color-background)';
export const TOOLTIP_BORDER_RADIUS = '6px';
export const TOOLTIP_FONT_SIZE = '12px';
export const TOOLTIP_BORDER = 'none';
export const TOOLTIP_CURSOR_STROKE_WIDTH = 1;

// --- Donut / Pie ---

export const DONUT_HEIGHT = 280;
export const DONUT_INNER_RADIUS = 70;
export const DONUT_OUTER_RADIUS = 110;
export const DONUT_PADDING_ANGLE = 2;
export const DONUT_STROKE_WIDTH = 0;

// Palette for donut slices — ordered to give good contrast between adjacent slices.
export const DONUT_COLORS = [
  'oklch(0.424 0.199 265.638)', // blue-800
  'oklch(0.546 0.245 262.881)', // blue-600
  'oklch(0.623 0.214 259.815)', // blue-500
  'oklch(0.707 0.165 254.624)', // blue-400
  'oklch(0.809 0.105 251.813)', // blue-300
  'oklch(0.882 0.059 254.128)', // blue-200
  'oklch(0.488 0.243 264.376)', // blue-700
  'oklch(0.379 0.146 265.522)', // blue-900
  'oklch(0.932 0.032 255.585)', // blue-100
] as const;

export const DONUT_CENTER_FONT_SIZE = 14;
export const DONUT_CENTER_VALUE_FONT_SIZE = 20;

// --- Animation ---

export const CHART_ANIMATION_DURATION = 800;
export const CHART_ANIMATION_EASING = 'ease-in-out' as const;
export const TOOLTIP_ANIMATION_DURATION = 150;
