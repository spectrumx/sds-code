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
		this.loadProcessingStatus();

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
	 * Load processing status for the current capture
	 */
	async loadProcessingStatus() {
		if (!this.currentCaptureUuid) return;

		const statusContainer = this.modal.querySelector(
			"#processing-status-container",
		);

		try {
			const response = await fetch(
				`/api/v1/assets/captures/${this.currentCaptureUuid}/post_processing_status/`,
				{
					headers: {
						"X-CSRFToken": this.getCSRFToken(),
					},
				},
			);

			if (response.ok) {
				const data = await response.json();
				this.displayProcessingStatus(data.post_processed_data, statusContainer);
			} else {
				statusContainer.innerHTML =
					'<p class="text-muted">Unable to load processing status</p>';
			}
		} catch (error) {
			console.error("Error loading processing status:", error);
			statusContainer.innerHTML =
				'<p class="text-muted">Error loading processing status</p>';
		}
	}

	/**
	 * Display processing status for different visualization types
	 */
	displayProcessingStatus(postProcessedData, container) {
		if (!postProcessedData || postProcessedData.length === 0) {
			container.innerHTML =
				'<p class="text-muted">No processing data available</p>';
			return;
		}

		let html = '<div class="row">';
		let hasCompatibleStatus = false;

		// Only show processing status for visualization types compatible with current capture type
		for (const [vizType, config] of Object.entries(
			this.visualizationCompatibility,
		)) {
			if (config.supported_capture_types.includes(this.currentCaptureType)) {
				const vizData = postProcessedData.find(
					(item) => item.processing_type === vizType,
				);
				html += this.createStatusCard(
					vizType,
					vizData,
					this.capitalizeFirst(vizType),
				);
				hasCompatibleStatus = true;
			}
		}

		html += "</div>";

		if (!hasCompatibleStatus) {
			container.innerHTML =
				'<p class="text-muted">No compatible visualizations available for this capture type</p>';
		} else {
			container.innerHTML = html;
		}
	}

	/**
	 * Create a status card for a visualization type
	 */
	createStatusCard(type, data, title) {
		if (!data) {
			return `
                <div class="col-md-6">
                    <div class="card border-secondary">
                        <div class="card-body p-3">
                            <h6 class="card-title">${title}</h6>
                            <span class="badge bg-secondary">Not Started</span>
                        </div>
                    </div>
                </div>
            `;
		}

		let badgeClass = "bg-secondary";
		let statusText = "Unknown";

		switch (data.processing_status) {
			case "pending":
				badgeClass = "bg-warning";
				statusText = "Pending";
				break;
			case "processing":
				badgeClass = "bg-info";
				statusText = "Processing";
				break;
			case "completed":
				badgeClass = "bg-success";
				statusText = "Completed";
				break;
			case "failed":
				badgeClass = "bg-danger";
				statusText = "Failed";
				break;
		}

		let details = "";
		if (data.processing_status === "completed") {
			details = `<small class="text-muted d-block mt-1">Ready to view</small>`;
		} else if (data.processing_status === "failed" && data.processing_error) {
			details = `<small class="text-danger d-block mt-1">${data.processing_error}</small>`;
		}

		return `
            <div class="col-md-6">
                <div class="card">
                    <div class="card-body p-3">
                        <h6 class="card-title">${title}</h6>
                        <span class="badge ${badgeClass}">${statusText}</span>
                        ${details}
                    </div>
                </div>
            </div>
        `;
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
