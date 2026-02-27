/**
 * Periodogram Chart Manager
 * Manages CanvasJS chart operations for the periodogram display
 */

import {
	CANVASJS_LEFT_MARGIN,
	CANVASJS_RIGHT_MARGIN,
	DEFAULT_SCALE_MAX,
	DEFAULT_SCALE_MIN,
	PLOTS_LEFT_MARGIN,
	PLOTS_RIGHT_MARGIN,
} from "./constants.js";

class PeriodogramChart {
	constructor(containerId) {
		this.containerId = containerId;
		this.chart = null;
	}

	/**
	 * Initialize the periodogram chart using CanvasJS
	 */
	initialize() {
		const container = document.getElementById(this.containerId);
		if (!container) {
			console.warn(
				"Periodogram chart container not found, skipping chart initialization",
			);
			return;
		}

		// Check if CanvasJS is available
		if (typeof CanvasJS === "undefined") {
			console.warn("CanvasJS not available, skipping chart initialization");
			return;
		}

		try {
			this.chart = new CanvasJS.Chart(container, {
				animationEnabled: false,
				theme: "light2",
				title: {},
				axisX: {
					// Hide axisX and remove margin to reduce space between periodogram and waterfall
					tickLength: 0,
					labelFontSize: 0,
					labelPlacement: "inside",
					lineThickness: 0,
					margin: 0,
				},
				axisX2: {
					title: "Frequency (MHz)",
					titlePadding: 10,
					titleFontSize: 14,
					titleFontWeight: "bold",
					labelFontSize: 11,
					labelAngle: 0,
					minimum: -1,
					maximum: 1,
					gridThickness: 1,
					gridColor: "#e9ecef",
					labelFormatter: (e) => {
						// Format large frequencies nicely (e.g., 2400.5 instead of 2400.500000)
						return e.value.toFixed(1);
					},
				},
				axisY: {
					interval: 20,
					gridThickness: 1,
					gridColor: "#e9ecef",
					minimum: DEFAULT_SCALE_MIN,
					maximum: DEFAULT_SCALE_MAX,
					viewportMinimum: DEFAULT_SCALE_MIN,
					viewportMaximum: DEFAULT_SCALE_MAX,
					includeZero: false,
					tickLength: 0,
					labelPlacement: "inside",
					labelBackgroundColor: "white",
					labelFormatter: (e) => {
						// Replace minus sign with longer dash symbol for better readability
						return e.value.toString().replace("-", "\u{2012}");
					},
					labelFontWeight: "bold",
					labelPadding: 1,
					stripLines: [],
					// Apply left margin for alignment with waterfall plot
					margin: 0,
				},
				data: [
					{
						type: "line",
						dataPoints: [],
						color: "#0d6efd",
						lineThickness: 2,
						axisXType: "secondary", // Use secondary X axis for proper alignment
					},
				],
			});

			this.setCSSMarginProperties();
		} catch (error) {
			console.error("Failed to initialize periodogram chart:", error);
			this.chart = null;
		}
	}

	/**
	 * Update the y-axis bounds to use global scale
	 */
	updateYAxisBounds(scaleMin, scaleMax) {
		if (this.chart && scaleMin !== null && scaleMax !== null) {
			this.chart.options.axisY.minimum = scaleMin;
			this.chart.options.axisY.maximum = scaleMax;
			this.chart.options.axisY.viewportMinimum = scaleMin;
			this.chart.options.axisY.viewportMaximum = scaleMax;
		}
	}

	/**
	 * Render the periodogram chart with new data
	 */
	renderPeriodogram(currentSlice) {
		if (!this.chart || !currentSlice) return;

		try {
			const dataArray = currentSlice.data;
			if (!dataArray || !Array.isArray(dataArray) || dataArray.length === 0) {
				console.warn("Invalid data array for periodogram render");
				return;
			}

			const sampleRate = currentSlice.sample_rate || 0;
			const centerFreq = currentSlice.center_frequency || 0;
			const freqStep = sampleRate / dataArray.length;

			// Create data points for the chart - include center frequency offset
			const dataPoints = dataArray.map((power, index) => {
				// Calculate frequency relative to center frequency
				const offsetFromCenter = (index - dataArray.length / 2) * freqStep;
				const frequency = centerFreq + offsetFromCenter;
				const freqMHz = frequency / 1000000;

				return { x: freqMHz, y: power };
			});

			this.chart.options.data[0].dataPoints = dataPoints;

			if (dataPoints.length > 0 && sampleRate && Number.isFinite(sampleRate)) {
				const minFreq = centerFreq - (dataArray.length / 2) * freqStep;
				const maxFreq = centerFreq + (dataArray.length / 2) * freqStep;

				const minFreqMHz = minFreq / 1000000;
				const maxFreqMHz = maxFreq / 1000000;

				if (minFreqMHz < maxFreqMHz) {
					this.chart.options.axisX2.minimum = minFreqMHz;
					this.chart.options.axisX2.maximum = maxFreqMHz;

					// Set a sensible interval based on the frequency range
					const rangeMHz = maxFreqMHz - minFreqMHz;
					// Aim for roughly 5-8 labels
					const interval = Math.ceil(rangeMHz / 6);
					this.chart.options.axisX2.interval = interval;
				} else {
					console.warn("Frequency bounds not valid, using defaults");
					this.chart.options.axisX2.minimum = -1;
					this.chart.options.axisX2.maximum = 1;
					this.chart.options.axisX2.interval = 0.5;
				}
			}

			// Only render if the chart is properly initialized and has valid data
			if (dataPoints.length > 0) {
				this.chart.render();
			}
		} catch (error) {
			console.warn("Failed to render periodogram chart:", error);
		}
	}

	/**
	 * Set CSS custom properties for margins
	 */
	setCSSMarginProperties() {
		document.documentElement.style.setProperty(
			"--plots-left-margin",
			`${PLOTS_LEFT_MARGIN - CANVASJS_LEFT_MARGIN}px`,
		);
		document.documentElement.style.setProperty(
			"--plots-right-margin",
			`${PLOTS_RIGHT_MARGIN - CANVASJS_RIGHT_MARGIN}px`,
		);
	}

	/**
	 * Cleanup resources
	 */
	destroy() {
		if (this.chart) {
			this.chart = null;
		}
	}
}

// Make the class globally available
window.PeriodogramChart = PeriodogramChart;
