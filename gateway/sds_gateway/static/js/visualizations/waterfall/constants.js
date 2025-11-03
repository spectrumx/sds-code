/**
 * Constants for Waterfall Visualization
 */

// Color map constants
export const DEFAULT_COLOR_MAP = "viridis";

// Scale constants
export const DEFAULT_SCALE_MIN = -130;
export const DEFAULT_SCALE_MAX = 0;

// Desired margins for both periodogram and waterfall plots
export const PLOTS_LEFT_MARGIN = 85;
export const PLOTS_RIGHT_MARGIN = 80;

// Approximate CanvasJS built-in margins we need to adjust for
// in the periodogram
export const CANVASJS_LEFT_MARGIN = 10;
export const CANVASJS_RIGHT_MARGIN = 10;

// Waterfall-specific margins
export const WATERFALL_TOP_MARGIN = 5;
export const WATERFALL_BOTTOM_MARGIN = 5;

// Window size constants
export const WATERFALL_WINDOW_SIZE = 100;

export const ERROR_MESSAGES = {
	NO_CAPTURE: "No capture data found",
	API_ERROR: "API request failed",
	RENDER_ERROR: "Failed to render waterfall",
	NO_DATA:
		"Waterfall data not available. Please ensure post-processing is complete.",
};
