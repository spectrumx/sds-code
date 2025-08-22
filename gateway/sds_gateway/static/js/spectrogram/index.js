/**
 * Spectrogram Visualization Components Index
 * Loads all spectrogram components and handles initialization
 */

// Import constants first (used by other components)
import "./constants.js";

// Import all spectrogram components in dependency order
import "./SpectrogramControls.js";
import "./SpectrogramRenderer.js";
import "./SpectrogramVisualization.js";

// Auto-initialize when DOM is ready
document.addEventListener("DOMContentLoaded", async () => {
	// Get the capture UUID from the data attribute
	const container = document.querySelector("[data-capture-uuid]");
	const captureUuid = container?.dataset.captureUuid;

	if (captureUuid) {
		const spectrogramViz = new SpectrogramVisualization(captureUuid);
		await spectrogramViz.initialize();
	} else {
		console.error("No capture UUID found for spectrogram initialization");
	}
});
