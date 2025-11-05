/**
 * Waterfall Visualization Class
 * Main orchestrator that coordinates all waterfall components
 */

import { generateErrorMessage, setupErrorDisplay } from "../errorHandler.js";
import { WaterfallAPIClient } from "./WaterfallAPIClient.js";
import { WaterfallCacheManager } from "./WaterfallCacheManager.js";
import {
	DEFAULT_COLOR_MAP,
	ERROR_MESSAGES,
	PREFETCH_DISTANCE,
	PREFETCH_TRIGGER,
	WATERFALL_WINDOW_SIZE,
} from "./constants.js";

class WaterfallVisualization {
	constructor(captureUuid) {
		this.captureUuid = captureUuid;

		// Component instances
		this.waterfallRenderer = null;
		this.periodogramChart = null;
		this.controls = null;

		// Data state
		this.totalSlices = 0;
		this.scaleMin = null;
		this.scaleMax = null;
		this.isLoading = false;

		// Cache manager for slice loading
		this.cacheManager = null;
		this.jobId = null; // Store job ID for range requests

		// API client
		this.apiClient = new WaterfallAPIClient(captureUuid);

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
					// Check if we need to load more slices for the new window
					this.ensureSlicesLoaded(waterfallWindowStart);
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
		if (this.cacheManager && this.totalSlices > 0) {
			this.render();
		}
	}

	/**
	 * Render the waterfall visualization
	 */
	render() {
		if (this.totalSlices === 0) {
			return;
		}

		// Hide error display if it exists
		this.hideErrorDisplay();

		// Show visualization components
		this.showVisualizationComponents();

		// Ensure slices for current window are loaded
		this.ensureSlicesLoaded(this.waterfallWindowStart);

		// Render waterfall with cached parsed data
		this.renderWaterfall();

		// Render periodogram (only if slice is loaded)
		if (
			this.cacheManager &&
			this.currentSliceIndex >= 0 &&
			this.currentSliceIndex < this.totalSlices &&
			this.cacheManager.sliceData.get(this.currentSliceIndex)
		) {
			this.renderPeriodogram();
		}
	}

	/**
	 * Render the periodogram chart
	 */
	renderPeriodogram() {
		if (!this.periodogramChart || !this.cacheManager) return;

		// Get slice from cache manager
		const slice = this.cacheManager.sliceData.get(this.currentSliceIndex);
		if (!slice || !slice.data) {
			return; // Slice not loaded yet
		}

		this.periodogramChart.renderPeriodogram(slice);
	}

	/**
	 * Render only the waterfall plot (for color map changes)
	 */
	renderWaterfall() {
		if (this.totalSlices === 0 || !this.cacheManager) {
			return;
		}

		// Check if window is fully loaded
		const isFullyLoaded = this.isWindowFullyLoaded();

		if (!isFullyLoaded) {
			// Show loading overlay if window is not fully loaded
			this.showLoadingOverlay();
			return;
		}

		// Hide loading overlay
		this.hideLoadingOverlay();

		// Get slices for the current window
		const windowSize = WATERFALL_WINDOW_SIZE;
		const startIndex = this.waterfallWindowStart;
		const endIndex = Math.min(startIndex + windowSize, this.totalSlices);

		// Since window is fully loaded, all slices should be available
		const loadedSlices = this.cacheManager.getRangeSlices(startIndex, endIndex);
		if (loadedSlices.some((slice) => slice === null)) {
			this.showError("Failed to load waterfall data");
			return;
		}

		// Render with fully-loaded data
		this.waterfallRenderer.renderWaterfall(
			loadedSlices,
			this.totalSlices,
			startIndex,
		);
	}

	/**
	 * Show loading overlay
	 */
	showLoadingOverlay() {
		const overlay = document.getElementById("waterfallLoadingOverlay");
		if (overlay) {
			overlay.classList.remove("d-none");
		}
		if (this.controls) {
			this.controls.setLoading(true);
		}
	}

	/**
	 * Hide loading overlay
	 */
	hideLoadingOverlay() {
		const overlay = document.getElementById("waterfallLoadingOverlay");
		if (overlay) {
			overlay.classList.add("d-none");
		}
		if (this.controls) {
			this.controls.setLoading(false);
		}
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
			const statusData = await this.apiClient.getPostProcessingStatus();
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

			// Store job ID for range requests
			this.jobId = waterfallData.uuid;

			// Get metadata first to know total slices and power bounds
			await this.loadWaterfallMetadata();

			// Initialize cache manager
			this.cacheManager = new WaterfallCacheManager(this.totalSlices);

			// Load initial window of slices
			await this.loadWaterfallRange(
				0,
				Math.min(WATERFALL_WINDOW_SIZE, this.totalSlices),
			);

			this.isLoading = false;
			this.showLoading(false);

			// Initial render will happen after first range loads
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
	 * Load waterfall metadata
	 */
	async loadWaterfallMetadata() {
		if (!this.jobId) {
			throw new Error("Job ID not available");
		}

		const metadata = await this.apiClient.getWaterfallMetadata(this.jobId);
		this.totalSlices = metadata.slices_processed || 0;
		this.scaleMin = metadata.power_scale_min ?? -130.0;
		this.scaleMax = metadata.power_scale_max ?? 0.0;

		// Update visualization bounds
		if (this.waterfallRenderer) {
			this.waterfallRenderer.setScaleBounds(this.scaleMin, this.scaleMax);
		}
		if (this.periodogramChart) {
			this.periodogramChart.updateYAxisBounds(this.scaleMin, this.scaleMax);
		}
		if (this.controls) {
			this.controls.setTotalSlices(this.totalSlices);
		}
		this.updateColorLegend();
	}

	/**
	 * Load a range of waterfall slices
	 */
	async loadWaterfallRange(startIndex, endIndex) {
		if (!this.jobId || !this.cacheManager) {
			throw new Error("Job ID or cache manager not available");
		}

		// Clamp indices
		startIndex = Math.max(0, startIndex);
		endIndex = Math.min(endIndex, this.totalSlices);

		if (startIndex >= endIndex) {
			return;
		}

		// Check if this range is already loaded or loading
		if (this.cacheManager.isRangeLoading(startIndex, endIndex)) {
			return; // Already loading this range
		}

		if (this.cacheManager.isRangeLoaded(startIndex, endIndex)) {
			return; // Already loaded
		}

		this.cacheManager.markRangeLoading(startIndex, endIndex);

		try {
			const slices = await this.apiClient.loadWaterfallRange(
				this.jobId,
				startIndex,
				endIndex,
			);

			// Parse slices
			const parsedSlices = slices.map((slice) => ({
				...slice,
				data: this.parseWaterfallData(slice.data),
			}));

			// Store in cache manager
			this.cacheManager.addLoadedSlices(startIndex, parsedSlices);

			// Trigger render
			this.render();
		} finally {
			this.cacheManager.markRangeLoaded(startIndex, endIndex);
		}
	}

	/**
	 * Ensure slices for a given window or slice index are loaded
	 * Uses separate prefetch trigger threshold and prefetch distance:
	 * - Trigger threshold: Only prefetch when within windowSize * PREFETCH_TRIGGER of unfetched data
	 * - Prefetch distance: Once triggered, load up to windowSize * PREFETCH_DISTANCE on both sides
	 */
	async ensureSlicesLoaded(windowStart) {
		if (this.totalSlices === 0 || !this.jobId || !this.cacheManager) {
			return;
		}

		const windowEnd = windowStart + WATERFALL_WINDOW_SIZE;

		// Prefetch trigger threshold: check the range around the window
		const triggerStart = Math.max(
			windowStart - WATERFALL_WINDOW_SIZE * PREFETCH_TRIGGER,
			0,
		);
		const triggerEnd = Math.min(
			windowEnd + WATERFALL_WINDOW_SIZE * PREFETCH_TRIGGER,
			this.totalSlices,
		);

		// Check if there's any missing data within the trigger threshold
		const missingRangesInTrigger = this.cacheManager.getMissingRanges(
			triggerStart,
			triggerEnd,
		);

		// Only proceed with prefetching if we're approaching unfetched data
		if (missingRangesInTrigger.length === 0) {
			// No missing data within trigger threshold, no need to prefetch
			return;
		}

		// Check if all missing ranges in the trigger area are already being loaded
		const allMissingRangesAreLoading = missingRangesInTrigger.every(
			([missingStart, missingEnd]) =>
				this.cacheManager.isRangeContainedByLoadingRange(
					missingStart,
					missingEnd,
				),
		);

		if (allMissingRangesAreLoading) {
			// All missing ranges in trigger area are already being loaded, don't start a new request
			return;
		}

		// Prefetch distance: load up to WATERFALL_WINDOW_SIZE * PREFETCH_DISTANCE on both sides when triggered
		const prefetchStart = Math.max(
			windowStart - WATERFALL_WINDOW_SIZE * PREFETCH_DISTANCE,
			0,
		);
		const prefetchEnd = Math.min(
			windowEnd + WATERFALL_WINDOW_SIZE * PREFETCH_DISTANCE,
			this.totalSlices,
		);

		// Get all missing ranges in the prefetch range
		const missingRanges = this.cacheManager.getMissingRanges(
			prefetchStart,
			prefetchEnd,
		);

		// Load missing ranges (limit concurrent requests)
		const maxConcurrent = this.cacheManager.maxConcurrentLoads;
		let activeLoads = 0;
		const loadQueue = [...missingRanges];

		const processQueue = async () => {
			while (loadQueue.length > 0 || activeLoads > 0) {
				if (activeLoads < maxConcurrent && loadQueue.length > 0) {
					const [start, end] = loadQueue.shift();
					activeLoads++;
					this.loadWaterfallRange(start, end)
						.catch((error) => {
							console.error(`Error loading range ${start}-${end}:`, error);
						})
						.finally(() => {
							activeLoads--;
						});
				} else {
					// Wait a bit before checking again
					await new Promise((resolve) => setTimeout(resolve, 50));
				}
			}
		};

		// Start loading (don't await to avoid blocking)
		processQueue();
	}

	/**
	 * Check if the current window is fully loaded
	 */
	isWindowFullyLoaded() {
		if (this.totalSlices === 0 || !this.cacheManager) {
			return false;
		}

		const windowSize = WATERFALL_WINDOW_SIZE;
		const startIndex = this.waterfallWindowStart;
		const endIndex = Math.min(startIndex + windowSize, this.totalSlices);

		return this.cacheManager.isRangeLoaded(startIndex, endIndex);
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
			const data = await this.apiClient.createWaterfallJob();
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
			const data = await this.apiClient.getWaterfallJobStatus(
				this.currentJobId,
			);

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
			// Store job ID for range requests
			this.jobId = this.currentJobId;

			// Get metadata first to know total slices and power bounds
			await this.loadWaterfallMetadata();

			// Initialize cache manager
			this.cacheManager = new WaterfallCacheManager(this.totalSlices);

			// Load initial window of slices
			await this.loadWaterfallRange(
				0,
				Math.min(WATERFALL_WINDOW_SIZE, this.totalSlices),
			);

			this.setGeneratingState(false);

			// Initial render will happen after first range loads
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
		const errorDisplay = document.getElementById("visualizationErrorDisplay");
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
		const { message, errorDetail } = generateErrorMessage(
			errorInfo,
			hasSourceDataError,
		);
		this.showError(message, errorDetail);
	}

	/**
	 * Show error message
	 */
	showError(message, errorDetail = null) {
		// Clear data state first
		if (this.cacheManager) {
			this.cacheManager.clear();
		}
		this.totalSlices = 0;
		this.scaleMin = null;
		this.scaleMax = null;

		// Hide all visualization components
		this.hideVisualizationComponents();

		// Update controls to reflect empty state
		if (this.controls) {
			this.controls.setTotalSlices(0);
		}

		// Update error display
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
