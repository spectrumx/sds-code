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
				card.classList.add("d-block");
				const button = card.querySelector(".visualization-select-btn");
				if (button) {
					button.disabled = false;
					button.classList.remove("disabled");
				}
				visibleCount++;
			} else {
				// Hide this visualization option
				card.classList.remove("d-block");
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

		let html = '<div class="processing-status-grid">';
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
	createStatusCard(_type, data, title) {
		if (!data) {
			return `
                <div class="processing-status-card">
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
            <div class="processing-status-card">
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
		window.open(url, "_blank");

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
