/**
 * Waterfall Visualization Class
 * Handles the waterfall visualization using vanilla JavaScript, D3, and CanvasJS
 */
class WaterfallVisualization {
	constructor(captureUuid) {
		this.captureUuid = captureUuid;
		this.waterfallData = [];
		this.currentSliceIndex = 0;
		this.isPlaying = false;
		this.playbackInterval = null;
		this.playbackSpeed = 1; // fps
		this.fftSize = 1024;
		this.colorMap = "viridis";
		this.totalSlices = 0;
		this.canvas = null;
		this.ctx = null;
		this.periodogramChart = null;

		// Bind methods to preserve context
		this.handlePlayPause = this.handlePlayPause.bind(this);
		this.handleSave = this.handleSave.bind(this);
		this.handleSliceChange = this.handleSliceChange.bind(this);
		this.handlePlaybackSpeedChange = this.handlePlaybackSpeedChange.bind(this);
		this.handleFFTSizeChange = this.handleFFTSizeChange.bind(this);
		this.handleColorMapChange = this.handleColorMapChange.bind(this);
	}

	/**
	 * Initialize the waterfall visualization
	 */
	async initialize() {
		try {
			console.log(
				"Initializing waterfall visualization for capture:",
				this.captureUuid,
			);

			this.setupEventListeners();
			this.initializeCanvas();
			this.initializePeriodogramChart();

			// Load initial data
			await this.loadWaterfallData();

			// Render initial visualization
			this.render();

			console.log("Waterfall visualization initialized successfully");
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

			// Update UI elements
			this.updateSliceSlider();
			this.updateSliceCounter();

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

		if (slider) {
			slider.max = Math.max(0, this.totalSlices - 1);
			slider.value = 0;
		}

		if (counter) {
			counter.textContent = `0 / ${this.totalSlices}`;
		}
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

		// Get current slice data
		const currentSlice = this.waterfallData[this.currentSliceIndex];
		if (!currentSlice) return;

		// Parse the base64 data
		const dataArray = this.parseWaterfallData(currentSlice.data);
		if (!dataArray) return;

		// Calculate dimensions
		const fftPoints = dataArray.length;
		const sliceHeight = canvas.height / Math.min(this.totalSlices, 100); // Show max 100 slices

		// Draw waterfall
		for (let i = 0; i < Math.min(this.totalSlices, 100); i++) {
			const sliceIndex = Math.max(0, this.currentSliceIndex - 99 + i);
			const slice = this.waterfallData[sliceIndex];

			if (slice) {
				const sliceData = this.parseWaterfallData(slice.data);
				if (sliceData) {
					this.drawWaterfallSlice(
						sliceData,
						i * sliceHeight,
						sliceHeight,
						canvas.width,
					);
				}
			}
		}

		// Draw axes and labels
		this.drawWaterfallAxes();
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
		const pointWidth = width / fftPoints;

		// Find min/max for normalization
		const minPower = Math.min(...data);
		const maxPower = Math.max(...data);
		const powerRange = maxPower - minPower;

		for (let i = 0; i < fftPoints; i++) {
			const power = data[i];
			const normalizedPower = (power - minPower) / powerRange;
			const color = this.getColorForPower(normalizedPower);

			ctx.fillStyle = color;
			ctx.fillRect(i * pointWidth, y, pointWidth, height);
		}
	}

	/**
	 * Get color for power value using selected color map
	 */
	getColorForPower(normalizedPower) {
		// Simple color mapping - can be enhanced with proper color maps
		const intensity = Math.floor(normalizedPower * 255);

		switch (this.colorMap) {
			case "viridis":
				return `rgb(${intensity}, ${intensity}, ${255 - intensity})`;
			case "plasma":
				return `rgb(${255 - intensity}, ${intensity}, ${intensity})`;
			case "hot":
				return `rgb(${255}, ${intensity}, 0)`;
			case "gray":
				return `rgb(${intensity}, ${intensity}, ${intensity})`;
			default:
				return `rgb(${intensity}, ${intensity}, ${255 - intensity})`;
		}
	}

	/**
	 * Draw waterfall axes and labels
	 */
	drawWaterfallAxes() {
		if (!this.ctx || !this.canvas) return;

		const ctx = this.ctx;
		const canvas = this.canvas;

		ctx.strokeStyle = "#6c757d";
		ctx.lineWidth = 1;
		ctx.font = "12px Arial";
		ctx.fillStyle = "#6c757d";

		// Y-axis (time)
		ctx.beginPath();
		ctx.moveTo(0, 0);
		ctx.lineTo(0, canvas.height);
		ctx.stroke();

		// X-axis (frequency)
		ctx.beginPath();
		ctx.moveTo(0, canvas.height);
		ctx.lineTo(canvas.width, canvas.height);
		ctx.stroke();

		// Labels
		ctx.save();
		ctx.translate(10, canvas.height / 2);
		ctx.rotate(-Math.PI / 2);
		ctx.fillText("Time", 0, 0);
		ctx.restore();

		ctx.fillText("Frequency (Hz)", canvas.width / 2, canvas.height - 5);
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
		this.updateSliceCounter();
		this.render();
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
			this.currentSliceIndex = (this.currentSliceIndex + 1) % this.totalSlices;

			// Update UI
			const slider = document.getElementById("currentSlice");
			if (slider) {
				slider.value = this.currentSliceIndex;
			}
			this.updateSliceCounter();

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
	 * Cleanup resources
	 */
	destroy() {
		this.stopPlayback();
		window.removeEventListener("resize", () => this.resizeCanvas());
	}
}
