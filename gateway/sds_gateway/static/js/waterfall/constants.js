/**
 * Waterfall Visualization Constants
 * Centralized constants used across all waterfall components
 */

// Margin constants for alignment between periodogram and waterfall plots
export const PLOTS_LEFT_MARGIN = 85;
export const PLOTS_RIGHT_MARGIN = 80;

// CanvasJS specific margin adjustments
export const CANVASJS_LEFT_MARGIN = 10;
export const CANVASJS_RIGHT_MARGIN = 10;

// Waterfall rendering constants
export const WATERFALL_WINDOW_SIZE = 100;
export const WATERFALL_TOP_MARGIN = 5;
export const WATERFALL_BOTTOM_MARGIN = 5;

// Default scale bounds
export const DEFAULT_SCALE_MIN = -130;
export const DEFAULT_SCALE_MAX = 0;

// Color map options
export const COLOR_MAPS = {
	VIRIDIS: "viridis",
	PLASMA: "plasma",
	INFERNO: "inferno",
	MAGMA: "magma",
	HOT: "hot",
	GRAY: "gray",
};

// Default color map
export const DEFAULT_COLOR_MAP = COLOR_MAPS.VIRIDIS;
