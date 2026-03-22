// Chart configuration constants.
// All visual properties for Recharts-based charts live here so they can be
// tweaked in one place and verified instantly via hot-reload.

// --- Colors ---

// oklch value for blue-800. Recharts needs a resolved CSS color, not a Tailwind class.
export const CHART_COLOR_PRIMARY = 'oklch(0.424 0.199 265.638)';

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

// --- Tooltip ---

export const TOOLTIP_BG = 'var(--color-foreground)';
export const TOOLTIP_TEXT = 'var(--color-background)';
export const TOOLTIP_BORDER_RADIUS = '6px';
export const TOOLTIP_FONT_SIZE = '12px';
export const TOOLTIP_BORDER = 'none';
export const TOOLTIP_CURSOR_STROKE_WIDTH = 1;

// --- Value formatting thresholds ---

export const FORMAT_THRESHOLD_MILLION = 1_000_000;
export const FORMAT_THRESHOLD_THOUSAND = 1_000;
