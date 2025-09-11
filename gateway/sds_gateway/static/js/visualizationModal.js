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
			if (e.target.classList.contains("visualization-select-btn")) {
				const visualizationType = e.target.dataset.visualization;
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
		if (!this.visualizationCompatibility || !this.currentCaptureType) return;

		// Get all visualization option cards
		const visualizationCards = this.modal.querySelectorAll(
			".visualization-option",
		);

		for (const card of visualizationCards) {
			const vizType = card.dataset.visualization;
			const config = this.visualizationCompatibility[vizType];

			if (config?.supported_capture_types.includes(this.currentCaptureType)) {
				// Show this visualization option
				card.style.display = "block";
				const button = card.querySelector(".visualization-select-btn");
				if (button) {
					button.disabled = false;
					button.classList.remove("disabled");
				}
			} else {
				// Hide this visualization option
				card.style.display = "none";
			}
		}

		// Check if any visualizations are available
		const visibleCards = this.modal.querySelectorAll(
			'.visualization-option[style*="display: block"]',
		);
		if (visibleCards.length === 0) {
			// Show no visualizations available message
			const modalBody = this.modal.querySelector(".modal-body .row");
			modalBody.innerHTML = `
                <div class="col-12">
                    <div class="text-center py-4">
                        <i class="bi bi-exclamation-triangle text-warning display-4"></i>
                        <h5 class="mt-3">No Visualizations Available</h5>
                        <p class="mt-2 text-muted">
                            This capture type (${this.currentCaptureType}) does not support any visualizations.
                        </p>
                        <div class="mt-3">
                            <small class="text-muted">
                                <strong>Supported capture types:</strong><br>
                                ${Object.values(this.visualizationCompatibility)
																	.map((config) =>
																		config.supported_capture_types.join(", "),
																	)
																	.filter(
																		(types, index, arr) =>
																			arr.indexOf(types) === index,
																	)
																	.join(", ")}
                            </small>
                        </div>
                    </div>
                </div>
            `;
		}
	}

	/**
	 * Create HTML for a visualization option
	 */
	createVisualizationOption(vizType, config) {
		return `
            <div class="col-md-6 mb-3">
                <div class="card h-100 visualization-option" data-visualization="${vizType}">
                    <div class="card-body text-center">
                        <div class="mb-3">
                            <i class="bi ${config.icon} display-4 text-${config.color}"></i>
                        </div>
                        <h5 class="card-title">${this.capitalizeFirst(vizType)}</h5>
                        <p class="card-text text-muted">
                            ${config.description}
                        </p>
                        <div class="supported-types">
                            <small class="text-muted">
                                <strong>Supported:</strong> ${config.supported_capture_types.map((t) => t.toUpperCase()).join(", ")}
                            </small>
                        </div>
                    </div>
                    <div class="card-footer bg-transparent">
                        <button type="button"
                                class="btn btn-${config.color} w-100 visualization-select-btn"
                                data-visualization="${vizType}">
                            <i class="bi bi-arrow-right me-2"></i>Open ${this.capitalizeFirst(vizType)}
                        </button>
                    </div>
                </div>
            </div>
        `;
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
