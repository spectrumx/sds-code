/**
 * WaterfallOverview Class
 * Displays a compact overview of the entire waterfall dataset
 */

import { WaterfallBase } from "./WaterfallBase.js";
import { DEFAULT_COLOR_MAP } from "./constants.js";

class WaterfallOverview {
	constructor(canvasId) {
		this.canvasId = canvasId;
		this.canvas = null;
		this.ctx = null;

		// Data state
		this.overviewData = [];
		this.totalRows = 0;
		this.scaleMin = null;
		this.scaleMax = null;
		this.colorMap = DEFAULT_COLOR_MAP;

		// Canvas dimensions
		this.canvasWidth = 120;
		this.canvasHeight = 400;
		this.margin = 2;

		// Interaction state
		this.hoveredRow = null;
		this.tooltip = null;

		// Bind methods
		this.handleCanvasMouseMove = this.handleCanvasMouseMove.bind(this);
		this.handleCanvasMouseLeave = this.handleCanvasMouseLeave.bind(this);
		this.handleCanvasClick = this.handleCanvasClick.bind(this);
	}

	/**
	 * Initialize the overview component
	 */
	initialize() {
		this.canvas = document.getElementById(this.canvasId);
		if (!this.canvas) {
			throw new Error(`Overview canvas with id '${this.canvasId}' not found`);
		}

		this.ctx = this.canvas.getContext("2d");
		this.tooltip = document.getElementById("overviewTooltip");

		// Set canvas size
		this.canvas.width = this.canvasWidth;
		this.canvas.height = this.canvasHeight;

		// Set up event listeners
		this.setupEventListeners();
	}

	/**
	 * Set up event listeners for canvas interactions
	 */
	setupEventListeners() {
		if (this.canvas) {
			this.canvas.addEventListener("mousemove", this.handleCanvasMouseMove);
			this.canvas.addEventListener("mouseleave", this.handleCanvasMouseLeave);
			this.canvas.addEventListener("click", this.handleCanvasClick);
		}
	}

	/**
	 * Load and render overview data
	 */
	async loadOverviewData(captureUuid) {
		try {
			// First check if low-res waterfall data is available
			const statusResponse = await fetch(
				`/api/latest/assets/captures/${captureUuid}/post_processing_status/`,
			);
			if (!statusResponse.ok) {
				throw new Error(
					`Failed to get post-processing status: ${statusResponse.status}`,
				);
			}

			const statusData = await statusResponse.json();
			const lowResData = statusData.post_processed_data.find(
				(data) =>
					data.processing_type === "waterfall_low_res" &&
					data.processing_status === "completed",
			);

			if (!lowResData) {
				console.log("No low-res waterfall data found");
				return false;
			}

			// Get the low-res waterfall data
			const dataResponse = await fetch(
				`/api/latest/assets/captures/${captureUuid}/download_post_processed_data/?processing_type=waterfall_low_res`,
			);

			if (!dataResponse.ok) {
				throw new Error(
					`Failed to download low-res waterfall data: ${dataResponse.status}`,
				);
			}

			const overviewJson = await dataResponse.json();
			this.overviewData = overviewJson;
			this.totalRows = overviewJson.length;

			// Calculate power bounds from overview data
			this.calculatePowerBounds();

			// Show the canvas
			this.canvas.style.display = "block";

			// Render the overview
			this.render();

			return true;
		} catch (error) {
			console.error("Failed to load overview data:", error);
			return false;
		}
	}

	/**
	 * Calculate power bounds from overview data
	 */
	calculatePowerBounds() {
		if (this.overviewData.length === 0) {
			this.scaleMin = -130;
			this.scaleMax = 0;
			return;
		}

		// Parse all data first
		const parsedDataArray = [];
		for (const row of this.overviewData) {
			if (row.data) {
				const parsedData = WaterfallBase.parseWaterfallData(row.data);
				if (parsedData && parsedData.length > 0) {
					parsedDataArray.push(parsedData);
				}
			}
		}

		// Use base class method to calculate bounds
		const bounds = WaterfallBase.calculatePowerBounds(parsedDataArray);
		this.scaleMin = bounds.min;
		this.scaleMax = bounds.max;
	}

	/**
	 * Render the overview
	 */
	render() {
		if (!this.overviewData || this.overviewData.length === 0) {
			return;
		}

		// Clear canvas
		this.ctx.clearRect(0, 0, this.canvasWidth, this.canvasHeight);

		// Calculate row height
		const plotHeight = this.canvasHeight - this.margin * 2;
		const rowHeight = plotHeight / this.totalRows;

		// Render each row
		for (let i = 0; i < this.overviewData.length; i++) {
			const row = this.overviewData[i];
			if (!row.data) continue;

			const parsedData = this.parseWaterfallData(row.data);
			if (!parsedData || parsedData.length === 0) continue;

			// Calculate row position
			const y = this.margin + i * rowHeight;

			// Render the row as a horizontal line
			this.renderRow(parsedData, y, rowHeight);
		}
	}

	/**
	 * Render a single row of data
	 */
	renderRow(data, y, rowHeight) {
		const plotWidth = this.canvasWidth - this.margin * 2;

		// Create gradient for this row
		const gradient = this.ctx.createLinearGradient(
			this.margin,
			y,
			this.margin + plotWidth,
			y,
		);

		// Add color stops based on data values
		for (let i = 0; i < data.length; i++) {
			const value = data[i];
			const normalizedValue = WaterfallBase.normalizeValue(
				value,
				this.scaleMin,
				this.scaleMax,
			);
			const color = WaterfallBase.getColorForValue(
				normalizedValue,
				this.colorMap,
			);
			const offset = i / (data.length - 1);
			gradient.addColorStop(offset, color);
		}

		// Draw the row
		this.ctx.fillStyle = gradient;
		this.ctx.fillRect(this.margin, y, plotWidth, rowHeight);
	}

	/**
	 * Handle canvas mouse move for hover effects
	 */
	handleCanvasMouseMove(event) {
		if (!this.canvas) return;

		const rect = this.canvas.getBoundingClientRect();
		const y = event.clientY - rect.top;

		// Calculate which row is being hovered
		const plotHeight = this.canvasHeight - this.margin * 2;
		const rowHeight = plotHeight / this.totalRows;
		const adjustedY = y - this.margin;

		if (adjustedY < 0 || adjustedY > plotHeight) {
			this.hoveredRow = null;
			this.hideTooltip();
			return;
		}

		const hoveredRowIndex = Math.floor(adjustedY / rowHeight);

		if (hoveredRowIndex >= 0 && hoveredRowIndex < this.totalRows) {
			this.hoveredRow = hoveredRowIndex;
			this.showTooltip(event, hoveredRowIndex);
		} else {
			this.hoveredRow = null;
			this.hideTooltip();
		}
	}

	/**
	 * Handle canvas mouse leave
	 */
	handleCanvasMouseLeave() {
		this.hoveredRow = null;
		this.hideTooltip();
	}

	/**
	 * Handle canvas click for navigation
	 */
	handleCanvasClick() {
		if (this.hoveredRow !== null) {
			// Emit event for main waterfall to navigate to this row
			const clickEvent = new CustomEvent("overview:rowClicked", {
				detail: { rowIndex: this.hoveredRow },
			});
			document.dispatchEvent(clickEvent);
		}
	}

	/**
	 * Show tooltip with time information
	 */
	showTooltip(event, rowIndex) {
		if (!this.tooltip || rowIndex >= this.overviewData.length) return;

		const row = this.overviewData[rowIndex];
		const timeElement = this.tooltip.querySelector(".tooltip-time");
		const sliceElement = this.tooltip.querySelector(".tooltip-slice");

		if (timeElement && sliceElement) {
			// Format timestamp
			const timestamp = row.timestamp || "Unknown time";
			const formattedTime = WaterfallBase.formatTimestamp(timestamp);

			// Get slice information
			const sliceInfo = row.custom_fields || {};
			const slicesCombined = sliceInfo.slices_combined || 1;
			const sliceIndices = sliceInfo.slice_indices || [];

			timeElement.textContent = formattedTime;
			sliceElement.textContent = `Slices ${sliceIndices[0] || 0}-${sliceIndices[sliceIndices.length - 1] || 0} (${slicesCombined} combined)`;

			// Position tooltip
			const rect = this.canvas.getBoundingClientRect();
			const tooltipRect = this.tooltip.getBoundingClientRect();

			let left = event.clientX - rect.left - tooltipRect.width / 2;
			let top = event.clientY - rect.top - tooltipRect.height - 10;

			// Adjust if tooltip would go off screen
			if (left < 0) left = 0;
			if (left + tooltipRect.width > rect.width) {
				left = rect.width - tooltipRect.width;
			}
			if (top < 0) {
				top = event.clientY - rect.top + 10;
			}

			this.tooltip.style.left = `${left}px`;
			this.tooltip.style.top = `${top}px`;
			this.tooltip.classList.remove("d-none");
		}
	}

	/**
	 * Hide tooltip
	 */
	hideTooltip() {
		if (this.tooltip) {
			this.tooltip.classList.add("d-none");
		}
	}

	/**
	 * Update color map
	 */
	updateColorMap(colorMap) {
		this.colorMap = colorMap;
		this.render();
	}

	/**
	 * Cleanup resources
	 */
	destroy() {
		if (this.canvas) {
			this.canvas.removeEventListener("mousemove", this.handleCanvasMouseMove);
			this.canvas.removeEventListener(
				"mouseleave",
				this.handleCanvasMouseLeave,
			);
			this.canvas.removeEventListener("click", this.handleCanvasClick);
		}

		this.canvas = null;
		this.ctx = null;
		this.tooltip = null;
	}
}

// Make the class globally available
window.WaterfallOverview = WaterfallOverview;
