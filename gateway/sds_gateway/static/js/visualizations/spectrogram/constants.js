/**
 * Constants for Spectrogram Visualization
 */

export const DEFAULT_SPECTROGRAM_SETTINGS = {
	fftSize: 1024,
	stdDev: 100,
	hopSize: 500,
	colorMap: "magma",
};

// FFT size options (powers of 2 from 64 to 65536)
export const FFT_SIZE_OPTIONS = [
	64, 128, 256, 512, 1024, 2048, 4096, 8192, 16384, 32768, 65536,
];

export const COLOR_MAP_OPTIONS = [
	"magma",
	"viridis",
	"plasma",
	"inferno",
	"cividis",
	"turbo",
	"jet",
	"hot",
	"cool",
	"rainbow",
];

// Input validation ranges
export const INPUT_RANGES = {
	stdDev: { min: 10, max: 500 },
	hopSize: { min: 100, max: 1000 },
};

export const DEFAULT_IMAGE_DIMENSIONS = {
	width: 800,
	height: 400,
};

// API endpoints
export const get_create_spectrogram_endpoint = (capture_uuid) => {
	return `/api/v1/visualizations/${capture_uuid}/create_spectrogram/`;
};

export const get_spectrogram_status_endpoint = (capture_uuid, job_id) => {
	return `/api/v1/visualizations/${capture_uuid}/spectrogram_status/?job_id=${job_id}`;
};

export const get_spectrogram_result_endpoint = (capture_uuid, job_id) => {
	return `/api/v1/visualizations/${capture_uuid}/download_spectrogram/?job_id=${job_id}`;
};

export const STATUS_MESSAGES = {
	GENERATING: "Generating spectrogram...",
	SUCCESS: "",
	ERROR: "Failed to generate spectrogram",
	LOADING: "Loading...",
};

export const ERROR_MESSAGES = {
	NO_CAPTURE: "No capture data found",
	INVALID_SETTINGS: "Invalid spectrogram parameters",
	API_ERROR: "API request failed",
	RENDER_ERROR: "Failed to render spectrogram",
};
