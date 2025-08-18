/**
 * Waterfall Renderer
 * Handles canvas drawing, color mapping, and visual rendering
 */

import {
	DEFAULT_COLOR_MAP,
	DEFAULT_SCALE_MAX,
	DEFAULT_SCALE_MIN,
	PLOTS_LEFT_MARGIN,
	PLOTS_RIGHT_MARGIN,
	WATERFALL_BOTTOM_MARGIN,
	WATERFALL_TOP_MARGIN,
	WATERFALL_WINDOW_SIZE,
} from "./constants.js";

class WaterfallRenderer {
	constructor(canvas, overlayCanvas) {
		this.canvas = canvas;
		this.overlayCanvas = overlayCanvas;
		this.ctx = canvas ? canvas.getContext("2d") : null;
		this.overlayCtx = overlayCanvas ? overlayCanvas.getContext("2d") : null;

		// Constants from shared constants file
		this.WATERFALL_WINDOW_SIZE = WATERFALL_WINDOW_SIZE;
		this.TOP_MARGIN = WATERFALL_TOP_MARGIN;
		this.BOTTOM_MARGIN = WATERFALL_BOTTOM_MARGIN;
		this.PLOTS_LEFT_MARGIN = PLOTS_LEFT_MARGIN;
		this.PLOTS_RIGHT_MARGIN = PLOTS_RIGHT_MARGIN;

		// State
		this.colorMap = DEFAULT_COLOR_MAP;
		this.scaleMin = DEFAULT_SCALE_MIN;
		this.scaleMax = DEFAULT_SCALE_MAX;
		this.hoveredSliceIndex = null;
		this.currentSliceIndex = 0;
		this.waterfallWindowStart = 0;
		this.totalSlices = 0;
	}

	/**
	 * Set color map
	 */
	setColorMap(colorMap) {
		this.colorMap = colorMap;
	}

	/**
	 * Set scale bounds
	 */
	setScaleBounds(scaleMin, scaleMax) {
		this.scaleMin = scaleMin;
		this.scaleMax = scaleMax;
	}

	/**
	 * Set current slice index
	 */
	setCurrentSliceIndex(index) {
		this.currentSliceIndex = index;
	}

	/**
	 * Set waterfall window start
	 */
	setWaterfallWindowStart(start) {
		this.waterfallWindowStart = start;
	}

	/**
	 * Set total slices count
	 */
	setTotalSlices(total) {
		this.totalSlices = total;
	}

	/**
	 * Set hovered slice index
	 */
	setHoveredSliceIndex(index) {
		this.hoveredSliceIndex = index;
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

		// Clear overlay when resizing
		this.clearOverlay();
	}

	/**
	 * Render the waterfall plot
	 */
	renderWaterfall(waterfallData, totalSlices) {
		if (!this.ctx || !this.canvas || waterfallData.length === 0) return;

		// Store total slices for overlay updates
		this.totalSlices = totalSlices;

		// Clear canvas
		this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);

		// Calculate dimensions with margins
		const plotHeight =
			this.canvas.height - this.TOP_MARGIN - this.BOTTOM_MARGIN;
		const maxVisibleSlices = Math.min(totalSlices, this.WATERFALL_WINDOW_SIZE);
		const sliceHeight = plotHeight / maxVisibleSlices;

		// Calculate which slices to display
		const startSliceIndex = this.waterfallWindowStart;

		// Draw waterfall slices from bottom to top
		for (let i = 0; i < this.WATERFALL_WINDOW_SIZE; i++) {
			const sliceIndex = startSliceIndex + i;
			if (sliceIndex >= totalSlices) break;

			const slice = waterfallData[sliceIndex];
			if (slice?.data) {
				// Calculate Y position: bottom slice is at bottom margin, top slice is at top margin
				const y = this.BOTTOM_MARGIN + (maxVisibleSlices - 1 - i) * sliceHeight;

				this.drawWaterfallSlice(slice.data, y, sliceHeight, this.canvas.width);
			}
		}

		// Update the overlay with highlights and index legend
		this.updateOverlay();
	}

	/**
	 * Draw a single waterfall slice
	 */
	drawWaterfallSlice(data, y, height, width) {
		if (!this.ctx) return;

		const fftPoints = data.length;
		const plotWidth = width - this.PLOTS_LEFT_MARGIN - this.PLOTS_RIGHT_MARGIN;
		const pointWidth = plotWidth / fftPoints;

		const powerRange = this.scaleMax - this.scaleMin;

		for (let i = 0; i < fftPoints; i++) {
			const power = data[i];

			// Clamp power to the scale range and normalize
			const clampedPower = Math.max(
				this.scaleMin,
				Math.min(this.scaleMax, power),
			);
			const normalizedPower = (clampedPower - this.scaleMin) / powerRange;

			const color = this.getColorForPower(normalizedPower);

			this.ctx.fillStyle = color;
			this.ctx.fillRect(
				this.PLOTS_LEFT_MARGIN + i * pointWidth,
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
					return `rgb(${Math.floor(128 + 127 * t)}, 0, ${Math.floor(255 - 255 * t)})`;
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
					return `rgb(${Math.floor(128 + 127 * t)}, 0, ${Math.floor(255 - 127 * t)})`;
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
	 * Draw highlight box around a slice
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
		const maxVisibleSlices = Math.min(this.WATERFALL_WINDOW_SIZE, 100);
		const y =
			this.BOTTOM_MARGIN + (maxVisibleSlices - 1 - sliceInRange) * sliceHeight;

		// Draw highlight box using consistent margins for alignment
		this.overlayCtx.strokeStyle = strokeStyle;
		this.overlayCtx.lineWidth = lineWidth;
		const plotWidth =
			canvasWidth - this.PLOTS_LEFT_MARGIN - this.PLOTS_RIGHT_MARGIN;
		this.overlayCtx.strokeRect(
			this.PLOTS_LEFT_MARGIN,
			y,
			plotWidth,
			sliceHeight,
		);
	}

	/**
	 * Update the overlay canvas with highlights and index legend
	 */
	updateOverlay() {
		if (!this.overlayCanvas || !this.overlayCtx) return;

		// Get current canvas dimensions
		const plotHeight =
			this.canvas.height - this.TOP_MARGIN - this.BOTTOM_MARGIN;
		const maxVisibleSlices = Math.min(
			this.totalSlices || 100,
			this.WATERFALL_WINDOW_SIZE,
		);
		const sliceHeight = plotHeight / maxVisibleSlices;

		// Calculate slice indices for current window
		const startSliceIndex = this.waterfallWindowStart;
		const endSliceIndex = Math.min(
			this.waterfallWindowStart + this.WATERFALL_WINDOW_SIZE,
			this.totalSlices || 100,
		);

		// Clear and redraw everything on the overlay
		this.clearOverlay();

		// Draw current slice highlight
		this.drawHighlightBox(
			this.currentSliceIndex,
			startSliceIndex,
			endSliceIndex,
			sliceHeight,
			this.canvas.width,
			"#000000", // Black color for current slice
			1,
		);

		// Draw hover highlight if there is one
		if (this.hoveredSliceIndex !== null) {
			this.drawHighlightBox(
				this.hoveredSliceIndex,
				startSliceIndex,
				endSliceIndex,
				sliceHeight,
				this.canvas.width,
				"#808080", // Light grey color for hover
				1,
			);
		}

		// Draw the index legend
		this.updateSliceIndexLegend(
			this.totalSlices || 100,
			maxVisibleSlices,
			sliceHeight,
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
	 * Update the slice index legend on the overlay canvas
	 */
	updateSliceIndexLegend(totalSlices, maxVisibleSlices, sliceHeight) {
		if (!this.overlayCtx || !this.overlayCanvas) return;

		// Clear the left side area for labels using consistent margins
		const labelWidth = this.PLOTS_LEFT_MARGIN;
		this.overlayCtx.fillStyle = "rgba(255, 255, 255, 0.95)";
		this.overlayCtx.fillRect(0, 0, labelWidth, this.overlayCanvas.height);

		// Only draw indices if we have 5 or more rows
		if (maxVisibleSlices >= 5) {
			this.overlayCtx.font = "10px Arial";
			this.overlayCtx.textAlign = "right";
			this.overlayCtx.fillStyle = "#000";

			// Show every 5th index
			for (let i = 0; i < maxVisibleSlices; i++) {
				const sliceIndex = this.waterfallWindowStart + i;
				if (sliceIndex >= totalSlices) break;

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
						this.overlayCtx.fillStyle = "#000"; // Black for current slice
					} else if (sliceIndex === this.hoveredSliceIndex) {
						this.overlayCtx.fillStyle = "#333"; // Dark grey for hovered slice
					} else {
						this.overlayCtx.fillStyle = "#999"; // Light grey for other indices
					}

					this.overlayCtx.fillText(
						String(displayedIndex),
						labelWidth - 5,
						y + 3,
					);
				}
			}
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
	 * Cleanup resources
	 */
	destroy() {
		this.canvas = null;
		this.overlayCanvas = null;
		this.ctx = null;
		this.overlayCtx = null;
	}
}

// Make the class globally available
window.WaterfallRenderer = WaterfallRenderer;
