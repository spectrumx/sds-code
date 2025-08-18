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
		this.scaleMin = DEFAULT_SCALE_MIN;
		this.scaleMax = DEFAULT_SCALE_MAX;

		// Constants for alignment from shared constants file
		this.PLOTS_LEFT_MARGIN = PLOTS_LEFT_MARGIN;
		this.PLOTS_RIGHT_MARGIN = PLOTS_RIGHT_MARGIN;
		this.CANVASJS_LEFT_MARGIN = CANVASJS_LEFT_MARGIN;
		this.CANVASJS_RIGHT_MARGIN = CANVASJS_RIGHT_MARGIN;
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
				title: {}, // Remove title for cleaner look
				axisX: {
					// Hide axisX and remove margin to reduce space between periodogram and waterfall
					tickLength: 0,
					labelFontSize: 0,
					labelPlacement: "inside",
					lineThickness: 0,
					margin: 0,
				},
				axisX2: {
					interval: 0.1, // Smaller interval for MHz display
					title: "Frequency (MHz)",
					titlePadding: 15,
					titleFontSize: 16,
					titleFontWeight: "bold",
					labelFontWeight: "bold",
					labelAngle: 90,
					// Set reasonable default bounds
					minimum: -1,
					maximum: 1,
					// Add grid lines for better readability
					gridThickness: 1,
					gridColor: "#e9ecef",
				},
				axisY: {
					interval: 20,
					gridThickness: 1,
					gridColor: "#e9ecef",
					minimum: this.scaleMin,
					maximum: this.scaleMax,
					viewportMinimum: this.scaleMin,
					viewportMaximum: this.scaleMax,
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
			this.scaleMin = scaleMin;
			this.scaleMax = scaleMax;

			// Update the y-axis bounds
			this.chart.options.axisY.minimum = this.scaleMin;
			this.chart.options.axisY.maximum = this.scaleMax;
			this.chart.options.axisY.viewportMinimum = this.scaleMin;
			this.chart.options.axisY.viewportMaximum = this.scaleMax;
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

			// Additional safety check for valid data
			if (!dataArray.every((val) => Number.isFinite(val))) {
				console.warn(
					"Invalid data values detected, skipping periodogram render",
				);
				return;
			}

			// Create data points for the chart - convert frequencies to MHz for better display
			const dataPoints = dataArray
				.map((power, index) => {
					const frequency =
						(index - dataArray.length / 2) *
						(currentSlice.sample_rate / dataArray.length);
					// Convert to MHz to avoid extremely large numbers that could crash CanvasJS
					const freqMHz = frequency / 1000000;

					// Validate frequency value to prevent CanvasJS crashes
					if (!Number.isFinite(freqMHz) || Math.abs(freqMHz) > 10000) {
						console.warn(
							`Invalid frequency value: ${freqMHz}, skipping data point`,
						);
						return null;
					}

					// Validate power value to prevent CanvasJS crashes
					if (!Number.isFinite(power) || Math.abs(power) > 1000) {
						console.warn(`Invalid power value: ${power}, skipping data point`);
						return null;
					}

					return { x: freqMHz, y: power };
				})
				.filter((point) => point !== null); // Remove invalid points

			// Check if we have any valid data points
			if (dataPoints.length === 0) {
				console.warn(
					"No valid data points after filtering, skipping periodogram render",
				);
				return;
			}

			// Update the chart with proper frequency bounds for alignment
			this.chart.options.data[0].dataPoints = dataPoints;

			// Set frequency bounds to match waterfall plot alignment
			// Add validation to prevent invalid bounds that could cause infinite loops
			if (
				dataPoints.length > 0 &&
				currentSlice.sample_rate &&
				Number.isFinite(currentSlice.sample_rate)
			) {
				const freqStep = currentSlice.sample_rate / dataArray.length;
				const centerFreq = currentSlice.center_frequency || 0;
				const minFreq = centerFreq - (dataArray.length / 2) * freqStep;
				const maxFreq = centerFreq + (dataArray.length / 2) * freqStep;

				// Validate frequency bounds to prevent CanvasJS issues
				// Convert to MHz and add reasonable bounds checking
				const minFreqMHz = minFreq / 1000000;
				const maxFreqMHz = maxFreq / 1000000;

				if (
					Number.isFinite(minFreqMHz) &&
					Number.isFinite(maxFreqMHz) &&
					minFreqMHz < maxFreqMHz &&
					Math.abs(minFreqMHz) < 10000 && // Reasonable bounds: ±10 GHz
					Math.abs(maxFreqMHz) < 10000
				) {
					this.chart.options.axisX2.minimum = minFreqMHz;
					this.chart.options.axisX2.maximum = maxFreqMHz;
				} else {
					console.warn(
						"Frequency bounds out of reasonable range, using defaults",
					);
					// Use reasonable default bounds
					this.chart.options.axisX2.minimum = -1;
					this.chart.options.axisX2.maximum = 1;
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
	 * Set CSS custom properties for margins to eliminate duplication
	 */
	setCSSMarginProperties() {
		// Set CSS custom properties on the document root to eliminate margin value duplication
		document.documentElement.style.setProperty(
			"--plots-left-margin",
			`${this.PLOTS_LEFT_MARGIN - this.CANVASJS_LEFT_MARGIN}px`,
		);
		document.documentElement.style.setProperty(
			"--plots-right-margin",
			`${this.PLOTS_RIGHT_MARGIN - this.CANVASJS_RIGHT_MARGIN}px`,
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
