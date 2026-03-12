/**
 * Main Spectrogram Visualization Class
 * Orchestrates all spectrogram components and handles the main functionality
 */

import { generateErrorMessage, setupErrorDisplay } from "../errorHandler.js";
import { SpectrogramControls } from "./SpectrogramControls.js";
import { SpectrogramRenderer } from "./SpectrogramRenderer.js";
import {
	DEFAULT_IMAGE_DIMENSIONS,
	ERROR_MESSAGES,
	STATUS_MESSAGES,
	get_create_spectrogram_endpoint,
	get_spectrogram_result_endpoint,
	get_spectrogram_status_endpoint,
} from "./constants.js";

export class SpectrogramVisualization {
	constructor(captureUuid) {
		this.captureUuid = captureUuid;
		this.controls = null;
		this.renderer = null;
		this.currentSpectrogramUrl = null;
		this.isGenerating = false;
		this.currentJobId = null;
		this.pollingInterval = null;

		// DOM elements
		this.errorDisplay = null;
		this.loadingOverlay = null;
		this.saveButton = null;

		this.initialize();
	}

	/**
	 * Initialize the spectrogram visualization
	 */
	async initialize() {
		try {
			await this.initializeComponents();
			this.setupEventHandlers();
			// Generate spectrogram with default parameters
			await this.generateSpectrogram();
		} catch (error) {
			console.error("Failed to initialize spectrogram visualization:", error);
			this.showError(ERROR_MESSAGES.RENDER_ERROR);
		}
	}

	/**
	 * Initialize all component classes
	 */
	async initializeComponents() {
		// Initialize controls
		this.controls = new SpectrogramControls();

		// Initialize renderer
		this.renderer = new SpectrogramRenderer();

		// Get DOM elements
		this.errorDisplay = document.getElementById("visualizationErrorDisplay");
		this.loadingOverlay = document.getElementById("loadingOverlay");
		this.saveButton = document.getElementById("saveSpectrogramBtn");

		// Initialize the renderer
		if (!this.renderer.initializeImage()) {
			console.error("Failed to initialize spectrogram renderer image");
		}

		// Set up control callbacks
		this.controls.setGenerateCallback(() => {
			this.generateSpectrogram();
		});
	}

	/**
	 * Set up event handlers
	 */
	setupEventHandlers() {
		// Save button click handler
		if (this.saveButton) {
			this.saveButton.addEventListener("click", () => this.saveSpectrogram());
		}
	}

	/**
	 * Generate spectrogram with current settings
	 */
	async generateSpectrogram() {
		if (this.isGenerating) {
			return;
		}

		try {
			this.clearStatusDisplay();
			this.setGeneratingState(true);
			this.showSaveButton(false);
			this.showStatus(STATUS_MESSAGES.GENERATING);

			const settings = this.controls.getSettings();

			// Call the actual API
			await this.createSpectrogramJob(settings);
		} catch (error) {
			console.error("Error generating spectrogram:", error);
			this.displayRequestError(error, ERROR_MESSAGES.API_ERROR);
			this.setGeneratingState(false);
		}
	}

	/**
	 * Create a spectrogram generation job via API
	 */
	async createSpectrogramJob(settings) {
		try {
			const rendererDimensions = this.renderer?.getDisplayDimensions();
			const dimensions = rendererDimensions || DEFAULT_IMAGE_DIMENSIONS;

			const response = await fetch(
				get_create_spectrogram_endpoint(this.captureUuid),
				{
					method: "POST",
					headers: {
						"Content-Type": "application/json",
						"X-CSRFToken": this.getCSRFToken(),
					},
					body: JSON.stringify({
						fft_size: settings.fftSize,
						std_dev: settings.stdDev,
						hop_size: settings.hopSize,
						colormap: settings.colorMap,
						timestamp: new Date().toISOString(),
						dimensions: dimensions,
					}),
				},
			);

			await this.throwOnFailedResponse(
				response,
				"Unable to create spectrogram job",
			);

			const data = await response.json();

			if (!data.uuid) {
				const missingUuidError = new Error("Spectrogram job ID not found");
				missingUuidError.userMessage = "Unable to create spectrogram job.";
				missingUuidError.errorDetail = "Response did not include a job id.";
				throw missingUuidError;
			}
			this.currentJobId = data.uuid;

			// Start polling for status
			this.startStatusPolling();
		} catch (error) {
			console.error("Error creating spectrogram job:", error);
			throw error;
		}
	}

	/**
	 * Start polling for job status
	 */
	startStatusPolling() {
		if (this.pollingInterval) {
			clearInterval(this.pollingInterval);
		}

		this.pollingInterval = setInterval(async () => {
			await this.checkJobStatus();
		}, 3000); // Poll every 3 seconds
	}

	/**
	 * Check the status of the current job
	 */
	async checkJobStatus() {
		if (!this.currentJobId) return;

		try {
			const response = await fetch(
				get_spectrogram_status_endpoint(this.captureUuid, this.currentJobId),
				{
					headers: {
						"X-CSRFToken": this.getCSRFToken(),
					},
				},
			);

			await this.throwOnFailedResponse(
				response,
				"Unable to check spectrogram status",
			);

			const data = await response.json();
			const processingStatus = data.processing_status;

			if (processingStatus === "completed") {
				// Job completed, stop polling and fetch result
				this.stopStatusPolling();
				await this.fetchSpectrogramResult();
			} else if (processingStatus === "failed") {
				// Job failed
				this.stopStatusPolling();
				this.handleProcessingError(data);
				this.setGeneratingState(false);
			} else if (processingStatus) {
				this.showStatus(
					`${STATUS_MESSAGES.GENERATING} (${this.formatProcessingStatus(processingStatus)})`,
				);
			}
			// If still processing, continue polling
		} catch (error) {
			console.error("Error checking job status:", error);
			this.stopStatusPolling();
			this.displayRequestError(error, "Failed to check spectrogram status");
			this.setGeneratingState(false);
		}
	}

	/**
	 * Stop status polling
	 */
	stopStatusPolling() {
		if (this.pollingInterval) {
			clearInterval(this.pollingInterval);
			this.pollingInterval = null;
		}
	}

	/**
	 * Fetch the completed spectrogram result
	 */
	async fetchSpectrogramResult() {
		try {
			const response = await fetch(
				get_spectrogram_result_endpoint(this.captureUuid, this.currentJobId),
				{
					headers: {
						"X-CSRFToken": this.getCSRFToken(),
					},
				},
			);

			await this.throwOnFailedResponse(
				response,
				"Unable to fetch spectrogram result",
			);

			const blob = await response.blob();

			// Revoke the old URL before creating a new one
			if (this.currentSpectrogramUrl) {
				URL.revokeObjectURL(this.currentSpectrogramUrl);
				this.currentSpectrogramUrl = null;
			}

			const renderResult = await this.renderer.renderFromImageBlob(blob);

			this.setGeneratingState(false);

			if (renderResult) {
				this.clearStatusDisplay();
				this.showSaveButton(true);
			} else {
				this.showErrorWithDetails("Failed to render spectrogram");
			}

			// Store the result for saving
			this.currentSpectrogramUrl = URL.createObjectURL(blob);
		} catch (error) {
			console.error("Error fetching spectrogram result:", error);
			this.displayRequestError(error, "Failed to fetch spectrogram result");
			this.setGeneratingState(false);
		}
	}

	/**
	 * Throw enriched error for failed HTTP responses
	 */
	async throwOnFailedResponse(response, userMessage) {
		if (response.ok) {
			return;
		}

		const responseData = await this.safeParseJson(response);
		const processingStatus = responseData?.processing_status;
		const responseDetail = this.extractResponseDetail(responseData);

		const details = [];
		if (processingStatus) {
			details.push(
				`Processing status: ${this.formatProcessingStatus(processingStatus)}`,
			);
		}
		if (responseDetail) {
			details.push(responseDetail);
		} else {
			details.push(`HTTP ${response.status}: ${response.statusText}`);
		}

		const requestError = new Error(
			`HTTP ${response.status}: ${response.statusText}`,
		);
		requestError.userMessage = `${userMessage}.`;
		requestError.errorDetail = details.join(" • ");
		throw requestError;
	}

	/**
	 * Parse JSON payload safely from response
	 */
	async safeParseJson(response) {
		try {
			return await response.json();
		} catch {
			return null;
		}
	}

	/**
	 * Extract a readable error detail from API response payload
	 */
	extractResponseDetail(responseData) {
		if (!responseData) {
			return null;
		}

		if (typeof responseData === "string") {
			return responseData;
		}

		const detailFields = ["detail", "error", "message"];
		for (const fieldName of detailFields) {
			if (typeof responseData[fieldName] === "string") {
				return responseData[fieldName];
			}
		}

		if (Array.isArray(responseData.errors)) {
			return responseData.errors.join(", ");
		}

		if (
			responseData.errors &&
			typeof responseData.errors === "object" &&
			!Array.isArray(responseData.errors)
		) {
			const firstFieldErrors = Object.entries(responseData.errors)[0];
			if (!firstFieldErrors) {
				return null;
			}

			const [fieldName, fieldValue] = firstFieldErrors;
			if (Array.isArray(fieldValue)) {
				return `${fieldName}: ${fieldValue.join(", ")}`;
			}

			if (typeof fieldValue === "string") {
				return `${fieldName}: ${fieldValue}`;
			}
		}

		return null;
	}

	/**
	 * Format backend processing status for user display
	 */
	formatProcessingStatus(processingStatus) {
		if (!processingStatus || typeof processingStatus !== "string") {
			return "unknown";
		}

		return processingStatus.replace(/_/g, " ");
	}

	/**
	 * Display request error to user
	 */
	displayRequestError(error, fallbackMessage) {
		const message = error?.userMessage || fallbackMessage;
		const errorDetail = error?.errorDetail || error?.message || null;
		this.showErrorWithDetails(message, errorDetail);
	}

	/**
	 * Get CSRF token from form input
	 */
	getCSRFToken() {
		const token = document.querySelector("[name=csrfmiddlewaretoken]");
		return token ? token.value : "";
	}

	/**
	 * Set the generating state (loading indicators, button states)
	 */
	setGeneratingState(isGenerating) {
		this.isGenerating = isGenerating;

		// Update controls
		this.controls.setGenerateButtonState(!isGenerating);

		// Show/hide loading overlay
		if (this.loadingOverlay) {
			if (isGenerating) {
				this.loadingOverlay.classList.remove("d-none");
			} else {
				this.loadingOverlay.classList.add("d-none");
			}
		}

		// Keep status/error display visibility in sync with whether it has content
		if (this.errorDisplay) {
			const hasContent = this.errorDisplay
				.querySelector("p.error-message-text")
				?.textContent.trim();

			if (hasContent) {
				this.errorDisplay.classList.remove("d-none");
			} else {
				this.errorDisplay.classList.add("d-none");
			}
		}
	}

	/**
	 * Save the current spectrogram
	 */
	async saveSpectrogram() {
		if (!this.currentSpectrogramUrl) {
			console.warn("No spectrogram to save");
			return;
		}

		try {
			// Export from canvas
			const blob = await this.renderer.exportAsBlob();
			if (blob) {
				this.downloadBlob(blob, `spectrogram-${this.captureUuid}.png`);
			}
		} catch (error) {
			console.error("Error saving spectrogram:", error);
			this.showError("Failed to save spectrogram");
		}
	}

	/**
	 * Download a blob as a file
	 */
	downloadBlob(blob, filename) {
		const url = URL.createObjectURL(blob);
		const link = document.createElement("a");
		link.href = url;
		link.download = filename;
		document.body.appendChild(link);
		link.click();
		document.body.removeChild(link);
		URL.revokeObjectURL(url);
	}

	/**
	 * Show save button
	 */
	showSaveButton(show) {
		if (this.saveButton) {
			this.saveButton.style.display = show ? "block" : "none";
		}
	}

	/**
	 * Update status message
	 */
	updateStatus(message) {
		if (message) {
			this.showStatus(message);
			return;
		}

		this.clearStatusDisplay();
	}

	/**
	 * Show error message
	 */
	showError(message) {
		this.showErrorWithDetails(message);
	}

	/**
	 * Show non-error status message
	 */
	showStatus(message, detail = null) {
		if (!this.errorDisplay) {
			return;
		}

		const messageElement = this.errorDisplay.querySelector(
			"p.error-message-text",
		);
		const errorDetailElement = this.errorDisplay.querySelector(
			"p.error-detail-line",
		);

		setupErrorDisplay({
			messageElement,
			errorDetailElement,
			message,
			errorDetail: detail,
		});

		this.errorDisplay.classList.remove("d-none");
	}

	/**
	 * Clear status/error display
	 */
	clearStatusDisplay() {
		if (!this.errorDisplay) {
			return;
		}

		const messageElement = this.errorDisplay.querySelector(
			"p.error-message-text",
		);
		const errorDetailElement = this.errorDisplay.querySelector(
			"p.error-detail-line",
		);

		setupErrorDisplay({
			messageElement,
			errorDetailElement,
			message: "",
			errorDetail: null,
		});

		this.errorDisplay.classList.add("d-none");
	}

	/**
	 * Handle processing error with detailed information
	 */
	handleProcessingError(data) {
		const errorInfo = data.error_info || {};
		const hasSourceDataError = data.has_source_data_error || false;
		const processingStatus = data.processing_status;
		const { message, errorDetail } = generateErrorMessage(
			errorInfo,
			hasSourceDataError,
		);

		const detailParts = [];
		if (processingStatus) {
			detailParts.push(
				`Processing status: ${this.formatProcessingStatus(processingStatus)}`,
			);
		}
		if (errorDetail) {
			detailParts.push(errorDetail);
		}

		this.showErrorWithDetails(
			message,
			detailParts.length > 0 ? detailParts.join(" • ") : null,
		);
	}

	/**
	 * Show error message with details
	 */
	showErrorWithDetails(message, errorDetail = null) {
		// Clear image
		if (this.renderer) {
			this.renderer.clearImage();
		}

		// Setup error display using the centralized handler
		const errorDisplay = document.getElementById("visualizationErrorDisplay");
		if (errorDisplay) {
			const messageElement = errorDisplay.querySelector("p.error-message-text");
			const errorDetailElement = errorDisplay.querySelector(
				"p.error-detail-line",
			);

			setupErrorDisplay({
				messageElement,
				errorDetailElement,
				message,
				errorDetail,
			});

			errorDisplay.classList.remove("d-none");
		}
	}

	/**
	 * Clean up resources
	 */
	destroy() {
		// Stop polling
		this.stopStatusPolling();

		if (this.controls) {
			// Clean up controls if needed
		}

		if (this.renderer) {
			this.renderer.destroy();
		}

		// Clean up URL objects
		if (this.currentSpectrogramUrl) {
			URL.revokeObjectURL(this.currentSpectrogramUrl);
		}
	}
}

window.SpectrogramVisualization = SpectrogramVisualization;
