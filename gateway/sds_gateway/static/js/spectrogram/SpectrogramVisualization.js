/**
 * Main Spectrogram Visualization Class
 * Orchestrates all spectrogram components and handles the main functionality
 */

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
		this.statusMessage = null;
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
		this.statusMessage = document.getElementById("statusMessage");
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
			this.setGeneratingState(true);

			const settings = this.controls.getSettings();

			// Call the actual API
			await this.createSpectrogramJob(settings);
		} catch (error) {
			console.error("Error generating spectrogram:", error);
			this.showError(ERROR_MESSAGES.API_ERROR);
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

			if (!response.ok) {
				throw new Error(`HTTP ${response.status}: ${response.statusText}`);
			}

			const data = await response.json();

			if (!data.uuid) {
				throw new Error("Spectrogram job ID not found");
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

			if (!response.ok) {
				throw new Error(`HTTP ${response.status}: ${response.statusText}`);
			}

			const data = await response.json();

			if (data.processing_status === "completed") {
				// Job completed, stop polling and fetch result
				this.stopStatusPolling();
				await this.fetchSpectrogramResult();
			} else if (data.processing_status === "failed") {
				// Job failed
				this.stopStatusPolling();
				this.showError(
					data.processing_error || "Spectrogram generation failed",
				);
				this.setGeneratingState(false);
			}
			// If still processing, continue polling
		} catch (error) {
			console.error("Error checking job status:", error);
			// Continue polling on error
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

			if (!response.ok) {
				throw new Error(`HTTP ${response.status}: ${response.statusText}`);
			}

			const blob = await response.blob();

			// Revoke the old URL before creating a new one
			if (this.currentSpectrogramUrl) {
				URL.revokeObjectURL(this.currentSpectrogramUrl);
				this.currentSpectrogramUrl = null;
			}

			const renderResult = await this.renderer.renderFromImageBlob(blob);

			this.setGeneratingState(false);

			if (renderResult) {
				this.updateStatus(STATUS_MESSAGES.SUCCESS);
				this.showSaveButton(true);
			} else {
				this.showError("Failed to render spectrogram");
			}

			// Store the result for saving
			this.currentSpectrogramUrl = URL.createObjectURL(blob);
		} catch (error) {
			console.error("Error fetching spectrogram result:", error);
			this.showError("Failed to fetch spectrogram result");
			this.setGeneratingState(false);
		}
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

		// Hide status message during generation, show transparent overlay instead
		if (this.statusMessage) {
			this.statusMessage.style.display = isGenerating ? "none" : "block";
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
		if (this.statusMessage) {
			const statusText = this.statusMessage.querySelector("p");
			if (statusText) {
				statusText.textContent = message;
			}
		}
	}

	/**
	 * Show error message
	 */
	showError(message) {
		this.updateStatus(message);
		if (this.renderer) {
			this.renderer.clearImage();
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
