/**
 * Waterfall Visualization Class
 * Main orchestrator that coordinates all waterfall components
 */

import { generateErrorMessage, setupErrorDisplay } from "../errorHandler.js";
import {
	DEFAULT_COLOR_MAP,
	ERROR_MESSAGES,
	get_create_waterfall_endpoint,
	get_waterfall_result_endpoint,
	get_waterfall_status_endpoint,
} from "./constants.js";

class WaterfallVisualization {
	constructor(captureUuid) {
		this.captureUuid = captureUuid;

		// Component instances
		this.waterfallRenderer = null;
		this.periodogramChart = null;
		this.controls = null;

		// Data state
		this.waterfallData = [];
		this.parsedWaterfallData = []; // Cache parsed data to avoid re-parsing
		this.totalSlices = 0;
		this.scaleMin = null;
		this.scaleMax = null;
		this.isLoading = false;

		// Processing state
		this.isGenerating = false;
		this.currentJobId = null;
		this.pollingInterval = null;

		// Visualization state
		this.currentSliceIndex = 0;
		this.waterfallWindowStart = 0;
		this.colorMap = DEFAULT_COLOR_MAP;

		// Canvas references
		this.canvas = null;
		this.overlayCanvas = null;

		// Bind methods
		this.handleCanvasClick = this.handleCanvasClick.bind(this);
		this.handleCanvasMouseMove = this.handleCanvasMouseMove.bind(this);
		this.handleCanvasMouseLeave = this.handleCanvasMouseLeave.bind(this);
		this.resizeCanvas = this.resizeCanvas.bind(this);
	}

	/**
	 * Initialize the waterfall visualization
	 */
	async initialize() {
		try {
			// Initialize components first
			this.initializeComponents();

			// Set up event listeners
			this.setupEventListeners();

			// Load initial data
			await this.loadWaterfallData();

			// Set up event listeners for component communication
			this.setupComponentEventListeners();
		} catch (error) {
			console.error("Failed to initialize waterfall visualization:", error);
			this.showError("Failed to initialize visualization");
		}
	}

	/**
	 * Initialize all component instances
	 */
	initializeComponents() {
		// Initialize canvas and renderer
		this.initializeCanvas();
		this.waterfallRenderer = new WaterfallRenderer(
			this.canvas,
			this.overlayCanvas,
		);

		// Initialize periodogram chart
		this.periodogramChart = new PeriodogramChart("periodogramChart");
		this.periodogramChart.initialize();

		// Initialize controls with callback for slice changes
		this.controls = new WaterfallControls(
			(currentSliceIndex, waterfallWindowStart) => {
				const sliceChanged = this.currentSliceIndex !== currentSliceIndex;
				const windowChanged =
					this.waterfallWindowStart !== waterfallWindowStart;

				this.currentSliceIndex = currentSliceIndex;
				this.waterfallWindowStart = waterfallWindowStart;

				// Update renderer state
				this.waterfallRenderer.setCurrentSliceIndex(currentSliceIndex);
				this.waterfallRenderer.setWaterfallWindowStart(waterfallWindowStart);

				if (windowChanged) {
					this.renderWaterfall();
				}

				if (sliceChanged) {
					this.renderPeriodogram();
					this.updateSliceHighlights();
				}
			},
		);
		this.controls.setupEventListeners();
	}

	/**
	 * Initialize the canvas for waterfall plotting
	 */
	initializeCanvas() {
		this.canvas = document.getElementById("waterfallCanvas");
		if (!this.canvas) {
			throw new Error("Waterfall canvas not found");
		}

		this.overlayCanvas = document.getElementById("waterfallOverlayCanvas");
		if (!this.overlayCanvas) {
			throw new Error("Waterfall overlay canvas not found");
		}

		// Set canvas size based on container
		this.resizeCanvas();

		// Add resize listener
		window.addEventListener("resize", this.resizeCanvas);
	}

	/**
	 * Set up event listeners for component communication
	 */
	setupComponentEventListeners() {
		// Listen for color map change events
		document.addEventListener("waterfall:colorMapChanged", (event) => {
			const { colorMap } = event.detail;
			this.colorMap = colorMap;

			this.waterfallRenderer.setColorMap(colorMap);

			this.updateColorLegend();

			// Re-render waterfall with new color map
			this.renderWaterfall();
		});
	}

	/**
	 * Set up event listeners for canvas interactions
	 */
	setupEventListeners() {
		// Canvas click for slice selection
		if (this.canvas) {
			this.canvas.addEventListener("click", this.handleCanvasClick);
			this.canvas.addEventListener("mousemove", this.handleCanvasMouseMove);
			this.canvas.addEventListener("mouseleave", this.handleCanvasMouseLeave);
		}
	}

	/**
	 * Resize canvas to fit container
	 */
	resizeCanvas() {
		if (!this.canvas || !this.overlayCanvas) return;

		const container = this.canvas.parentElement;
		const rect = container.getBoundingClientRect();

		this.canvas.width = rect.width;
		this.canvas.height = rect.height;

		// Resize overlay canvas to match
		this.overlayCanvas.width = rect.width;
		this.overlayCanvas.height = rect.height;
		this.overlayCanvas.style.width = `${rect.width}px`;
		this.overlayCanvas.style.height = `${rect.height}px`;

		if (this.waterfallRenderer) {
			this.waterfallRenderer.resizeCanvas();
		}

		// Re-render if we have data
		if (this.parsedWaterfallData && this.parsedWaterfallData.length > 0) {
			this.render();
		}
	}

	/**
	 * Render the waterfall visualization
	 */
	render() {
		if (!this.parsedWaterfallData || this.parsedWaterfallData.length === 0) {
			return;
		}

		// Hide error display if it exists
		this.hideErrorDisplay();

		// Show visualization components
		this.showVisualizationComponents();

		// Render waterfall with cached parsed data
		this.renderWaterfall();

		// Render periodogram
		this.renderPeriodogram();
	}

	/**
	 * Render the periodogram chart
	 */
	renderPeriodogram() {
		if (!this.periodogramChart || this.parsedWaterfallData.length === 0) return;
		this.periodogramChart.renderPeriodogram(
			this.parsedWaterfallData[this.currentSliceIndex],
		);
	}

	/**
	 * Render only the waterfall plot (for color map changes)
	 */
	renderWaterfall() {
		if (!this.parsedWaterfallData || this.parsedWaterfallData.length === 0) {
			return;
		}

		// Render waterfall with cached parsed data - let renderer handle slicing
		this.waterfallRenderer.renderWaterfall(
			this.parsedWaterfallData,
			this.totalSlices,
		);
	}

	/**
	 * Update only slice highlights without re-rendering everything
	 */
	updateSliceHighlights() {
		if (!this.waterfallRenderer) return;
		this.waterfallRenderer.updateOverlay();
	}

	/**
	 * Handle canvas click for slice selection
	 */
	handleCanvasClick(event) {
		if (!this.canvas) return;

		const rect = this.canvas.getBoundingClientRect();
		const y = event.clientY - rect.top;

		// Calculate which slice was clicked
		const maxVisibleSlices = Math.min(
			this.totalSlices,
			this.waterfallRenderer.WATERFALL_WINDOW_SIZE,
		);
		const plotHeight =
			this.canvas.height -
			this.waterfallRenderer.TOP_MARGIN -
			this.waterfallRenderer.BOTTOM_MARGIN;
		const sliceHeight = plotHeight / maxVisibleSlices;

		// Calculate clicked slice index
		const adjustedY = y - this.waterfallRenderer.TOP_MARGIN;
		if (adjustedY < 0 || adjustedY > plotHeight) return; // Click outside plot area

		const clickedRow = Math.floor(adjustedY / sliceHeight);
		const clickedSliceIndex =
			this.waterfallWindowStart +
			this.waterfallRenderer.WATERFALL_WINDOW_SIZE -
			clickedRow -
			1;

		// Validate the index is within bounds
		if (clickedSliceIndex >= 0 && clickedSliceIndex < this.totalSlices) {
			// Update visualization state
			this.currentSliceIndex = clickedSliceIndex;
			this.waterfallRenderer.setCurrentSliceIndex(clickedSliceIndex);

			// Update controls UI
			this.controls.setCurrentSliceIndex(clickedSliceIndex);

			this.updateSliceHighlights();
			this.renderPeriodogram();
		}
	}

	/**
	 * Handle canvas mouse move for hover effects
	 */
	handleCanvasMouseMove(event) {
		if (!this.canvas) return;

		const rect = this.canvas.getBoundingClientRect();
		const y = event.clientY - rect.top;

		// Calculate which slice is being hovered
		const maxVisibleSlices = Math.min(
			this.totalSlices,
			this.waterfallRenderer.WATERFALL_WINDOW_SIZE,
		);
		const plotHeight =
			this.canvas.height -
			this.waterfallRenderer.TOP_MARGIN -
			this.waterfallRenderer.BOTTOM_MARGIN;
		const sliceHeight = plotHeight / maxVisibleSlices;

		// Calculate hovered slice index
		const adjustedY = y - this.waterfallRenderer.TOP_MARGIN;
		if (adjustedY < 0 || adjustedY > plotHeight) {
			this.canvas.style.cursor = "default";
			this.waterfallRenderer.setHoveredSliceIndex(null);
			this.controls.setHoveredSliceIndex(null);
			this.waterfallRenderer.updateOverlay();
			return;
		}

		const hoveredRow = Math.floor(adjustedY / sliceHeight);
		const hoveredSliceIndex =
			this.waterfallWindowStart +
			this.waterfallRenderer.WATERFALL_WINDOW_SIZE -
			hoveredRow -
			1;

		// Update cursor style based on whether we're hovering over a valid slice
		if (hoveredSliceIndex >= 0 && hoveredSliceIndex < this.totalSlices) {
			this.canvas.style.cursor = "pointer";
			this.waterfallRenderer.setHoveredSliceIndex(hoveredSliceIndex);
			this.controls.setHoveredSliceIndex(hoveredSliceIndex);
		} else {
			this.canvas.style.cursor = "default";
			this.waterfallRenderer.setHoveredSliceIndex(null);
			this.controls.setHoveredSliceIndex(null);
		}

		// Always update overlay to reflect current hover state
		this.waterfallRenderer.updateOverlay();
	}

	/**
	 * Handle canvas mouse leave
	 */
	handleCanvasMouseLeave() {
		if (this.canvas) {
			this.canvas.style.cursor = "default";
		}
		// Clear hover state and update overlay
		this.waterfallRenderer.setHoveredSliceIndex(null);
		this.controls.setHoveredSliceIndex(null);
		this.waterfallRenderer.updateOverlay();
	}

	/**
	 * Update the color legend showing dB scale
	 */
	updateColorLegend() {
		const legendElement = document.getElementById("colorLegend");
		if (!legendElement) return;

		const legendGradient = legendElement.querySelector(".legend-gradient");
		const legendLabels = legendElement.querySelector(".legend-labels");

		if (!legendGradient || !legendLabels) return;

		// Create CSS gradient based on selected color map
		const scaleMin = this.scaleMin || -130;
		const scaleMax = this.scaleMax || 0;

		// Generate gradient stops for the selected color map
		const gradientStops = this.waterfallRenderer.generateColorMapGradient();
		legendGradient.style.background = gradientStops;

		// Clear existing labels
		legendLabels.innerHTML = "";

		// Add dB labels
		const dbStep = 20; // Draw label every 20 dB
		for (let dbVal = scaleMax; dbVal >= scaleMin; dbVal -= dbStep) {
			const label = document.createElement("div");
			// Round to nearest integer
			const roundedDb = Math.round(dbVal);
			label.textContent = `${roundedDb}`;
			label.style.fontSize = "0.7rem";
			label.style.color = "#000";
			label.style.textAlign = "right";
			label.style.margin = "2px 0";
			legendLabels.appendChild(label);
		}
	}

	/**
	 * Load waterfall data from the SDS API
	 */
	async loadWaterfallData() {
		try {
			this.isLoading = true;
			this.showLoading(true);

			// First, get the post-processing status to check if waterfall data is available
			const statusResponse = await fetch(
				`/api/latest/assets/captures/${this.captureUuid}/post_processing_status/`,
			);
			if (!statusResponse.ok) {
				throw new Error(
					`Failed to get post-processing status: ${statusResponse.status}`,
				);
			}

			const statusData = await statusResponse.json();
			const waterfallData = statusData.post_processed_data.find(
				(data) =>
					data.processing_type === "waterfall" &&
					data.processing_status === "completed",
			);

			if (!waterfallData) {
				// No waterfall data available, trigger processing
				await this.triggerWaterfallProcessing();
				return;
			}

			// Get the waterfall data file
			const dataResponse = await fetch(
				`/api/latest/assets/captures/${this.captureUuid}/download_post_processed_data/?processing_type=waterfall`,
			);

			if (!dataResponse.ok) {
				throw new Error(
					`Failed to download waterfall data: ${dataResponse.status}`,
				);
			}

			const waterfallJson = await dataResponse.json();
			this.waterfallData = waterfallJson;
			this.totalSlices = waterfallJson.length;

			// Parse all waterfall data once and cache it
			this.parsedWaterfallData = this.waterfallData.map((slice) => ({
				...slice,
				data: this.parseWaterfallData(slice.data),
			}));

			// Calculate power bounds from all data
			this.calculatePowerBounds();

			this.isLoading = false;
			this.showLoading(false);

			this.controls.setTotalSlices(this.totalSlices);
			this.waterfallRenderer.setScaleBounds(this.scaleMin, this.scaleMax);
			this.periodogramChart.updateYAxisBounds(this.scaleMin, this.scaleMax);
			this.updateColorLegend();

			this.render();
		} catch (error) {
			console.error("Failed to load waterfall data:", error);
			this.isLoading = false;
			this.showLoading(false);

			// Provide more helpful error messages
			let userMessage = error.message;
			if (error.message.includes("404")) {
				userMessage =
					"Capture not found or you do not have permission to access it.";
			} else if (error.message.includes("403")) {
				userMessage = "You do not have permission to access this capture.";
			} else if (error.message.includes("500")) {
				userMessage = "Server error occurred. Please try again later.";
			}

			this.showError(userMessage);
		}
	}

	/**
	 * Trigger waterfall processing when data is not available
	 */
	async triggerWaterfallProcessing() {
		// Check if we are already generating
		if (this.isGenerating) {
			return;
		}

		try {
			this.setGeneratingState(true);

			// Create waterfall processing job
			await this.createWaterfallJob();
		} catch (error) {
			console.error("Error triggering waterfall processing:", error);
			this.showError(ERROR_MESSAGES.API_ERROR);
			this.setGeneratingState(false);
		}
	}

	/**
	 * Create a waterfall generation job via API
	 */
	async createWaterfallJob() {
		try {
			const response = await fetch(
				get_create_waterfall_endpoint(this.captureUuid),
				{
					method: "POST",
					headers: {
						"X-CSRFToken": this.getCSRFToken(),
					},
				},
			);

			if (!response.ok) {
				throw new Error(`HTTP ${response.status}: ${response.statusText}`);
			}

			const data = await response.json();

			if (!data.uuid) {
				throw new Error("Waterfall job ID not found");
			}
			this.currentJobId = data.uuid;

			// Start polling for status
			this.startStatusPolling();
		} catch (error) {
			console.error("Error creating waterfall job:", error);
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
				get_waterfall_status_endpoint(this.captureUuid, this.currentJobId),
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
				await this.fetchWaterfallResult();
			} else if (data.processing_status === "failed") {
				// Job failed
				this.stopStatusPolling();
				this.handleProcessingError(data);
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
	 * Fetch the completed waterfall result
	 */
	async fetchWaterfallResult() {
		try {
			const response = await fetch(
				get_waterfall_result_endpoint(this.captureUuid, this.currentJobId),
				{
					headers: {
						"X-CSRFToken": this.getCSRFToken(),
					},
				},
			);

			if (!response.ok) {
				throw new Error(`HTTP ${response.status}: ${response.statusText}`);
			}

			const waterfallJson = await response.json();

			this.waterfallData = waterfallJson;
			this.totalSlices = waterfallJson.length;

			// Parse all waterfall data once and cache it
			this.parsedWaterfallData = this.waterfallData.map((slice) => ({
				...slice,
				data: this.parseWaterfallData(slice.data),
			}));

			// Calculate power bounds from all data
			this.calculatePowerBounds();

			this.setGeneratingState(false);

			this.controls.setTotalSlices(this.totalSlices);
			this.waterfallRenderer.setScaleBounds(this.scaleMin, this.scaleMax);
			this.periodogramChart.updateYAxisBounds(this.scaleMin, this.scaleMax);
			this.updateColorLegend();

			this.render();
		} catch (error) {
			console.error("Error fetching waterfall result:", error);
			this.showError("Failed to fetch waterfall result");
			this.setGeneratingState(false);
		}
	}

	/**
	 * Set the generating state (loading indicators, button states)
	 */
	setGeneratingState(isGenerating) {
		this.isGenerating = isGenerating;
		this.isLoading = isGenerating;

		// Show/hide loading overlay
		this.showLoading(isGenerating);
	}

	/**
	 * Get CSRF token from form input
	 */
	getCSRFToken() {
		const token = document.querySelector("[name=csrfmiddlewaretoken]");
		return token ? token.value : "";
	}

	/**
	 * Parse base64 waterfall data
	 */
	parseWaterfallData(base64Data) {
		try {
			const binaryString = atob(base64Data);
			const bytes = new Uint8Array(binaryString.length);
			for (let i = 0; i < binaryString.length; i++) {
				bytes[i] = binaryString.charCodeAt(i);
			}

			const floatArray = new Float32Array(bytes.buffer);
			return Array.from(floatArray);
		} catch (error) {
			console.error("Failed to parse waterfall data:", error);
			return null;
		}
	}

	/**
	 * Calculate power bounds from all waterfall data
	 */
	calculatePowerBounds() {
		if (this.parsedWaterfallData.length === 0) {
			// Fallback to default bounds if no data
			this.scaleMin = -130;
			this.scaleMax = 0;
			return;
		}

		let globalMin = Number.POSITIVE_INFINITY;
		let globalMax = Number.NEGATIVE_INFINITY;

		// Iterate through all parsed slices to find global min/max
		for (const slice of this.parsedWaterfallData) {
			if (slice.data && slice.data.length > 0) {
				const sliceMin = Math.min(...slice.data);
				const sliceMax = Math.max(...slice.data);

				globalMin = Math.min(globalMin, sliceMin);
				globalMax = Math.max(globalMax, sliceMax);
			}
		}

		// If we found valid data, use it; otherwise fall back to defaults
		if (
			globalMin !== Number.POSITIVE_INFINITY &&
			globalMax !== Number.NEGATIVE_INFINITY
		) {
			// Add a small margin (5%) to the bounds for better visualization
			const margin = (globalMax - globalMin) * 0.05;
			this.scaleMin = globalMin - margin;
			this.scaleMax = globalMax + margin;
		} else {
			// Fallback to default bounds
			this.scaleMin = -130;
			this.scaleMax = 0;
		}
	}

	/**
	 * Get waterfall data for a specific range
	 */
	getWaterfallRange(startIndex, endIndex) {
		const start = Math.max(0, startIndex);
		const end = Math.min(this.totalSlices, endIndex);

		if (start >= end) return [];

		return this.parsedWaterfallData.slice(start, end);
	}

	/**
	 * Show/hide loading state
	 */
	showLoading(show) {
		const overlay = document.getElementById("loadingOverlay");
		if (overlay) {
			if (show) {
				overlay.classList.remove("d-none");
			} else {
				overlay.classList.add("d-none");
			}
		}
	}

	/**
	 * Hide all visualization components
	 */
	hideVisualizationComponents() {
		// Hide waterfall canvas
		if (this.canvas) {
			this.canvas.classList.add("d-none");
		}
		if (this.overlayCanvas) {
			this.overlayCanvas.classList.add("d-none");
		}

		// Hide periodogram chart
		const periodogramContainer = document.getElementById("periodogramChart");
		if (periodogramContainer) {
			periodogramContainer.classList.add("d-none");
		}

		// Hide color legend
		const colorLegend = document.getElementById("colorLegend");
		if (colorLegend) {
			colorLegend.classList.add("d-none");
		}
	}

	/**
	 * Hide error display
	 */
	hideErrorDisplay() {
		const errorDisplay = document.getElementById("waterfallErrorDisplay");
		if (errorDisplay) {
			errorDisplay.classList.add("d-none");
		}
	}

	/**
	 * Show all visualization components
	 */
	showVisualizationComponents() {
		// Show waterfall canvas
		if (this.canvas) {
			this.canvas.classList.remove("d-none");
		}
		if (this.overlayCanvas) {
			this.overlayCanvas.classList.remove("d-none");
		}

		// Show periodogram chart
		const periodogramContainer = document.getElementById("periodogramChart");
		if (periodogramContainer) {
			periodogramContainer.classList.remove("d-none");
		}

		// Show color legend
		const colorLegend = document.getElementById("colorLegend");
		if (colorLegend) {
			colorLegend.classList.remove("d-none");
		}
	}

	/**
	 * Handle processing error with detailed information
	 */
	handleProcessingError(data) {
		const errorInfo = data.error_info || {};
		const hasSourceDataError = data.has_source_data_error || false;
		const userMessage = generateErrorMessage(errorInfo, hasSourceDataError);
		this.showError(userMessage, errorInfo);
	}

	/**
	 * Show error message with collapsible details
	 */
	showError(message, errorInfo = {}) {
		// Clear data state first
		this.waterfallData = [];
		this.parsedWaterfallData = [];
		this.totalSlices = 0;
		this.scaleMin = null;
		this.scaleMax = null;

		// Hide all visualization components
		this.hideVisualizationComponents();

		// Update controls to reflect empty state
		if (this.controls) {
			this.controls.setTotalSlices(0);
		}

		// Update error display with details
		const errorDisplay = document.getElementById("waterfallErrorDisplay");
		if (errorDisplay) {
			const messageElement = errorDisplay.querySelector("p.error-message-text");
			const detailsContainer = errorDisplay.querySelector(
				".error-details-container",
			);
			const detailsContent = document.getElementById(
				"waterfallErrorDetailsContent",
			);
			const toggleButton = document.getElementById(
				"waterfallErrorDetailsToggle",
			);

			setupErrorDisplay({
				messageElement,
				detailsContainer,
				detailsContent,
				toggleButton,
				message,
				errorInfo,
			});

			errorDisplay.classList.remove("d-none");
		}
	}

	/**
	 * Cleanup resources
	 */
	destroy() {
		// Stop polling
		this.stopStatusPolling();

		// Cleanup components
		if (this.waterfallRenderer) {
			this.waterfallRenderer.destroy();
		}
		if (this.periodogramChart) {
			this.periodogramChart.destroy();
		}
		if (this.controls) {
			this.controls.destroy();
		}

		// Remove event listeners
		window.removeEventListener("resize", this.resizeCanvas);
		if (this.canvas) {
			this.canvas.removeEventListener("click", this.handleCanvasClick);
			this.canvas.removeEventListener("mousemove", this.handleCanvasMouseMove);
			this.canvas.removeEventListener(
				"mouseleave",
				this.handleCanvasMouseLeave,
			);
		}

		// Clear references
		this.canvas = null;
		this.overlayCanvas = null;
	}
}

// Make the class globally available
window.WaterfallVisualization = WaterfallVisualization;
