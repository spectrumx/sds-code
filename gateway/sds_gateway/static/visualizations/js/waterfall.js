/**
 * Waterfall Visualization Class
 * Handles the waterfall visualization using vanilla JavaScript, D3, and CanvasJS
 */
class WaterfallVisualization {
	constructor(captureUuid) {
		this.captureUuid = captureUuid;
		this.waterfallData = [];
		this.currentSliceIndex = 0;
		this.waterfallWindowStart = 0; // Track the start of the visible waterfall window
		this.isPlaying = false;
		this.playbackInterval = null;
		this.playbackSpeed = 1; // fps
		this.fftSize = 1024;
		this.colorMap = "viridis";
		this.totalSlices = 0;
		this.canvas = null;
		this.ctx = null;
		this.periodogramChart = null;
		this.scaleMin = null;
		this.scaleMax = null;

		// Constants
		this.WATERFALL_WINDOW_SIZE = 100; // Number of slices visible in the waterfall plot at once
		this.LEFT_INDEX_WIDTH = 60; // Width of the left index legend area
		this.RIGHT_LEGEND_WIDTH = 80; // Width of the right color legend area

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

		// Re-render if we have data
		if (this.waterfallData.length > 0) {
			this.render();
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

		// Calculate dimensions
		const maxVisibleSlices = Math.min(
			this.totalSlices,
			this.WATERFALL_WINDOW_SIZE,
		);
		const sliceHeight = canvas.height / maxVisibleSlices;

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
					// Calculate Y position: bottom slice is at bottom of canvas
					const y = canvas.height - (i + 1) * sliceHeight;

					this.drawWaterfallSlice(sliceData, y, sliceHeight, canvas.width);
				}
			}
		}

		// Draw highlight box around current slice
		this.drawCurrentSliceHighlight(
			canvas,
			sliceHeight,
			startSliceIndex,
			endSliceIndex,
		);

		// Update color legend
		this.updateColorLegend();

		// Update slice index legend
		this.updateSliceIndexLegend();
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
	 * Draw highlight box around the current slice
	 */
	drawCurrentSliceHighlight(
		canvas,
		sliceHeight,
		startSliceIndex,
		endSliceIndex,
	) {
		if (!this.ctx) return;

		const ctx = this.ctx;

		// Find the position of the current slice in the visible range
		const currentSliceInRange = this.currentSliceIndex - startSliceIndex;
		if (
			currentSliceInRange < 0 ||
			currentSliceInRange >= endSliceIndex - startSliceIndex
		)
			return;

		// Calculate Y position: bottom slice is at bottom of canvas
		const y = canvas.height - (currentSliceInRange + 1) * sliceHeight;

		// Draw highlight box (between left index area and right legend area)
		ctx.strokeStyle = "#000000";
		ctx.lineWidth = 1;
		const plotWidth =
			canvas.width - this.LEFT_INDEX_WIDTH - this.RIGHT_LEGEND_WIDTH;
		ctx.strokeRect(this.LEFT_INDEX_WIDTH, y, plotWidth, sliceHeight);

		// Reset stroke style for other drawing operations
		ctx.strokeStyle = "#6c757d";
		ctx.lineWidth = 1;
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
		this.updateSliceUI();
		this.render();
	}

	handleSliceIndexInputChange(event) {
		const newIndex = Number.parseInt(event.target.value) - 1; // Convert from 1-based to 0-based
		if (
			!Number.isNaN(newIndex) &&
			newIndex >= 0 &&
			newIndex < this.totalSlices
		) {
			this.currentSliceIndex = newIndex;
			this.updateSliceUI();
			this.render();
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
			this.updateSliceUI();
			this.render();
		}
	}

	handleIncrementSlice() {
		if (this.currentSliceIndex < this.totalSlices - 1) {
			this.currentSliceIndex++;
			this.updateSliceUI();
			this.render();
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
			this.updateSliceUI();
			this.render();
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
			this.updateSliceUI();
			this.render();
		}
	}

	handlePlaybackSpeedChange(event) {
		this.playbackSpeed = Number.parseFloat(event.target.value);
		if (this.isPlaying) {
			this.stopPlayback();
			this.startPlayback();
		}
	}

	handleFFTSizeChange(event) {
		this.fftSize = Number.parseInt(event.target.value);
		this.render();
	}

	handleColorMapChange(event) {
		this.colorMap = event.target.value;
		this.updateColorLegend();
		this.render();
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
			this.updateSliceUI();

			// Re-render
			this.render();
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
		const sliceHeight = this.canvas.height / maxVisibleSlices;

		// Calculate clicked slice index (from bottom to top)
		const clickedRow = Math.floor((this.canvas.height - y) / sliceHeight);
		const clickedSliceIndex = this.waterfallWindowStart + clickedRow;

		// Validate the index is within bounds
		if (clickedSliceIndex >= 0 && clickedSliceIndex < this.totalSlices) {
			// Only change the selected slice, don't shift the window
			this.currentSliceIndex = clickedSliceIndex;

			// Update UI
			const slider = document.getElementById("currentSlice");
			if (slider) {
				slider.value = this.currentSliceIndex;
			}
			this.updateSliceUI();

			// Re-render (window stays in place, only highlight changes)
			this.render();
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
		const sliceHeight = this.canvas.height / maxVisibleSlices;

		// Calculate hovered slice index (from bottom to top)
		const hoveredRow = Math.floor((this.canvas.height - y) / sliceHeight);
		const hoveredSliceIndex = this.waterfallWindowStart + hoveredRow;

		// Update cursor style based on whether we're hovering over a valid slice
		if (hoveredSliceIndex >= 0 && hoveredSliceIndex < this.totalSlices) {
			this.canvas.style.cursor = "pointer";
		} else {
			this.canvas.style.cursor = "crosshair";
		}
	}

	/**
	 * Handle canvas mouse leave
	 */
	handleCanvasMouseLeave() {
		if (this.canvas) {
			this.canvas.style.cursor = "crosshair";
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
	 * Update the slice index legend
	 */
	updateSliceIndexLegend() {
		if (!this.ctx || !this.canvas) return;

		const ctx = this.ctx;
		const canvas = this.canvas;

		// Calculate dimensions
		const maxVisibleSlices = Math.min(
			this.totalSlices,
			this.WATERFALL_WINDOW_SIZE,
		);
		const sliceHeight = canvas.height / maxVisibleSlices;

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
				const y = canvas.height - (i + 1) * sliceHeight + sliceHeight / 2;

				// Only draw if this index should be highlighted (every 5th or current slice)
				if (displayedIndex % 5 === 0 || sliceIndex === this.currentSliceIndex) {
					// Highlight current slice
					if (sliceIndex === this.currentSliceIndex) {
						ctx.fillStyle = "#000";
					} else {
						ctx.fillStyle = "#999";
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
