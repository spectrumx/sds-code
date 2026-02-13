/**
 * Waterfall Visualization Class
 * Main orchestrator that coordinates all waterfall components
 */

import { generateErrorMessage, setupErrorDisplay } from "../errorHandler.js";
import WaterfallSliceCache from "./WaterfallSliceCache.js";
import WaterfallSliceLoader from "./WaterfallSliceLoader.js";
import {
	DEFAULT_COLOR_MAP,
	DEFAULT_SCALE_MAX,
	DEFAULT_SCALE_MIN,
	ERROR_MESSAGES,
	LARGE_CAPTURE_THRESHOLD,
	PREFETCH_DISTANCE,
	PREFETCH_TRIGGER,
	WATERFALL_WINDOW_SIZE,
	get_create_waterfall_endpoint,
	get_waterfall_metadata_stream_endpoint,
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

		// Cache and loader for streaming
		this.sliceCache = null;
		this.sliceLoader = null;

		// Data state
		this.waterfallData = [];
		this.parsedWaterfallData = []; // Cache parsed data to avoid re-parsing (legacy, will be phased out)
		this.totalSlices = 0;
		this.scaleMin = null;
		this.scaleMax = null;
		this.isLoading = false;
		this.isStreamingMode = false; // Flag to indicate streaming mode
		this._isLoadingWindow = false; // Flag to prevent redundant loads during render
		this._pendingRender = false; // Flag to batch renders via requestAnimationFrame
		this._pendingWindowRender = false; // Flag to re-render after load completes

		// Processing state
		this.isGenerating = false;
		this.currentJobId = null;
		this.pollingInterval = null;
		this._isLoadingPeriodogram = false; // Flag to prevent re-entrant periodogram loads
		this._loadingPeriodogramSlice = null; // Track which slice is being loaded

		// Throttle/debounce for smooth playback (avoid heavy work every frame)
		this._lastPeriodogramTime = 0;
		this._periodogramThrottleMs = 80;
		this._pendingPeriodogramRender = false;
		this._prefetchDebounceTimer = null;
		this._prefetchDebounceMs = 120;

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
		// Initialize cache and loader for streaming
		this.sliceCache = new WaterfallSliceCache();
		this.sliceLoader = new WaterfallSliceLoader(
			this.captureUuid,
			this.sliceCache,
			(slices, startIndex, endIndex) => {
				// Guard against destroyed state (request completed after destroy)
				if (!this.sliceCache) return;
				// Callback when slices are loaded - trigger re-render
				this.onSlicesLoaded(slices, startIndex, endIndex);
			},
		);

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
					// Debounce prefetch so rapid scroll doesn't fire many requests
					if (this._prefetchDebounceTimer) {
						clearTimeout(this._prefetchDebounceTimer);
					}
					this._prefetchDebounceTimer = setTimeout(() => {
						this._prefetchDebounceTimer = null;
						this.prefetchAhead();
					}, this._prefetchDebounceMs);
				}

				if (sliceChanged) {
					// When slice is cached, always update periodogram (sync, smooth). When missing,
					// throttle loads so we don't trigger a network request every frame.
					const sliceInCache = this.sliceCache?.getSlice(currentSliceIndex);
					const now = performance.now();
					const throttleElapsed =
						now - this._lastPeriodogramTime >= this._periodogramThrottleMs;
					if (
						sliceInCache ||
						!this.controls?.isPlaying ||
						throttleElapsed
					) {
						if (!sliceInCache) this._lastPeriodogramTime = now;
						this.renderPeriodogram();
					}
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
	async render() {
		if (this.isStreamingMode) {
			if (this.totalSlices === 0) {
				return;
			}
		} else {
			// Legacy mode
			if (!this.parsedWaterfallData || this.parsedWaterfallData.length === 0) {
				return;
			}
		}

		// Hide error display if it exists
		this.hideErrorDisplay();

		// Show visualization components
		this.showVisualizationComponents();

		// Render waterfall with cached parsed data
		await this.renderWaterfall();

		// Render periodogram
		await this.renderPeriodogram();
	}

	/**
	 * Render the periodogram chart
	 */
	async renderPeriodogram() {
		if (!this.periodogramChart) return;

		if (this.isStreamingMode) {
			// Get slice from cache
			const slice = this.sliceCache.getSlice(this.currentSliceIndex);
			if (slice?._gap) {
				// Known data gap - no periodogram to show
				if (this.periodogramChart.showLoading) {
					this.periodogramChart.showLoading(false);
				}
				// Optionally render empty or "No data" state if periodogram supports it
				return;
			}
			if (slice?.data) {
				// Parse if needed
				const parsedSlice = {
					...slice,
					data: this.parseWaterfallData(slice.data),
				};
				this.periodogramChart.renderPeriodogram(parsedSlice);
				// Hide loading in case it was shown
				if (this.periodogramChart.showLoading) {
					this.periodogramChart.showLoading(false);
				}
			} else {
				// Slice not loaded yet - request it and show loading
				// Guard against re-entrant calls to prevent loading flicker
				// But allow if we're loading a different slice than requested
				if (
					this._isLoadingPeriodogram &&
					this._loadingPeriodogramSlice === this.currentSliceIndex
				) {
					return;
				}
				this._isLoadingPeriodogram = true;
				this._loadingPeriodogramSlice = this.currentSliceIndex;
				const targetSliceIndex = this.currentSliceIndex;

				if (this.periodogramChart.showLoading) {
					this.periodogramChart.showLoading(true);
				}
				try {
					await this.loadSliceRange(targetSliceIndex, targetSliceIndex + 1);
					// Only render if we're still on the same slice
					if (this.currentSliceIndex === targetSliceIndex) {
						const loadedSlice = this.sliceCache.getSlice(targetSliceIndex);
						if (loadedSlice?.data && !loadedSlice._gap) {
							const parsedSlice = {
								...loadedSlice,
								data: this.parseWaterfallData(loadedSlice.data),
							};
							this.periodogramChart.renderPeriodogram(parsedSlice);
						}
						if (this.periodogramChart.showLoading) {
							this.periodogramChart.showLoading(false);
						}
					}
					// If slice changed during load, trigger another render
					else if (this.currentSliceIndex !== targetSliceIndex) {
						this._isLoadingPeriodogram = false;
						this._loadingPeriodogramSlice = null;
						this.renderPeriodogram();
						return;
					}
				} catch (error) {
					// Slice may have been loaded by another request (e.g. waterfall batch)
					if (this.currentSliceIndex === targetSliceIndex) {
						const fromCache = this.sliceCache.getSlice(targetSliceIndex);
						if (fromCache?.data && !fromCache._gap) {
							const parsed = {
								...fromCache,
								data: this.parseWaterfallData(fromCache.data),
							};
							this.periodogramChart.renderPeriodogram(parsed);
						} else if (!fromCache?._gap) {
							console.warn(
								"Failed to load slice for periodogram (network/timeout):",
								error?.message || error,
							);
						}
						if (this.periodogramChart.showLoading) {
							this.periodogramChart.showLoading(false);
						}
					}
				} finally {
					this._isLoadingPeriodogram = false;
					this._loadingPeriodogramSlice = null;
				}
			}
		} else {
			// Legacy mode - use parsedWaterfallData
			if (this.parsedWaterfallData.length === 0) return;
			this.periodogramChart.renderPeriodogram(
				this.parsedWaterfallData[this.currentSliceIndex],
			);
		}
	}

	/**
	 * Render only the waterfall plot (for color map changes)
	 */
	async renderWaterfall() {
		if (this.isStreamingMode) {
			// Calculate visible slice range
			const startIndex = this.waterfallWindowStart;
			const endIndex = Math.min(
				startIndex + this.waterfallRenderer.WATERFALL_WINDOW_SIZE,
				this.totalSlices,
			);

			// Get slices from cache (may include nulls for missing slices)
			const slices = this.sliceCache.getSliceRange(startIndex, endIndex);

			// Check for missing slices and load them
			const missing = this.sliceCache.getMissingSlices(startIndex, endIndex);
			if (missing.length > 0) {
				// If already loading, schedule a re-render after load completes
				if (this._isLoadingWindow) {
					// Mark that we need a re-render after current load completes
					this._pendingWindowRender = true;
					// Don't render with incomplete data - wait for load to complete
					return;
				}

				this._isLoadingWindow = true;

				// Only pause playback and show full overlay when most of the window is missing
				// (e.g. big scroll/jump). Small refills (e.g. edge prefetch) load without overlay.
				const windowSize = endIndex - startIndex;
				const mostlyMissing = missing.length >= windowSize / 2;
				const wasPlaying = this.controls?.isPlaying ?? false;
				if (mostlyMissing) {
					if (wasPlaying) {
						this.controls.stopPlayback();
					}
					this.showLoading(true);
				}

				// Wait for missing slices to load before rendering
				try {
					await this.loadSliceRange(startIndex, endIndex);
				} catch (error) {
					console.error("Failed to load slices for waterfall:", error);
				} finally {
					this._isLoadingWindow = false;
					if (mostlyMissing) {
						this.showLoading(false);
						if (wasPlaying) {
							this.controls.startPlayback();
						}
					}
				}

				// Check if another render was requested while we were loading
				if (this._pendingWindowRender) {
					this._pendingWindowRender = false;
					// Schedule re-render for the new window position
					requestAnimationFrame(() => {
						this.renderWaterfall();
					});
					return;
				}

				// Verify slices were actually loaded (load may have failed)
				const stillMissing = this.sliceCache.getMissingSlices(
					startIndex,
					endIndex,
				);
				if (stillMissing.length > 0) {
					// Don't render with nulls - would show "Loading..." indefinitely
					return;
				}

				// Re-get slices after loading and render
				const loadedSlices = this.sliceCache.getSliceRange(
					startIndex,
					endIndex,
				);
				const parsedSlices = this._parseSlicesForRender(
					loadedSlices,
					endIndex - startIndex,
				);
				this.waterfallRenderer.renderWaterfall(
					parsedSlices,
					this.totalSlices,
					startIndex,
				);
				return;
			}

			// All slices are cached - render immediately
			const parsedSlices = this._parseSlicesForRender(
				slices,
				endIndex - startIndex,
			);
			this.waterfallRenderer.renderWaterfall(
				parsedSlices,
				this.totalSlices,
				startIndex,
			);
		} else {
			// Legacy mode
			if (!this.parsedWaterfallData || this.parsedWaterfallData.length === 0) {
				return;
			}
			this.waterfallRenderer.renderWaterfall(
				this.parsedWaterfallData,
				this.totalSlices,
			);
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
		const scaleMin = this.scaleMin ?? DEFAULT_SCALE_MIN;
		const scaleMax = this.scaleMax ?? DEFAULT_SCALE_MAX;

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
	 * Load waterfall data from the SDS API.
	 * Large captures use streaming (on-demand); smaller ones use preprocessed when available.
	 */
	async loadWaterfallData() {
		try {
			this.isLoading = true;
			this.showLoading(true);

			// For large captures, prefer streaming (no full preprocessed file load)
			const metadataUrl = get_waterfall_metadata_stream_endpoint(
				this.captureUuid,
			);
			const metadataResponse = await fetch(metadataUrl, {
				headers: { "X-CSRFToken": this.getCSRFToken() },
			});
			if (metadataResponse.ok) {
				try {
					const metadataData = await metadataResponse.json();
					const total = metadataData?.metadata?.total_slices;
					if (
						typeof total === "number" &&
						total >= LARGE_CAPTURE_THRESHOLD
					) {
						const streamingSuccess = await this.tryLoadStreamingMode();
						if (streamingSuccess) return;
					}
				} catch (_) {
					// Fall through to preprocessed/streaming logic below
				}
			}

			// When preprocessed waterfall exists (and not large), use it first
			const statusResponse = await fetch(
				`/api/latest/assets/captures/${this.captureUuid}/post_processing_status/`,
			);
			if (statusResponse.ok) {
				const statusData = await statusResponse.json();
				const hasPreprocessed = statusData.post_processed_data?.some(
					(d) =>
						d.processing_type === "waterfall" &&
						d.processing_status === "completed",
				);
				if (hasPreprocessed) {
					await this.loadFullPreprocessedDataLikeMaster();
					return;
				}
			}

			// No preprocessed data: use on-demand streaming
			const streamingSuccess = await this.tryLoadStreamingMode();
			if (streamingSuccess) {
				return;
			}

			// Streaming not available (e.g. not DRF), try preprocessed again for edge cases
			await this.loadPreprocessedData();
		} catch (error) {
			console.error("Failed to load waterfall data:", error);
			this.isLoading = false;
			this.showLoading(false);

			// Provide more helpful error messages
			let userMessage = error.message;
			const msg = error.message ?? "";
			if (
				error.name === "TypeError" &&
				(msg.includes("fetch") || msg.includes("NetworkError"))
			) {
				userMessage =
					"Unable to reach the server. Check your connection and that the server is running.";
			} else if (msg.includes("404")) {
				// Prefer backend message when it explains the 404 (e.g. no completed waterfall data)
				if (!msg.includes("No completed") && !msg.includes("not found")) {
					userMessage =
						"Capture not found or you do not have permission to access it.";
				}
			} else if (msg.includes("403")) {
				userMessage = "You do not have permission to access this capture.";
			} else if (msg.includes("500")) {
				userMessage = "Server error occurred. Please try again later.";
			}

			this.showError(userMessage);
		}
	}

	/**
	 * Load preprocessed waterfall exactly like master: full file download, parse all, calculatePowerBounds().
	 * Guarantees scale matches master (76 to -4 etc).
	 */
	async loadFullPreprocessedDataLikeMaster() {
		const dataResponse = await fetch(
			`/api/latest/assets/captures/${this.captureUuid}/download_post_processed_data/?processing_type=waterfall`,
		);
		if (!dataResponse.ok) {
			const body = await dataResponse.json().catch(() => ({}));
			const apiError = body?.error ?? body?.detail;
			throw new Error(
				typeof apiError === "string" && apiError
					? apiError
					: `Failed to download waterfall data: ${dataResponse.status}`,
			);
		}
		const waterfallJson = await dataResponse.json();
		this.waterfallData = waterfallJson;
		this.totalSlices = waterfallJson.length;
		this.parsedWaterfallData = this.waterfallData.map((slice) => ({
			...slice,
			data: this.parseWaterfallData(slice.data),
		}));
		this.calculatePowerBounds();
		this.isStreamingMode = false;
		this.isLoading = false;
		this.showLoading(false);
		this.controls.setTotalSlices(this.totalSlices);
		this.waterfallRenderer.setScaleBounds(this.scaleMin, this.scaleMax);
		this.periodogramChart.updateYAxisBounds(this.scaleMin, this.scaleMax);
		this.updateColorLegend();
		this.render();
	}

	/**
	 * Try to load waterfall using on-demand streaming (no preprocessing required)
	 * Returns true if successful, false if should fall back to preprocessed
	 */
	async tryLoadStreamingMode() {
		try {
			// Get metadata from streaming endpoint. Do not request power_bounds here:
			// that triggers DRF reconstruction and MinIO downloads and can timeout
			// (NetworkError). Scale will come from setScaleFromPostProcessedMetadata
			// or calculatePowerBoundsFromSamples after we load slices.
			const metadataUrl = get_waterfall_metadata_stream_endpoint(
				this.captureUuid,
				false, // include_power_bounds = false for fast probe
			);
			const metadataResponse = await fetch(metadataUrl, {
				method: "GET",
				credentials: "same-origin",
				headers: {
					"Content-Type": "application/json",
					"X-CSRFToken": this.getCSRFToken(),
				},
			});

			if (!metadataResponse.ok) {
				// Streaming not available for this capture (e.g., not DRF)
				return false;
			}

			let metadataData;
			try {
				metadataData = await metadataResponse.json();
			} catch (_) {
				return false;
			}
			const metadata = metadataData?.metadata;

			if (!metadata || !metadata.total_slices) {
				console.warn("Streaming metadata missing total_slices");
				return false;
			}

			// Streaming is available! Configure for streaming mode
			this.totalSlices = metadata.total_slices;
			this.isStreamingMode = true;

			// Enable streaming mode in the loader
			if (this.sliceLoader) {
				this.sliceLoader.setStreamingMode(true);
			}

			// Load initial visible window first so we can show it ASAP
			const initialStart = 0;
			const initialEnd = Math.min(WATERFALL_WINDOW_SIZE, this.totalSlices);

			await this.loadSliceRange(initialStart, initialEnd);

			// Scale from the loaded window so the range isn't way too big (avoids full-capture 76 to -4 when first screen is e.g. 71-31)
			this.calculatePowerBoundsFromLoadedSlices(initialStart, initialEnd);
			const needFallbackScale =
				this.scaleMin === null ||
				this.scaleMax === null ||
				(this.scaleMin === DEFAULT_SCALE_MIN &&
					this.scaleMax === DEFAULT_SCALE_MAX);
			if (needFallbackScale) {
				await this.setScaleFromPostProcessedMetadata();
			}
			const stillNeedFallback =
				this.scaleMin === null ||
				this.scaleMax === null ||
				(this.scaleMin === DEFAULT_SCALE_MIN &&
					this.scaleMax === DEFAULT_SCALE_MAX);
			if (stillNeedFallback) {
				const boundsUrl = get_waterfall_metadata_stream_endpoint(
					this.captureUuid,
					true, // include_power_bounds
				);
				try {
					const boundsResponse = await fetch(boundsUrl, {
						method: "GET",
						credentials: "same-origin",
						headers: {
							"Content-Type": "application/json",
							"X-CSRFToken": this.getCSRFToken(),
						},
					});
					if (boundsResponse.ok) {
						const boundsData = await boundsResponse.json();
						const streamBounds = boundsData?.metadata?.power_bounds;
						if (
							typeof streamBounds?.min === "number" &&
							typeof streamBounds?.max === "number" &&
							streamBounds.min < streamBounds.max
						) {
							this.scaleMin = streamBounds.min;
							this.scaleMax = streamBounds.max;
						}
					}
				} catch (_) {
					// Fall through to calculatePowerBoundsFromSamples
				}
			}
			if (this.scaleMin === null || this.scaleMax === null) {
				await this.calculatePowerBoundsFromSamples();
			}

			this.isLoading = false;
			this.showLoading(false);

			this.controls.setTotalSlices(this.totalSlices);
			this.waterfallRenderer.setScaleBounds(this.scaleMin, this.scaleMax);
			this.periodogramChart.updateYAxisBounds(this.scaleMin, this.scaleMax);
			this.updateColorLegend();

			this.render();

			// Prefetch in background so scrolling is smooth (don't block initial display)
			const prefetchEnd = Math.min(
				initialEnd + PREFETCH_DISTANCE,
				this.totalSlices,
			);
			if (prefetchEnd > initialEnd) {
				this.loadSliceRange(initialEnd, prefetchEnd)
					.then(() => this.prefetchAhead())
					.catch(() => {});
			} else {
				this.prefetchAhead();
			}

			return true;
		} catch (error) {
			const reason =
				error?.message ||
				(error?.name && error?.name !== "Error" ? error.name : String(error));
			console.warn(
				"Streaming mode failed, will try preprocessed:",
				reason,
				error,
			);
			return false;
		}
	}

	/**
	 * Load waterfall data from preprocessed files (legacy flow)
	 */
	async loadPreprocessedData() {
		// Get the post-processing status to check if waterfall data is available
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

		// Scale from stored metadata (same as master: min/max over all slices + 5% margin)
		await this.setScaleFromPostProcessedMetadata();

		// Get total slices from waterfall_slices endpoint with a small range
		try {
			const testResponse = await fetch(
				`/api/latest/assets/captures/${this.captureUuid}/waterfall_slices/?start_index=0&end_index=1&processing_type=waterfall`,
			);
			if (testResponse.ok) {
				const testData = await testResponse.json();
				this.totalSlices = testData.total_slices || 0;
				// Use power_bounds from slices response if we didn't get them from metadata
				if (
					(this.scaleMin === null || this.scaleMax === null) &&
					testData.metadata?.power_bounds
				) {
					const bounds = testData.metadata.power_bounds;
					if (
						typeof bounds.min === "number" &&
						typeof bounds.max === "number" &&
						bounds.min < bounds.max
					) {
						this.scaleMin = bounds.min;
						this.scaleMax = bounds.max;
					}
				}
			} else {
				throw new Error(
					`Failed to get waterfall metadata: ${testResponse.status}`,
				);
			}
		} catch (e) {
			console.warn("Could not determine total slices:", e);
			throw e;
		}

		if (this.totalSlices === 0) {
			throw new Error("No waterfall slices found");
		}

		// Enable streaming mode (using preprocessed slices)
		this.isStreamingMode = true;

		// Ensure loader uses preprocessed endpoint
		if (this.sliceLoader) {
			this.sliceLoader.setStreamingMode(false);
		}

		// Load initial visible window
		const initialStart = 0;
		const initialEnd = Math.min(WATERFALL_WINDOW_SIZE, this.totalSlices);

		await this.loadSliceRange(initialStart, initialEnd);

		// Calculate power bounds from initial slices if not in metadata
		if (this.scaleMin === null || this.scaleMax === null) {
			await this.calculatePowerBoundsFromSamples();
		}

		// Prefetch additional data
		const prefetchEnd = Math.min(
			initialEnd + PREFETCH_DISTANCE,
			this.totalSlices,
		);
		if (prefetchEnd > initialEnd) {
			await this.loadSliceRange(initialEnd, prefetchEnd);
		}

		this.isLoading = false;
		this.showLoading(false);

		this.controls.setTotalSlices(this.totalSlices);
		this.waterfallRenderer.setScaleBounds(this.scaleMin, this.scaleMax);
		this.periodogramChart.updateYAxisBounds(this.scaleMin, this.scaleMax);
		this.updateColorLegend();

		this.render();
		this.prefetchAhead();
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
			// In streaming mode, reload data using streaming endpoint
			if (this.isStreamingMode) {
				await this.loadWaterfallData();
				return;
			}

			// Legacy mode: load all data at once
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
	 * Load a range of slices using the streaming endpoint
	 * @param {number} startIndex - Starting slice index (inclusive)
	 * @param {number} endIndex - Ending slice index (exclusive)
	 * @returns {Promise<Array>} Promise resolving to loaded slices
	 */
	async loadSliceRange(startIndex, endIndex) {
		if (!this.sliceLoader) {
			throw new Error("Slice loader not initialized");
		}

		try {
			const slices = await this.sliceLoader.loadSliceRange(
				startIndex,
				endIndex,
				"waterfall",
			);
			return slices;
		} catch (error) {
			console.error(
				`Failed to load slice range ${startIndex}-${endIndex}:`,
				error,
			);
			throw error;
		}
	}

	/**
	 * Callback when slices are loaded
	 * @param {Array} slices - The loaded slices
	 * @param {number} startIndex - Starting index
	 * @param {number} endIndex - Ending index
	 */
	onSlicesLoaded(slices, startIndex, endIndex) {
		// Skip callback renders during initial load - the initial render() will handle it
		if (this.isLoading) {
			return;
		}

		const currentStart = this.waterfallWindowStart;
		const currentEnd = Math.min(
			currentStart + this.waterfallRenderer.WATERFALL_WINDOW_SIZE,
			this.totalSlices,
		);

		// Only re-render when the visible window is fully filled (no missing slices).
		// This avoids blinking when multiple batches complete in quick succession.
		if (startIndex < currentEnd && endIndex > currentStart) {
			const stillMissing = this.sliceCache.getMissingSlices(
				currentStart,
				currentEnd,
			);
			if (stillMissing.length === 0 && !this._pendingRender) {
				this._pendingRender = true;
				requestAnimationFrame(() => {
					this._pendingRender = false;
					this.renderWaterfall();
				});
			}
		}

		// If loaded slice is the current slice, update periodogram (throttle rapid callbacks)
		if (
			this.currentSliceIndex >= startIndex &&
			this.currentSliceIndex < endIndex
		) {
			const now = performance.now();
			if (
				now - this._lastPeriodogramTime >= this._periodogramThrottleMs
			) {
				this._lastPeriodogramTime = now;
				this.renderPeriodogram();
			} else if (!this._pendingPeriodogramRender) {
				this._pendingPeriodogramRender = true;
				requestAnimationFrame(() => {
					this._pendingPeriodogramRender = false;
					this._lastPeriodogramTime = performance.now();
					this.renderPeriodogram();
				});
			}
		}
	}

	/**
	 * Prefetch slices around the current window using a smart trigger-based strategy.
	 *
	 * Strategy:
	 * - PREFETCH_TRIGGER: Only start prefetching when within this distance of unfetched data
	 * - PREFETCH_DISTANCE: Once triggered, load this many slices ahead/behind
	 *
	 * This reduces unnecessary API calls while ensuring smooth scrolling.
	 */
	prefetchAhead() {
		if (!this.sliceLoader || !this.isStreamingMode) return;

		const windowStart = this.waterfallWindowStart;
		const windowEnd = Math.min(
			windowStart + WATERFALL_WINDOW_SIZE,
			this.totalSlices,
		);

		// Define trigger zone around the window
		const triggerStart = Math.max(windowStart - PREFETCH_TRIGGER, 0);
		const triggerEnd = Math.min(windowEnd + PREFETCH_TRIGGER, this.totalSlices);

		// Check if there's any missing data within the trigger zone
		const missingInTriggerZone = this.sliceCache.getMissingSlices(
			triggerStart,
			triggerEnd,
		);

		// Only prefetch if we're approaching unfetched data
		if (missingInTriggerZone.length === 0) {
			// No missing data within trigger zone, no need to prefetch
			return;
		}

		// Define the full prefetch range (larger than trigger zone)
		const prefetchStart = Math.max(windowStart - PREFETCH_DISTANCE, 0);
		const prefetchEnd = Math.min(
			windowEnd + PREFETCH_DISTANCE,
			this.totalSlices,
		);

		// Get all missing slices in the prefetch range
		const missingSlices = this.sliceCache.getMissingSlices(
			prefetchStart,
			prefetchEnd,
		);

		if (missingSlices.length > 0) {
			// Load missing slices in the background
			this.sliceLoader
				.loadSliceRange(prefetchStart, prefetchEnd, "waterfall")
				.catch((error) => {
					console.warn("Prefetch failed:", error);
				});
		}

		// Evict distant slices to keep cache size manageable
		const centerIndex = Math.floor((windowStart + windowEnd) / 2);
		const keepRange = WATERFALL_WINDOW_SIZE + PREFETCH_DISTANCE;
		this.sliceCache.evictDistantSlices(centerIndex, keepRange);
	}

	/**
	 * Set scale from stored post-processed metadata when available (matches master range e.g. 76 to -4).
	 * Fetches get_post_processed_metadata and uses power_bounds.min/max if present.
	 */
	async setScaleFromPostProcessedMetadata() {
		try {
			const url = `/api/latest/assets/captures/${this.captureUuid}/get_post_processed_metadata/?processing_type=waterfall`;
			const response = await fetch(url, {
				headers: { "X-CSRFToken": this.getCSRFToken() },
			});
			if (!response.ok) return;
			const data = await response.json();
			const bounds = data?.metadata?.power_bounds;
			if (
				typeof bounds?.min === "number" &&
				typeof bounds?.max === "number" &&
				bounds.min < bounds.max
			) {
				this.scaleMin = bounds.min;
				this.scaleMax = bounds.max;
			}
		} catch (_) {
			// Fall back to computed bounds
		}
	}

	/**
	 * Set scale from min/max with 5% margin, or defaults if no valid data.
	 * @private
	 */
	_setScaleFromBounds(globalMin, globalMax) {
		if (
			globalMin !== Number.POSITIVE_INFINITY &&
			globalMax !== Number.NEGATIVE_INFINITY
		) {
			const margin = (globalMax - globalMin) * 0.05;
			this.scaleMin = globalMin - margin;
			this.scaleMax = globalMax + margin;
		} else {
			this.scaleMin = DEFAULT_SCALE_MIN;
			this.scaleMax = DEFAULT_SCALE_MAX;
		}
	}

	/**
	 * Calculate power bounds from slices already in cache (no loading).
	 * Use when the initial window is loaded so scale matches the first screen (master behavior).
	 * @param {number} startIndex - Start of range (inclusive)
	 * @param {number} endIndex - End of range (exclusive)
	 */
	calculatePowerBoundsFromLoadedSlices(startIndex, endIndex) {
		let globalMin = Number.POSITIVE_INFINITY;
		let globalMax = Number.NEGATIVE_INFINITY;

		for (let i = startIndex; i < endIndex; i++) {
			const slice = this.sliceCache.getSlice(i);
			if (slice?.data) {
				const parsedData = this.parseWaterfallData(slice.data);
				if (parsedData && parsedData.length > 0) {
					const sliceMin = Math.min(...parsedData);
					const sliceMax = Math.max(...parsedData);
					globalMin = Math.min(globalMin, sliceMin);
					globalMax = Math.max(globalMax, sliceMax);
				}
			}
		}

		this._setScaleFromBounds(globalMin, globalMax);
	}

	/**
	 * Calculate power bounds from sample slices (first, middle, last).
	 * Loads those slices if not cached. Used when we don't have a full window in cache.
	 */
	async calculatePowerBoundsFromSamples() {
		if (this.totalSlices === 0) {
			this.scaleMin = DEFAULT_SCALE_MIN;
			this.scaleMax = DEFAULT_SCALE_MAX;
			return;
		}

		// Sample slices: first, middle, last
		const sampleIndices = [
			0,
			Math.floor(this.totalSlices / 2),
			this.totalSlices - 1,
		].filter((idx) => idx >= 0 && idx < this.totalSlices);

		// Load sample slices if not cached
		for (const idx of sampleIndices) {
			if (!this.sliceCache.hasSlice(idx)) {
				try {
					await this.loadSliceRange(idx, idx + 1);
				} catch (error) {
					console.warn(`Failed to load sample slice ${idx}:`, error);
				}
			}
		}

		let globalMin = Number.POSITIVE_INFINITY;
		let globalMax = Number.NEGATIVE_INFINITY;
		for (const idx of sampleIndices) {
			const slice = this.sliceCache.getSlice(idx);
			if (slice?.data) {
				const parsedData = this.parseWaterfallData(slice.data);
				if (parsedData && parsedData.length > 0) {
					globalMin = Math.min(globalMin, Math.min(...parsedData));
					globalMax = Math.max(globalMax, Math.max(...parsedData));
				}
			}
		}
		this._setScaleFromBounds(globalMin, globalMax);
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
	 * Parse an array of slices for rendering
	 * @param {Array} slices - Array of slice objects (may contain nulls)
	 * @param {number} windowSize - Expected window size
	 * @returns {Array} Array of parsed slices (with nulls for missing/failed)
	 */
	_parseSlicesForRender(slices, windowSize) {
		const parsedSlices = [];
		for (let i = 0; i < windowSize; i++) {
			const slice = slices[i];
			if (slice?.data) {
				const parsedData = this.parseWaterfallData(slice.data);
				if (parsedData && parsedData.length > 0) {
					parsedSlices.push({
						...slice,
						data: parsedData,
					});
				} else {
					parsedSlices.push(null);
				}
			} else {
				parsedSlices.push(null);
			}
		}
		return parsedSlices;
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
		// Disable scroll buttons during loading
		if (this.controls) {
			this.controls.setLoading(show);
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

		if (this._prefetchDebounceTimer) {
			clearTimeout(this._prefetchDebounceTimer);
			this._prefetchDebounceTimer = null;
		}
		this._pendingPeriodogramRender = false;

		// Cleanup loader
		if (this.sliceLoader) {
			this.sliceLoader.destroy();
		}

		// Cleanup cache
		if (this.sliceCache) {
			this.sliceCache.clear();
		}

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
		this.sliceCache = null;
		this.sliceLoader = null;
	}
}

// Make the class globally available
window.WaterfallVisualization = WaterfallVisualization;
