/**
 * Waterfall Visualization Class
 * Handles the waterfall visualization using vanilla JavaScript, D3, and CanvasJS
 */
class WaterfallVisualization {
	constructor(captureUuid) {
		this.captureUuid = captureUuid;
		this.waterfallData = [];
		this.currentSliceIndex = 0;
		this.hoveredSliceIndex = null; // Track which slice is being hovered
		this.waterfallWindowStart = 0; // Track the start of the visible waterfall window
		this.isPlaying = false;
		this.playbackInterval = null;
		this.playbackSpeed = 1; // fps
		this.fftSize = 1024;
		this.colorMap = "viridis";
		this.totalSlices = 0;
		this.canvas = null;
		this.ctx = null;
		this.overlayCanvas = null;
		this.overlayCtx = null;
		this.periodogramChart = null;
		this.scaleMin = null;
		this.scaleMax = null;

		// Constants
		this.WATERFALL_WINDOW_SIZE = 100; // Number of slices visible in the waterfall plot at once
		this.LEFT_INDEX_WIDTH = 60; // Width of the left index legend area
		this.RIGHT_LEGEND_WIDTH = 80; // Width of the right color legend area
		this.TOP_MARGIN = 5; // Top margin for the waterfall plot
		this.BOTTOM_MARGIN = 5; // Bottom margin for the waterfall plot

		// Bind methods to preserve context
		this.handlePlayPause = this.handlePlayPause.bind(this);
		this.handleSave = this.handleSave.bind(this);
		this.handleSliceChange = this.handleSliceChange.bind(this);
		this.handleSliceIndexInputChange =
			this.handleSliceIndexInputChange.bind(this);
		this.handleSliceIndexInputKeyDown =
			this.handleSliceIndexInputKeyDown.bind(this);
		this.handleDecrementSlice = this.handleDecrementSlice.bind(this);
		this.handleIncrementSlice = this.handleIncrementSlice.bind(this);
		this.handleScrollUp = this.handleScrollUp.bind(this);
		this.handleScrollDown = this.handleScrollDown.bind(this);
		this.handlePlaybackSpeedChange = this.handlePlaybackSpeedChange.bind(this);
		this.handleFFTSizeChange = this.handleFFTSizeChange.bind(this);
		this.handleColorMapChange = this.handleColorMapChange.bind(this);
		this.handleKeyDown = this.handleKeyDown.bind(this);
	}

	/**
	 * Initialize the waterfall visualization
	 */
	async initialize() {
		try {
			this.setupEventListeners();
			this.initializeCanvas();
			this.initializePeriodogramChart();

			// Load initial data
			await this.loadWaterfallData();

			// Render initial visualization
			this.render();

			// Set initial color legend positioning
			this.updateColorLegendPosition();
		} catch (error) {
			console.error("Failed to initialize waterfall visualization:", error);
			this.showError("Failed to initialize visualization");
		}
	}

	/**
	 * Set up event listeners for controls
	 */
	setupEventListeners() {
		// Play/Pause button
		const playPauseBtn = document.getElementById("playPauseBtn");
		if (playPauseBtn) {
			playPauseBtn.addEventListener("click", this.handlePlayPause);
		}

		// Save button
		const saveBtn = document.getElementById("saveBtn");
		if (saveBtn) {
			saveBtn.addEventListener("click", this.handleSave);
		}

		// Slice slider
		const sliceSlider = document.getElementById("currentSlice");
		if (sliceSlider) {
			sliceSlider.addEventListener("input", this.handleSliceChange);
		}

		// Increment/Decrement slice buttons
		const decrementBtn = document.getElementById("decrementSlice");
		if (decrementBtn) {
			decrementBtn.addEventListener("click", this.handleDecrementSlice);
		}

		const incrementBtn = document.getElementById("incrementSlice");
		if (incrementBtn) {
			incrementBtn.addEventListener("click", this.handleIncrementSlice);
		}

		// Slice index input field
		const sliceIndexInput = document.getElementById("sliceIndexInput");
		if (sliceIndexInput) {
			sliceIndexInput.addEventListener(
				"change",
				this.handleSliceIndexInputChange,
			);
			sliceIndexInput.addEventListener(
				"keydown",
				this.handleSliceIndexInputKeyDown,
			);
		}

		// Playback speed
		const speedSelect = document.getElementById("playbackSpeed");
		if (speedSelect) {
			speedSelect.addEventListener("change", this.handlePlaybackSpeedChange);
		}

		// FFT size
		const fftSelect = document.getElementById("fftSize");
		if (fftSelect) {
			fftSelect.addEventListener("change", this.handleFFTSizeChange);
		}

		// Color map
		const colorSelect = document.getElementById("colorMap");
		if (colorSelect) {
			colorSelect.addEventListener("change", this.handleColorMapChange);
		}

		// Canvas click for slice selection
		const canvas = document.getElementById("waterfallCanvas");
		if (canvas) {
			canvas.addEventListener("click", this.handleCanvasClick.bind(this));
			canvas.addEventListener(
				"mousemove",
				this.handleCanvasMouseMove.bind(this),
			);
			canvas.addEventListener(
				"mouseleave",
				this.handleCanvasMouseLeave.bind(this),
			);
		}

		// Scroll indicator buttons
		const scrollUpBtn = document.getElementById("scrollUpBtn");
		if (scrollUpBtn) {
			scrollUpBtn.addEventListener("click", this.handleScrollUp);
		}

		const scrollDownBtn = document.getElementById("scrollDownBtn");
		if (scrollDownBtn) {
			scrollDownBtn.addEventListener("click", this.handleScrollDown);
		}

		// Keyboard navigation
		document.addEventListener("keydown", this.handleKeyDown);
	}

	/**
	 * Initialize the canvas for waterfall plotting
	 */
	initializeCanvas() {
		this.canvas = document.getElementById("waterfallCanvas");
		if (!this.canvas) {
			throw new Error("Waterfall canvas not found");
		}

		this.ctx = this.canvas.getContext("2d");

		// Get the overlay canvas for highlight boxes
		this.overlayCanvas = document.getElementById("waterfallOverlayCanvas");
		this.overlayCtx = this.overlayCanvas
			? this.overlayCanvas.getContext("2d")
			: null;

		// Set canvas size based on container
		this.resizeCanvas();

		// Add resize listener
		window.addEventListener("resize", () => this.resizeCanvas());
	}

	/**
	 * Resize canvas to fit container
	 */
	resizeCanvas() {
		const container = this.canvas.parentElement;
		const rect = container.getBoundingClientRect();

		this.canvas.width = rect.width;
		this.canvas.height = rect.height;

		// Resize overlay canvas to match
		if (this.overlayCanvas) {
			this.overlayCanvas.width = rect.width;
			this.overlayCanvas.height = rect.height;
			this.overlayCanvas.style.width = `${rect.width}px`;
			this.overlayCanvas.style.height = `${rect.height}px`;
			// Clear overlay when resizing
			this.clearOverlay();
		}

		// Re-render if we have data
		if (this.waterfallData.length > 0) {
			this.render();
		} else {
			// Still update color legend positioning even without data
			this.updateColorLegendPosition();
		}
	}

	/**
	 * Initialize the periodogram chart using CanvasJS
	 */
	initializePeriodogramChart() {
		const container = document.getElementById("periodogramChart");
		if (!container) {
			throw new Error("Periodogram chart container not found");
		}

		this.periodogramChart = new CanvasJS.Chart(container, {
			animationEnabled: false,
			theme: "light2",
			title: {
				text: "Frequency Domain",
			},
			axisX: {
				title: "Frequency (Hz)",
				gridThickness: 1,
				gridColor: "#e9ecef",
			},
			axisY: {
				title: "Power (dB)",
				gridThickness: 1,
				gridColor: "#e9ecef",
			},
			data: [
				{
					type: "line",
					dataPoints: [],
					color: "#0d6efd",
					lineThickness: 2,
				},
			],
		});
	}

	/**
	 * Load waterfall data from the SDS API
	 */
	async loadWaterfallData() {
		try {
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
				throw new Error(
					"Waterfall data not available. Please ensure post-processing is complete.",
				);
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

			// Calculate color scale bounds from all data
			this.calculateColorScaleBounds();

			// Clear hover state when loading new data
			this.hoveredSliceIndex = null;
			// Clear overlay when loading new data
			this.clearOverlay();

			// Update UI elements
			this.updateSliceSlider();
			this.updateSliceCounter();
			this.updateColorLegend();

			this.showLoading(false);
		} catch (error) {
			console.error("Failed to load waterfall data:", error);

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
			this.showLoading(false);
		}
	}

	/**
	 * Update the slice slider with total slices
	 */
	updateSliceSlider() {
		const slider = document.getElementById("currentSlice");
		const counter = document.getElementById("sliceCounter");
		const minLabel = document.getElementById("sliceMinLabel");
		const maxLabel = document.getElementById("sliceMaxLabel");

		if (slider) {
			slider.max = Math.max(0, this.totalSlices - 1);
			slider.value = 0;
		}

		if (counter) {
			counter.textContent = `0 / ${this.totalSlices}`;
		}

		// Update min/max labels (convert from 0-based to 1-based for display)
		if (minLabel) {
			minLabel.textContent = "1";
		}

		if (maxLabel) {
			maxLabel.textContent = this.totalSlices.toString();
		}

		// Update button states
		this.updateSliceButtons();
		this.updateSliceIndexInput();
		this.ensureSliceVisible();
		this.updateScrollIndicators();
	}

	/**
	 * Update the slice counter display
	 */
	updateSliceCounter() {
		const counter = document.getElementById("sliceCounter");
		if (counter) {
			counter.textContent = `${this.currentSliceIndex} / ${this.totalSlices}`;
		}
	}

	/**
	 * Ensure the selected slice is visible in the current window
	 */
	ensureSliceVisible() {
		if (this.currentSliceIndex < this.waterfallWindowStart) {
			// Selected slice is below the current window, shift window down
			this.waterfallWindowStart = this.currentSliceIndex;
		} else if (
			this.currentSliceIndex >=
			this.waterfallWindowStart + this.WATERFALL_WINDOW_SIZE
		) {
			// Selected slice is above the current window, shift window up
			this.waterfallWindowStart =
				this.currentSliceIndex - this.WATERFALL_WINDOW_SIZE + 1;
		}
		// Ensure window bounds are respected
		this.waterfallWindowStart = Math.max(
			0,
			Math.min(
				this.waterfallWindowStart,
				this.totalSlices - this.WATERFALL_WINDOW_SIZE,
			),
		);
	}

	/**
	 * Update all slice-related UI elements
	 */
	updateSliceUI() {
		this.updateSliceCounter();
		this.updateSliceButtons();
		this.updateSliceIndexInput();
		this.ensureSliceVisible();
		this.updateScrollIndicators();

		// Update slider value
		const slider = document.getElementById("currentSlice");
		if (slider) {
			slider.value = this.currentSliceIndex;
		}
	}

	/**
	 * Update the state of increment/decrement buttons
	 */
	updateSliceButtons() {
		const decrementBtn = document.getElementById("decrementSlice");
		const incrementBtn = document.getElementById("incrementSlice");

		if (decrementBtn) {
			decrementBtn.disabled = this.currentSliceIndex <= 0;
		}

		if (incrementBtn) {
			incrementBtn.disabled = this.currentSliceIndex >= this.totalSlices - 1;
		}
	}

	/**
	 * Update the slice index input field
	 */
	updateSliceIndexInput() {
		const sliceIndexInput = document.getElementById("sliceIndexInput");
		if (sliceIndexInput) {
			// Update min/max values
			sliceIndexInput.min = 1;
			sliceIndexInput.max = this.totalSlices;
			// Update current value (convert from 0-based to 1-based for display)
			sliceIndexInput.value = this.currentSliceIndex + 1;
		}
	}

	/**
	 * Update scroll indicator buttons
	 */
	updateScrollIndicators() {
		const scrollUpBtn = document.getElementById("scrollUpBtn");
		const scrollDownBtn = document.getElementById("scrollDownBtn");
		const scrollIndicatorAbove = document.getElementById(
			"scrollIndicatorAbove",
		);
		const scrollIndicatorBelow = document.getElementById(
			"scrollIndicatorBelow",
		);

		const canScrollUp =
			this.waterfallWindowStart < this.totalSlices - this.WATERFALL_WINDOW_SIZE;
		const canScrollDown = this.waterfallWindowStart > 0;

		// Show/hide indicators based on whether scrolling is possible
		if (scrollIndicatorAbove) {
			scrollIndicatorAbove.classList.toggle("visible", canScrollUp);
		}

		if (scrollIndicatorBelow) {
			scrollIndicatorBelow.classList.toggle("visible", canScrollDown);
		}

		// Update button states
		if (scrollUpBtn) {
			scrollUpBtn.disabled = !canScrollUp;
			scrollUpBtn.classList.toggle("disabled", !canScrollUp);
		}

		if (scrollDownBtn) {
			scrollDownBtn.disabled = !canScrollDown;
			scrollDownBtn.classList.toggle("disabled", !canScrollDown);
		}
	}

	/**
	 * Calculate color scale bounds from all waterfall data
	 */
	calculateColorScaleBounds() {
		if (this.waterfallData.length === 0) {
			// Fallback to default bounds if no data
			this.scaleMin = -130;
			this.scaleMax = 0;
			return;
		}

		let globalMin = Number.POSITIVE_INFINITY;
		let globalMax = Number.NEGATIVE_INFINITY;

		// Iterate through all slices to find global min/max
		for (const slice of this.waterfallData) {
			if (slice.data) {
				const sliceData = this.parseWaterfallData(slice.data);
				if (sliceData && sliceData.length > 0) {
					const sliceMin = Math.min(...sliceData);
					const sliceMax = Math.max(...sliceData);

					globalMin = Math.min(globalMin, sliceMin);
					globalMax = Math.max(globalMax, sliceMax);
				}
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
	 * Render the waterfall visualization
	 */
	render() {
		if (this.waterfallData.length === 0) {
			return;
		}

		this.renderWaterfall();
		this.renderPeriodogram();
	}

	/**
	 * Render the waterfall plot on canvas
	 */
	renderWaterfall() {
		if (!this.ctx || !this.canvas) return;

		const canvas = this.canvas;
		const ctx = this.ctx;

		// Clear canvas
		ctx.clearRect(0, 0, canvas.width, canvas.height);

		// Calculate dimensions with margins
		const plotHeight = canvas.height - this.TOP_MARGIN - this.BOTTOM_MARGIN;
		const maxVisibleSlices = Math.min(
			this.totalSlices,
			this.WATERFALL_WINDOW_SIZE,
		);
		const sliceHeight = plotHeight / maxVisibleSlices;

		// Calculate which slices to display
		// We want to show slices from bottom (oldest) to top (newest)
		// The window position is controlled independently from the selected slice
		const startSliceIndex = this.waterfallWindowStart;
		const endSliceIndex = Math.min(
			this.waterfallWindowStart + this.WATERFALL_WINDOW_SIZE,
			this.totalSlices,
		);

		// Draw waterfall slices from bottom to top
		for (let i = 0; i < this.WATERFALL_WINDOW_SIZE; i++) {
			const sliceIndex = startSliceIndex + i;
			if (sliceIndex >= this.totalSlices) break;

			const slice = this.waterfallData[sliceIndex];
			if (slice) {
				const sliceData = this.parseWaterfallData(slice.data);
				if (sliceData) {
					// Calculate Y position: bottom slice is at bottom margin, top slice is at top margin
					const y =
						this.BOTTOM_MARGIN + (maxVisibleSlices - 1 - i) * sliceHeight;

					this.drawWaterfallSlice(sliceData, y, sliceHeight, canvas.width);
				}
			}
		}

		// Draw all highlights on the overlay canvas
		this.redrawHighlights(canvas, sliceHeight, startSliceIndex, endSliceIndex);

		// Update color legend
		this.updateColorLegend();

		// Update slice index legend
		this.updateSliceIndexLegend();

		// Update color legend positioning
		this.updateColorLegendPosition();
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
	 * Draw a single waterfall slice
	 */
	drawWaterfallSlice(data, y, height, width) {
		if (!this.ctx) return;

		const ctx = this.ctx;
		const fftPoints = data.length;
		// Account for left index area and right legend area
		const plotWidth = width - this.LEFT_INDEX_WIDTH - this.RIGHT_LEGEND_WIDTH;
		const pointWidth = plotWidth / fftPoints;

		// Use calculated bounds for optimal visualization
		const scaleMin = this.scaleMin || -130;
		const scaleMax = this.scaleMax || 0;
		const powerRange = scaleMax - scaleMin;

		for (let i = 0; i < fftPoints; i++) {
			const power = data[i];

			// Clamp power to the scale range and normalize
			const clampedPower = Math.max(scaleMin, Math.min(scaleMax, power));
			const normalizedPower = (clampedPower - scaleMin) / powerRange;

			const color = this.getColorForPower(normalizedPower);

			ctx.fillStyle = color;
			ctx.fillRect(
				this.LEFT_INDEX_WIDTH + i * pointWidth,
				y,
				pointWidth,
				height,
			);
		}
	}

	/**
	 * Get color for power value using selected color map
	 */
	getColorForPower(normalizedPower) {
		// Enhanced color mapping similar to SVI implementation
		const intensity = Math.floor(normalizedPower * 255);

		switch (this.colorMap) {
			case "viridis": {
				// Blue to green to yellow to red
				if (normalizedPower < 0.25) {
					return `rgb(0, ${Math.floor(intensity * 4)}, ${255 - intensity})`;
				}
				if (normalizedPower < 0.5) {
					const t = (normalizedPower - 0.25) * 4;
					return `rgb(0, 255, ${Math.floor(255 * (1 - t))})`;
				}
				if (normalizedPower < 0.75) {
					const t = (normalizedPower - 0.5) * 4;
					return `rgb(${Math.floor(255 * t)}, 255, 0)`;
				}
				const t = (normalizedPower - 0.75) * 4;
				return `rgb(255, ${Math.floor(255 * (1 - t))}, 0)`;
			}
			case "plasma": {
				// Purple to blue to green to yellow to red
				if (normalizedPower < 0.25) {
					return `rgb(${Math.floor(intensity * 4)}, 0, ${255 - intensity})`;
				}
				if (normalizedPower < 0.5) {
					const t = (normalizedPower - 0.25) * 4;
					return `rgb(255, 0, ${Math.floor(255 * (1 - t))})`;
				}
				if (normalizedPower < 0.75) {
					const t = (normalizedPower - 0.5) * 4;
					return `rgb(255, ${Math.floor(255 * t)}, 0)`;
				}
				const t = (normalizedPower - 0.75) * 4;
				return `rgb(255, 255, ${Math.floor(255 * t)})`;
			}
			case "hot": {
				// Black to red to yellow to white
				if (normalizedPower < 0.33) {
					const t = normalizedPower * 3;
					return `rgb(${Math.floor(255 * t)}, 0, 0)`;
				}
				if (normalizedPower < 0.67) {
					const t = (normalizedPower - 0.33) * 3;
					return `rgb(255, ${Math.floor(255 * t)}, 0)`;
				}
				const t = (normalizedPower - 0.67) * 3;
				return `rgb(255, 255, ${Math.floor(255 * t)})`;
			}
			case "gray":
				return `rgb(${intensity}, ${intensity}, ${intensity})`;
			case "inferno": {
				// Black to purple to red to yellow
				if (normalizedPower < 0.33) {
					const t = normalizedPower * 3;
					return `rgb(${Math.floor(128 * t)}, 0, ${Math.floor(255 * t)})`;
				}
				if (normalizedPower < 0.67) {
					const t = (normalizedPower - 0.33) * 3;
					return `rgb(${Math.floor(128 + 127 * t)}, 0, ${Math.floor(
						255 - 255 * t,
					)})`;
				}
				const t = (normalizedPower - 0.67) * 3;
				return `rgb(255, ${Math.floor(255 * t)}, 0)`;
			}
			case "magma": {
				// Black to purple to pink to white
				if (normalizedPower < 0.33) {
					const t = normalizedPower * 3;
					return `rgb(${Math.floor(128 * t)}, 0, ${Math.floor(255 * t)})`;
				}
				if (normalizedPower < 0.67) {
					const t = (normalizedPower - 0.33) * 3;
					return `rgb(${Math.floor(128 + 127 * t)}, 0, ${Math.floor(
						255 - 127 * t,
					)})`;
				}
				const t = (normalizedPower - 0.67) * 3;
				return `rgb(255, ${Math.floor(255 * t)}, ${Math.floor(128 + 127 * t)})`;
			}
			default: {
				// Default to viridis-like blue to green to yellow to red
				if (normalizedPower < 0.25) {
					return `rgb(0, ${Math.floor(intensity * 4)}, ${255 - intensity})`;
				}
				if (normalizedPower < 0.5) {
					const t = (normalizedPower - 0.25) * 4;
					return `rgb(0, 255, ${Math.floor(255 * (1 - t))})`;
				}
				if (normalizedPower < 0.75) {
					const t = (normalizedPower - 0.5) * 4;
					return `rgb(${Math.floor(255 * t)}, 255, 0)`;
				}
				const t = (normalizedPower - 0.75) * 4;
				return `rgb(255, ${Math.floor(255 * (1 - t))}, 0)`;
			}
		}
	}

	/**
	 * Draw a highlight box around a slice
	 */
	drawHighlightBox(
		sliceIndex,
		startSliceIndex,
		endSliceIndex,
		sliceHeight,
		canvasWidth,
		strokeStyle,
		lineWidth = 1,
	) {
		if (!this.overlayCtx || !this.overlayCanvas) return;

		// Find the position of the slice in the visible range
		const sliceInRange = sliceIndex - startSliceIndex;
		if (sliceInRange < 0 || sliceInRange >= endSliceIndex - startSliceIndex)
			return;

		// Calculate Y position with margins: bottom slice is at bottom margin
		const maxVisibleSlices = Math.min(
			this.totalSlices,
			this.WATERFALL_WINDOW_SIZE,
		);
		const y =
			this.BOTTOM_MARGIN + (maxVisibleSlices - 1 - sliceInRange) * sliceHeight;

		// Draw highlight box (between left index area and right legend area)
		this.overlayCtx.strokeStyle = strokeStyle;
		this.overlayCtx.lineWidth = lineWidth;
		const plotWidth =
			canvasWidth - this.LEFT_INDEX_WIDTH - this.RIGHT_LEGEND_WIDTH;
		this.overlayCtx.strokeRect(
			this.LEFT_INDEX_WIDTH,
			y,
			plotWidth,
			sliceHeight,
		);
	}

	/**
	 * Draw highlight box around the current slice
	 */
	drawCurrentSliceHighlight(
		canvas,
		sliceHeight,
		startSliceIndex,
		endSliceIndex,
	) {
		this.drawHighlightBox(
			this.currentSliceIndex,
			startSliceIndex,
			endSliceIndex,
			sliceHeight,
			canvas.width,
			"#000000", // Black color for current slice
			1,
		);
	}

	/**
	 * Draw hover highlight box around the slice being hovered
	 */
	drawHoverHighlight(canvas, sliceHeight, startSliceIndex, endSliceIndex) {
		if (this.hoveredSliceIndex === null) return;

		this.drawHighlightBox(
			this.hoveredSliceIndex,
			startSliceIndex,
			endSliceIndex,
			sliceHeight,
			canvas.width,
			"#808080", // Light grey color for hover
			1,
		);
	}

	/**
	 * Clear the overlay canvas
	 */
	clearOverlay() {
		if (!this.overlayCtx || !this.overlayCanvas) return;
		this.overlayCtx.clearRect(
			0,
			0,
			this.overlayCanvas.width,
			this.overlayCanvas.height,
		);
	}

	/**
	 * Redraw all highlight boxes on the overlay
	 */
	redrawHighlights(canvas, sliceHeight, startSliceIndex, endSliceIndex) {
		if (this.overlayCanvas && this.overlayCtx) {
			// Clear the overlay first
			this.clearOverlay();

			// Draw current slice highlight
			this.drawCurrentSliceHighlight(
				canvas,
				sliceHeight,
				startSliceIndex,
				endSliceIndex,
			);

			// Draw hover highlight if there is one
			this.drawHoverHighlight(
				canvas,
				sliceHeight,
				startSliceIndex,
				endSliceIndex,
			);
		}
		// If no overlay, just skip drawing highlights

		// Always update the slice index legend to show hover state
		this.updateSliceIndexLegend();
	}

	/**
	 * Update highlights after slice changes (helper method)
	 */
	updateHighlightsAfterSliceChange() {
		if (this.canvas && this.waterfallData.length > 0) {
			const plotHeight =
				this.canvas.height - this.TOP_MARGIN - this.BOTTOM_MARGIN;
			const sliceHeight =
				plotHeight / Math.min(this.totalSlices, this.WATERFALL_WINDOW_SIZE);
			this.redrawHighlights(
				this.canvas,
				sliceHeight,
				this.waterfallWindowStart,
				Math.min(
					this.waterfallWindowStart + this.WATERFALL_WINDOW_SIZE,
					this.totalSlices,
				),
			);
		}
	}

	/**
	 * Draw color legend showing dB scale
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
		const gradientStops = this.generateColorMapGradient();
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
	 * Generate CSS gradient string for the selected color map
	 */
	generateColorMapGradient() {
		const stops = [];
		const numStops = 20;

		for (let i = 0; i <= numStops; i++) {
			const fraction = i / numStops;
			const normalizedPower = fraction;
			const color = this.getColorForPower(normalizedPower);
			stops.push(`${color} ${fraction * 100}%`);
		}

		return `linear-gradient(to bottom, ${stops.join(", ")})`;
	}

	/**
	 * Render the periodogram chart
	 */
	renderPeriodogram() {
		if (!this.periodogramChart || this.waterfallData.length === 0) return;

		const currentSlice = this.waterfallData[this.currentSliceIndex];
		if (!currentSlice) return;

		const dataArray = this.parseWaterfallData(currentSlice.data);
		if (!dataArray) return;

		// Create data points for the chart
		const dataPoints = dataArray.map((power, index) => {
			const frequency =
				(index - dataArray.length / 2) *
				(currentSlice.sample_rate / dataArray.length);
			return { x: frequency, y: power };
		});

		// Update the chart
		this.periodogramChart.options.data[0].dataPoints = dataPoints;
		this.periodogramChart.render();
	}

	/**
	 * Event handlers
	 */
	handlePlayPause() {
		if (this.isPlaying) {
			this.stopPlayback();
		} else {
			this.startPlayback();
		}
	}

	handleSave() {
		this.saveVisualization();
	}

	handleSliceChange(event) {
		this.currentSliceIndex = Number.parseInt(event.target.value);
		this.hoveredSliceIndex = null;
		this.updateSliceUI();
		this.render();
		// Redraw highlights on overlay after render
		this.updateHighlightsAfterSliceChange();
	}

	handleSliceIndexInputChange(event) {
		const newIndex = Number.parseInt(event.target.value) - 1; // Convert from 1-based to 0-based
		if (
			!Number.isNaN(newIndex) &&
			newIndex >= 0 &&
			newIndex < this.totalSlices
		) {
			this.currentSliceIndex = newIndex;
			this.hoveredSliceIndex = null;
			this.updateSliceUI();
			this.render();
			// Redraw highlights on overlay after render
			this.updateHighlightsAfterSliceChange();
		} else {
			// Reset to current value if invalid
			this.updateSliceIndexInput();
		}
	}

	handleSliceIndexInputKeyDown(event) {
		switch (event.key) {
			case "ArrowUp":
			case "ArrowLeft":
				event.preventDefault();
				this.handleDecrementSlice();
				break;
			case "ArrowDown":
			case "ArrowRight":
				event.preventDefault();
				this.handleIncrementSlice();
				break;
			case "Enter":
				event.preventDefault();
				event.target.blur(); // Commit the change
				break;
		}
	}

	handleDecrementSlice() {
		if (this.currentSliceIndex > 0) {
			this.currentSliceIndex--;
			// Clear hover state when changing slice
			this.hoveredSliceIndex = null;
			this.updateSliceUI();
			this.render();
			// Redraw highlights on overlay after render
			this.updateHighlightsAfterSliceChange();
		}
	}

	handleIncrementSlice() {
		if (this.currentSliceIndex < this.totalSlices - 1) {
			this.currentSliceIndex++;
			// Clear hover state when changing slice
			this.hoveredSliceIndex = null;
			this.updateSliceUI();
			this.render();
			// Redraw highlights on overlay after render
			this.updateHighlightsAfterSliceChange();
		}
	}

	handleScrollUp() {
		// Move the window up to show more recent slices
		const newWindowStart = Math.min(
			this.totalSlices - this.WATERFALL_WINDOW_SIZE,
			this.waterfallWindowStart + this.WATERFALL_WINDOW_SIZE,
		);
		if (newWindowStart !== this.waterfallWindowStart) {
			this.waterfallWindowStart = newWindowStart;
			// Keep the selected slice in the same relative position if possible
			if (this.currentSliceIndex < this.waterfallWindowStart) {
				this.currentSliceIndex = this.waterfallWindowStart;
			} else if (
				this.currentSliceIndex >=
				this.waterfallWindowStart + this.WATERFALL_WINDOW_SIZE
			) {
				this.currentSliceIndex =
					this.waterfallWindowStart + this.WATERFALL_WINDOW_SIZE - 1;
			}
			// Clear hover state when scrolling
			this.hoveredSliceIndex = null;
			this.updateSliceUI();
			this.render();
			// Redraw highlights on overlay after render
			this.updateHighlightsAfterSliceChange();
		}
	}

	handleScrollDown() {
		// Move the window down to show older slices
		const newWindowStart = Math.max(
			0,
			this.waterfallWindowStart - this.WATERFALL_WINDOW_SIZE,
		);
		if (newWindowStart !== this.waterfallWindowStart) {
			this.waterfallWindowStart = newWindowStart;
			// Keep the selected slice in the same relative position if possible
			if (this.currentSliceIndex < this.waterfallWindowStart) {
				this.currentSliceIndex = this.waterfallWindowStart;
			} else if (
				this.currentSliceIndex >=
				this.waterfallWindowStart + this.WATERFALL_WINDOW_SIZE
			) {
				this.currentSliceIndex =
					this.waterfallWindowStart + this.WATERFALL_WINDOW_SIZE - 1;
			}
			// Clear hover state when scrolling
			this.hoveredSliceIndex = null;
			this.updateSliceUI();
			this.render();
			// Redraw highlights on overlay after render
			this.updateHighlightsAfterSliceChange();
		}
	}

	handlePlaybackSpeedChange(event) {
		this.playbackSpeed = Number.parseFloat(event.target.value);
		// Clear hover state when changing playback speed
		this.hoveredSliceIndex = null;
		if (this.isPlaying) {
			this.stopPlayback();
			this.startPlayback();
		}
		// Redraw highlights on overlay after render
		this.updateHighlightsAfterSliceChange();
	}

	handleFFTSizeChange(event) {
		this.fftSize = Number.parseInt(event.target.value);
		// Clear hover state when changing FFT size
		this.hoveredSliceIndex = null;
		this.render();
		// Redraw highlights on overlay after render
		this.updateHighlightsAfterSliceChange();
	}

	handleColorMapChange(event) {
		this.colorMap = event.target.value;
		// Clear hover state when changing color map
		this.hoveredSliceIndex = null;
		this.updateColorLegend();
		this.render();
		// Redraw highlights on overlay after render
		this.updateHighlightsAfterSliceChange();
	}

	/**
	 * Start playback animation
	 */
	startPlayback() {
		if (this.isPlaying) return;

		this.isPlaying = true;
		const playPauseBtn = document.getElementById("playPauseBtn");
		if (playPauseBtn) {
			playPauseBtn.innerHTML = '<i class="bi bi-pause-fill"></i> Pause';
			playPauseBtn.classList.remove("btn-outline-primary");
			playPauseBtn.classList.add("btn-primary");
		}

		const interval = 1000 / this.playbackSpeed; // Convert fps to milliseconds
		this.playbackInterval = setInterval(() => {
			// Move to next slice, but don't loop around
			if (this.currentSliceIndex < this.totalSlices - 1) {
				this.currentSliceIndex++;
			} else {
				// Stop playback when we reach the end
				this.stopPlayback();
				return;
			}

			// Update UI
			const slider = document.getElementById("currentSlice");
			if (slider) {
				slider.value = this.currentSliceIndex;
			}

			// Clear hover state when changing slice during playback
			this.hoveredSliceIndex = null;

			this.updateSliceUI();

			// Re-render
			this.render();
			// Redraw highlights on overlay after render
			this.updateHighlightsAfterSliceChange();
		}, interval);
	}

	/**
	 * Stop playback animation
	 */
	stopPlayback() {
		if (!this.isPlaying) return;

		this.isPlaying = false;
		if (this.playbackInterval) {
			clearInterval(this.playbackInterval);
			this.playbackInterval = null;
		}

		const playPauseBtn = document.getElementById("playPauseBtn");
		if (playPauseBtn) {
			playPauseBtn.innerHTML = '<i class="bi bi-play-fill"></i> Play';
			playPauseBtn.classList.remove("btn-primary");
			playPauseBtn.classList.add("btn-outline-primary");
		}
	}

	/**
	 * Save the visualization as an image
	 */
	saveVisualization() {
		try {
			// Create a combined canvas with both periodogram and waterfall
			const combinedCanvas = document.createElement("canvas");
			const ctx = combinedCanvas.getContext("2d");

			// Set size
			combinedCanvas.width = this.canvas.width;
			combinedCanvas.height = this.canvas.height + 200; // Add space for periodogram

			// Fill background
			ctx.fillStyle = "white";
			ctx.fillRect(0, 0, combinedCanvas.width, combinedCanvas.height);

			// Draw periodogram (simplified)
			ctx.fillStyle = "#6c757d";
			ctx.font = "16px Arial";
			ctx.fillText("Periodogram", 10, 20);

			// Draw waterfall
			ctx.drawImage(this.canvas, 0, 200);

			// Convert to blob and download
			combinedCanvas.toBlob((blob) => {
				const url = URL.createObjectURL(blob);
				const a = document.createElement("a");
				a.href = url;
				a.download = `waterfall_${this.captureUuid}_${Date.now()}.png`;
				document.body.appendChild(a);
				a.click();
				document.body.removeChild(a);
				URL.revokeObjectURL(url);
			}, "image/png");
		} catch (error) {
			console.error("Failed to save visualization:", error);
			this.showError("Failed to save visualization");
		}
	}

	/**
	 * Show/hide loading state
	 */
	showLoading(show) {
		const overlay = document.getElementById("loadingOverlay");
		if (overlay) {
			overlay.style.display = show ? "flex" : "none";
		}
	}

	/**
	 * Show error message
	 */
	showError(message) {
		// Create error alert
		const alertDiv = document.createElement("div");
		alertDiv.className = "alert alert-danger alert-dismissible fade show";
		alertDiv.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;

		// Insert at top of content
		const content = document.querySelector(".container-fluid");
		if (content) {
			content.insertBefore(alertDiv, content.firstChild);
		}
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
			this.WATERFALL_WINDOW_SIZE,
		);
		const plotHeight =
			this.canvas.height - this.TOP_MARGIN - this.BOTTOM_MARGIN;
		const sliceHeight = plotHeight / maxVisibleSlices;

		// Calculate clicked slice index
		const adjustedY = y - this.TOP_MARGIN;
		if (adjustedY < 0 || adjustedY > plotHeight) return; // Click outside plot area

		const clickedRow = Math.floor(adjustedY / sliceHeight);
		const clickedSliceIndex =
			this.waterfallWindowStart + this.WATERFALL_WINDOW_SIZE - clickedRow - 1;

		// Validate the index is within bounds
		if (clickedSliceIndex >= 0 && clickedSliceIndex < this.totalSlices) {
			// Only change the selected slice, don't shift the window
			this.currentSliceIndex = clickedSliceIndex;

			// Clear hover state when selecting a slice
			this.hoveredSliceIndex = null;

			// Update UI
			const slider = document.getElementById("currentSlice");
			if (slider) {
				slider.value = this.currentSliceIndex;
			}
			this.updateSliceUI();

			// Redraw highlights on overlay (window stays in place, only highlight changes)
			this.updateHighlightsAfterSliceChange();
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
			this.WATERFALL_WINDOW_SIZE,
		);
		const plotHeight =
			this.canvas.height - this.TOP_MARGIN - this.BOTTOM_MARGIN;
		const sliceHeight = plotHeight / maxVisibleSlices;

		// Calculate hovered slice index
		const adjustedY = y - this.TOP_MARGIN;
		if (adjustedY < 0 || adjustedY > plotHeight) {
			this.canvas.style.cursor = "default";
			this.hoveredSliceIndex = null;
			this.render(); // Re-render to remove hover highlight
			return;
		}

		const hoveredRow = Math.floor(adjustedY / sliceHeight);
		const hoveredSliceIndex =
			this.waterfallWindowStart + this.WATERFALL_WINDOW_SIZE - hoveredRow - 1;

		// Update cursor style based on whether we're hovering over a valid slice
		if (hoveredSliceIndex >= 0 && hoveredSliceIndex < this.totalSlices) {
			this.canvas.style.cursor = "pointer";
			// Update hovered slice index and redraw highlights on overlay
			if (this.hoveredSliceIndex !== hoveredSliceIndex) {
				this.hoveredSliceIndex = hoveredSliceIndex;
				this.updateHighlightsAfterSliceChange();
			}
		} else {
			this.canvas.style.cursor = "default";
			this.hoveredSliceIndex = null;
			// Clear hover highlight from overlay
			this.updateHighlightsAfterSliceChange();
		}
	}

	/**
	 * Handle canvas mouse leave
	 */
	handleCanvasMouseLeave() {
		if (this.canvas) {
			this.canvas.style.cursor = "default";
		}
		// Clear hover state and redraw highlights on overlay
		if (this.hoveredSliceIndex !== null) {
			this.hoveredSliceIndex = null;
			this.updateHighlightsAfterSliceChange();
		}
	}

	/**
	 * Handle keyboard navigation
	 */
	handleKeyDown(event) {
		// Only handle arrow keys when not in an input field
		if (event.target.tagName === "INPUT" || event.target.tagName === "SELECT") {
			return;
		}

		switch (event.key) {
			case "ArrowDown":
			case "ArrowLeft":
				event.preventDefault();
				this.handleDecrementSlice();
				break;
			case "ArrowUp":
			case "ArrowRight":
				event.preventDefault();
				this.handleIncrementSlice();
				break;
			case "PageUp":
				event.preventDefault();
				this.handleScrollUp();
				break;
			case "PageDown":
				event.preventDefault();
				this.handleScrollDown();
				break;
		}
	}

	/**
	 * Update the color legend positioning to account for margins
	 */
	updateColorLegendPosition() {
		const legendElement = document.getElementById("colorLegend");
		if (!legendElement) return;

		// Position the legend to account for top and bottom margins
		legendElement.style.top = `${this.TOP_MARGIN}px`;
		legendElement.style.bottom = `${this.BOTTOM_MARGIN}px`;
	}

	/**
	 * Update the slice index legend
	 */
	updateSliceIndexLegend() {
		if (!this.ctx || !this.canvas) return;

		const ctx = this.ctx;
		const canvas = this.canvas;

		// Calculate dimensions with margins
		const plotHeight = canvas.height - this.TOP_MARGIN - this.BOTTOM_MARGIN;
		const maxVisibleSlices = Math.min(
			this.totalSlices,
			this.WATERFALL_WINDOW_SIZE,
		);
		const sliceHeight = plotHeight / maxVisibleSlices;

		// Clear the left side area for labels
		const labelWidth = this.LEFT_INDEX_WIDTH;
		ctx.fillStyle = "rgba(255, 255, 255, 0.95)";
		ctx.fillRect(0, 0, labelWidth, canvas.height);

		// Only draw indices if we have 5 or more rows
		if (maxVisibleSlices >= 5) {
			ctx.font = "10px Arial";
			ctx.textAlign = "right";
			ctx.fillStyle = "#000";

			// Show every 5th index
			for (let i = 0; i < maxVisibleSlices; i++) {
				const sliceIndex = this.waterfallWindowStart + i;
				if (sliceIndex >= this.totalSlices) break;

				const displayedIndex = sliceIndex + 1; // Convert to 1-based for display
				// Calculate Y position with margins: bottom slice is at bottom margin
				const y =
					this.BOTTOM_MARGIN +
					(maxVisibleSlices - 1 - i) * sliceHeight +
					sliceHeight / 2;

				// Only draw if this index should be highlighted (every 5th, current slice, or hovered slice)
				if (
					displayedIndex % 5 === 0 ||
					sliceIndex === this.currentSliceIndex ||
					sliceIndex === this.hoveredSliceIndex
				) {
					// Determine highlight color based on slice type
					if (sliceIndex === this.currentSliceIndex) {
						ctx.fillStyle = "#000"; // Black for current slice
					} else if (sliceIndex === this.hoveredSliceIndex) {
						ctx.fillStyle = "#333"; // Dark grey for hovered slice
					} else {
						ctx.fillStyle = "#999"; // Light grey for other indices
					}

					ctx.fillText(String(displayedIndex), labelWidth - 5, y + 3);
				}
			}
		}
	}

	/**
	 * Cleanup resources
	 */
	destroy() {
		this.stopPlayback();
		window.removeEventListener("resize", () => this.resizeCanvas());
		document.removeEventListener("keydown", this.handleKeyDown);
	}
}
