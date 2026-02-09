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

// Above this many slices we prefer streaming (on-demand) over preprocessed
export const LARGE_CAPTURE_THRESHOLD = 50_000;

// Cache and loading constants
export const CACHE_SIZE = 800; // Maximum cached slices for seamless navigation
// Default slices to request per API call.
// The backend may override this value by defining `window.MAX_SLICE_BATCH_SIZE`
// to keep it in sync with the backend MAX_SLICE_BATCH_SIZE setting.
const DEFAULT_BATCH_SIZE = 100;
export const BATCH_SIZE =
	typeof window !== "undefined" &&
	typeof window.MAX_SLICE_BATCH_SIZE === "number"
		? window.MAX_SLICE_BATCH_SIZE
		: DEFAULT_BATCH_SIZE;

// Prefetch strategy constants
// PREFETCH_TRIGGER: Only start prefetching when within this distance of unfetched data
// PREFETCH_DISTANCE: Once triggered, load this many slices ahead/behind
export const PREFETCH_TRIGGER = 2 * WATERFALL_WINDOW_SIZE; // 200 slices
export const PREFETCH_DISTANCE = 6 * WATERFALL_WINDOW_SIZE; // 600 slices - loads 700 total on init

// API endpoints
export const get_create_waterfall_endpoint = (capture_uuid) => {
	return `/api/v1/visualizations/${capture_uuid}/create_waterfall/`;
};

export const get_waterfall_status_endpoint = (capture_uuid, job_id) => {
	return `/api/v1/visualizations/${capture_uuid}/waterfall_status/?job_id=${job_id}`;
};

export const get_waterfall_result_endpoint = (capture_uuid, job_id) => {
	return `/api/v1/visualizations/${capture_uuid}/download_waterfall/?job_id=${job_id}`;
};

export const get_waterfall_slices_endpoint = (
	capture_uuid,
	start_index,
	end_index,
	processing_type = "waterfall",
) => {
	return `/api/latest/assets/captures/${capture_uuid}/waterfall_slices/?start_index=${start_index}&end_index=${end_index}&processing_type=${processing_type}`;
};

// Streaming endpoints - compute FFT on-demand without preprocessing
// include_power_bounds: when true, backend may do expensive DRF sample for scale (slower).
export const get_waterfall_metadata_stream_endpoint = (
	capture_uuid,
	include_power_bounds = false,
) => {
	const base = `/api/latest/assets/captures/${capture_uuid}/waterfall_metadata_stream/`;
	if (include_power_bounds) {
		return `${base}?include_power_bounds=true`;
	}
	return base;
};

export const get_waterfall_slices_stream_endpoint = (
	capture_uuid,
	start_index,
	end_index,
) => {
	return `/api/latest/assets/captures/${capture_uuid}/waterfall_slices_stream/?start_index=${start_index}&end_index=${end_index}`;
};

export const ERROR_MESSAGES = {
	NO_CAPTURE: "No capture data found",
	API_ERROR: "API request failed",
	RENDER_ERROR: "Failed to render waterfall",
	NO_DATA:
		"Waterfall data not available. Please ensure post-processing is complete.",
};
