/**
 * Waterfall Visualization Components Index
 * Loads all waterfall components and handles initialization
 */

// Import constants first (used by other components)
import "./constants.js";

// Import all waterfall components in dependency order
import "./WaterfallSliceCache.js";
import "./WaterfallSliceLoader.js";
import "./WaterfallRenderer.js";
import "./PeriodogramChart.js";
import "./WaterfallControls.js";
import "./WaterfallVisualization.js";

// Auto-initialize when DOM is ready
document.addEventListener("DOMContentLoaded", () => {
	// Get the capture UUID from the data attribute
	const container = document.querySelector("[data-capture-uuid]");
	const captureUuid = container?.dataset.captureUuid;

	if (captureUuid) {
		const waterfallViz = new WaterfallVisualization(captureUuid);
		waterfallViz.initialize();
	} else {
		console.error("No capture UUID found for waterfall initialization");
	}
});
