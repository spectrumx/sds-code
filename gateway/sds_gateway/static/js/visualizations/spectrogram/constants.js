/**
 * Constants for Spectrogram Visualization
 */

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
