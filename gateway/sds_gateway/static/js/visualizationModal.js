/**
 * Visualization Modal Component
 * Handles the visualization selection modal for captures
 */
class VisualizationModal {
	constructor() {
		this.modal = document.getElementById("visualization-modal");
		this.currentCaptureUuid = null;
		this.currentCaptureType = null;

		// Get visualization compatibility data from Django template context
		this.visualizationCompatibility =
			this.getVisualizationCompatibilityFromContext();

		this.init();
	}

	/**
	 * Open the visualization modal with capture data
	 */
	openWithCaptureData(captureUuid, captureType) {
		this.currentCaptureUuid = captureUuid;
		this.currentCaptureType = captureType;

		// Set the capture type on the modal for CSS-based filtering
		this.modal.setAttribute("data-current-capture-type", captureType);

		// Filter visualizations based on current capture type
		this.filterVisualizationOptions();

		// Open the modal
		let visualizationModal = bootstrap.Modal.getInstance(this.modal);
		if (!visualizationModal) {
			visualizationModal = new bootstrap.Modal(this.modal);
		}
		visualizationModal.show();
	}

	init() {
		if (!this.modal) {
			console.error("Visualization modal not found");
			return;
		}

		this.setupEventListeners();
	}

	setupEventListeners() {
		// Handle visualization selection buttons
		this.modal.addEventListener("click", (e) => {
			const button = e.target.closest(".visualization-select-btn");
			if (button) {
				const visualizationType = button.dataset.visualization;
				this.openVisualization(visualizationType);
			}
		});

		// Handle modal hide event to clean up
		this.modal.addEventListener("hidden.bs.modal", () => {
			// Clear the stored capture data
			this.currentCaptureUuid = null;
			this.currentCaptureType = null;

			// Remove any lingering modal backdrops
			const backdrops = Array.from(
				document.querySelectorAll(".modal-backdrop"),
			);
			for (const backdrop of backdrops) {
				if (backdrop.parentNode) {
					backdrop.parentNode.removeChild(backdrop);
				}
			}

			// Remove modal-open class from body if no other modals are open
			if (document.querySelectorAll(".modal.show").length === 0) {
				document.body.classList.remove("modal-open");
				document.body.style.paddingRight = "";
			}
		});
	}

	/**
	 * Get visualization compatibility data from Django template context
	 */
	getVisualizationCompatibilityFromContext() {
		// Look for the data in a script tag or data attribute
		const contextScript = document.querySelector(
			"script[data-visualization-context]",
		);
		if (contextScript) {
			try {
				return JSON.parse(contextScript.dataset.visualizationContext);
			} catch (e) {
				console.error("Failed to parse visualization context:", e);
			}
		}

		// Fallback: try to get from window object if set by Django
		if (window.visualizationCompatibility) {
			return window.visualizationCompatibility;
		}

		console.warn("No visualization compatibility data found in context");
		return {};
	}

	/**
	 * Filter visualization options based on current capture type (works with Django-rendered content)
	 */
	filterVisualizationOptions() {
		if (!this.currentCaptureType) return;

		// Get all visualization option cards
		const visualizationCards = this.modal.querySelectorAll(
			".visualization-option",
		);

		let visibleCount = 0;

		for (const card of visualizationCards) {
			const supportedTypes = card.dataset.supportedTypes;
			const isSupported = supportedTypes
				?.split(",")
				.includes(this.currentCaptureType);

			if (isSupported) {
				// Show this visualization option
				card.classList.remove("d-none");
				visibleCount++;
			} else {
				// Hide this visualization option
				card.classList.add("d-none");
			}
		}

		// Show/hide the no visualizations message
		this.toggleNoVisualizationsMessage(visibleCount === 0);
	}

	/**
	 * Show or hide the no visualizations available message
	 */
	toggleNoVisualizationsMessage(show) {
		const noVizMessage = this.modal.querySelector(".no-visualizations-message");

		if (show) {
			noVizMessage.classList.remove("d-none");
		} else if (noVizMessage) {
			noVizMessage.classList.add("d-none");
		}
	}

	/**
	 * Capitalize first letter of a string
	 */
	capitalizeFirst(str) {
		return str.charAt(0).toUpperCase() + str.slice(1);
	}

	/**
	 * Open the selected visualization
	 */
	openVisualization(visualizationType) {
		if (!this.currentCaptureUuid || !this.visualizationCompatibility) {
			console.error("Missing required data:", {
				currentCaptureUuid: this.currentCaptureUuid,
				visualizationCompatibility: this.visualizationCompatibility,
			});
			return;
		}

		const config = this.visualizationCompatibility[visualizationType];
		if (!config) {
			console.error(
				"No config found for visualization type:",
				visualizationType,
			);
			return;
		}

		// Build URL from the pattern
		const url = config.url_pattern.replace(
			"{capture_uuid}",
			this.currentCaptureUuid,
		);
		window.location.href = url;

		// Close the modal
		const modal = bootstrap.Modal.getInstance(this.modal);
		if (modal) {
			modal.hide();
		}
	}

	/**
	 * Get CSRF token from the page
	 */
	getCSRFToken() {
		const tokenElement = document.querySelector("[name=csrfmiddlewaretoken]");
		return tokenElement ? tokenElement.value : "";
	}
}

// Export for use in other modules
if (typeof module !== "undefined" && module.exports) {
	module.exports = VisualizationModal;
} else {
	window.VisualizationModal = VisualizationModal;
}
