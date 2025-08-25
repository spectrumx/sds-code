/**
 * Main Spectrogram Visualization Class
 * Orchestrates all spectrogram components and handles the main functionality
 */

import { SpectrogramControls } from "./SpectrogramControls.js";
import { SpectrogramRenderer } from "./SpectrogramRenderer.js";
import { API_ENDPOINTS, ERROR_MESSAGES, STATUS_MESSAGES } from "./constants.js";

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
			this.checkForDefaultSpectrogram();
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

		// Wait for canvas to be available and initialize the renderer
		try {
			const canvasReady = await this.renderer.waitForCanvas();
			if (canvasReady) {
				if (!this.renderer.initializeCanvas()) {
					console.error("Failed to initialize spectrogram renderer canvas");
				}
			} else {
				console.error("Canvas element not found after waiting");
			}
		} catch (error) {
			console.error("Error during canvas initialization:", error);
		}

		// Set up control callbacks
		this.controls.setGenerateCallback(() => this.generateSpectrogram());
	}

	/**
	 * Set up event handlers
	 */
	setupEventHandlers() {
		// Save button click handler
		if (this.saveButton) {
			this.saveButton.addEventListener("click", () => this.saveSpectrogram());
		}

		// Window resize handler
		window.addEventListener("resize", () => this.handleResize());
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
			this.updateStatus(STATUS_MESSAGES.GENERATING);

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
			const response = await fetch(
				API_ENDPOINTS.createSpectrogram.replace(
					"{capture_uuid}",
					this.captureUuid,
				),
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
						dimensions: {
							width: window.innerWidth,
							height: window.innerHeight,
						},
					}),
				},
			);

			if (!response.ok) {
				throw new Error(`HTTP ${response.status}: ${response.statusText}`);
			}

			const data = await response.json();
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
		}, 2000); // Poll every 2 seconds
	}

	/**
	 * Check the status of the current job
	 */
	async checkJobStatus() {
		if (!this.currentJobId) return;

		try {
			const response = await fetch(
				`${API_ENDPOINTS.getSpectrogramStatus.replace("{capture_uuid}", this.captureUuid)}?job_id=${this.currentJobId}`,
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
				`${API_ENDPOINTS.getSpectrogramResult.replace("{capture_uuid}", this.captureUuid)}?job_id=${this.currentJobId}`,
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
			await this.renderer.renderFromImageBlob(blob);

			this.setGeneratingState(false);
			this.showSaveButton(true);

			// Store the result for saving
			this.currentSpectrogramUrl = URL.createObjectURL(blob);
		} catch (error) {
			console.error("Error fetching spectrogram result:", error);
			this.showError("Failed to fetch spectrogram result");
			this.setGeneratingState(false);
		}
	}

	/**
	 * Check if there's a default spectrogram available for this capture
	 */
	async checkForDefaultSpectrogram() {
		try {
			this.updateStatus("Checking for existing spectrogram...");

			// Check if there's a completed spectrogram for this capture
			const response = await fetch(
				`/api/v1/assets/captures/${this.captureUuid}/post_processing_status/`,
				{
					headers: {
						"X-CSRFToken": this.getCSRFToken(),
					},
				},
			);

			if (response.ok) {
				const data = await response.json();
				const spectrogramData = data.post_processed_data?.find(
					(item) =>
						item.processing_type === "spectrogram" &&
						item.processing_status === "completed",
				);

				if (spectrogramData) {
					// Found a completed spectrogram, load it
					this.updateStatus("Loading existing spectrogram...");
					await this.loadExistingSpectrogram(spectrogramData.uuid);
					return;
				}
			}

			// No existing spectrogram found
			this.updateStatus(STATUS_MESSAGES.READY);
		} catch (error) {
			console.error("Error checking for default spectrogram:", error);
			this.updateStatus(STATUS_MESSAGES.READY);
		}
	}

	/**
	 * Load an existing spectrogram
	 */
	async loadExistingSpectrogram(spectrogramUuid) {
		try {
			const response = await fetch(
				`/api/v1/assets/captures/${this.captureUuid}/download_post_processed_data/?processing_type=spectrogram`,
				{
					headers: {
						"X-CSRFToken": this.getCSRFToken(),
					},
				},
			);

			if (response.ok) {
				const blob = await response.blob();
				await this.renderer.renderFromImageBlob(blob);

				this.updateStatus("");
				this.showSaveButton(true);

				// Store the result for saving
				this.currentSpectrogramUrl = URL.createObjectURL(blob);
			} else {
				throw new Error("Failed to download existing spectrogram");
			}
		} catch (error) {
			console.error("Error loading existing spectrogram:", error);
			this.updateStatus("Failed to load spectrogram");
		}
	}

	/**
	 * Get CSRF token from cookies
	 */
	getCSRFToken() {
		const name = "csrftoken";
		let cookieValue = null;
		if (document.cookie && document.cookie !== "") {
			const cookies = document.cookie.split(";");
			for (let i = 0; i < cookies.length; i++) {
				const cookie = cookies[i].trim();
				if (cookie.substring(0, name.length + 1) === `${name}=`) {
					cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
					break;
				}
			}
		}
		return cookieValue;
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
			this.loadingOverlay.style.display = isGenerating ? "flex" : "none";
		}

		// Show/hide status message
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
			this.renderer.showErrorMessage(message);
		}
	}

	/**
	 * Handle window resize
	 */
	handleResize() {
		// Could implement responsive canvas sizing here
		console.log("Window resized, spectrogram visualization updated");
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

		// Remove event listeners
		window.removeEventListener("resize", () => this.handleResize());

		// Clean up URL objects
		if (this.currentSpectrogramUrl) {
			URL.revokeObjectURL(this.currentSpectrogramUrl);
		}
	}
}

window.SpectrogramVisualization = SpectrogramVisualization;
