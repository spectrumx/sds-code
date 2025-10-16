/**
 * Details Action Manager
 * Handles all details-related actions and modal management
 */
class DetailsActionManager {
	/**
	 * Initialize details action manager
	 * @param {Object} config - Configuration object
	 */
	constructor(config) {
		this.permissions = config.permissions;
		this.initializeEventListeners();
	}

	/**
	 * Initialize event listeners
	 */
	initializeEventListeners() {
		// Initialize details buttons for datasets
		this.initializeDatasetDetailsButtons();

		// Initialize details buttons for captures
		this.initializeCaptureDetailsButtons();

		// Initialize modal event handlers
		this.initializeModalEventHandlers();
	}

	/**
	 * Initialize dataset details buttons
	 */
	initializeDatasetDetailsButtons() {
		const detailsButtons = document.querySelectorAll(".dataset-details-btn");

		for (const button of detailsButtons) {
			// Prevent duplicate event listener attachment
			if (button.dataset.detailsSetup === "true") {
				continue;
			}
			button.dataset.detailsSetup = "true";

			button.addEventListener("click", (e) => {
				e.preventDefault();
				e.stopPropagation();

				const datasetUuid = button.getAttribute("data-dataset-uuid");
				this.handleDatasetDetails(datasetUuid);
			});
		}
	}

	/**
	 * Initialize capture details buttons
	 */
	initializeCaptureDetailsButtons() {
		const detailsButtons = document.querySelectorAll(".capture-details-btn");

		for (const button of detailsButtons) {
			// Prevent duplicate event listener attachment
			if (button.dataset.detailsSetup === "true") {
				continue;
			}
			button.dataset.detailsSetup = "true";

			button.addEventListener("click", (e) => {
				e.preventDefault();
				e.stopPropagation();

				const captureUuid =
					button.getAttribute("data-capture-uuid") ||
					button.getAttribute("data-uuid");

				// Skip if no valid UUID
				if (
					!captureUuid ||
					captureUuid === "null" ||
					captureUuid === "undefined"
				) {
					console.warn(
						"No valid capture UUID found for details button:",
						button,
					);
					return;
				}

				this.handleCaptureDetails(captureUuid);
			});
		}
	}

	/**
	 * Initialize modal event handlers
	 */
	initializeModalEventHandlers() {
		// Handle modal show events
		document.addEventListener("show.bs.modal", (e) => {
			const modal = e.target;
			if (modal.id === "datasetDetailsModal") {
				this.handleDatasetDetailsModalShow(modal, e);
			}
		});
	}

	/**
	 * Handle dataset details
	 * @param {string} datasetUuid - Dataset UUID
	 */
	async handleDatasetDetails(datasetUuid) {
		try {
			// Show loading state
			this.showModalLoading("datasetDetailsModal");

			// Fetch dataset details
			const datasetData = await window.APIClient.get(
				`/users/dataset-details/?dataset_uuid=${datasetUuid}`,
			);

			// Populate modal with data
			this.populateDatasetDetailsModal(datasetData);

			// Show modal
			this.openModal("datasetDetailsModal");
		} catch (error) {
			console.error("Error loading dataset details:", error);
			this.showModalError(
				"datasetDetailsModal",
				"Failed to load dataset details",
			);
		}
	}

	/**
	 * Handle capture details
	 * @param {string} captureUuid - Capture UUID
	 */
	async handleCaptureDetails(captureUuid) {
		try {
			// Show loading state
			this.showModalLoading("captureDetailsModal");

			// Fetch capture details
			const captureData = await window.APIClient.get(
				`/users/capture-details/?capture_uuid=${captureUuid}`,
			);

			// Populate modal with data
			this.populateCaptureDetailsModal(captureData);

			// Show modal
			this.openModal("captureDetailsModal");
		} catch (error) {
			console.error("Error loading capture details:", error);
			this.showModalError(
				"captureDetailsModal",
				"Failed to load capture details",
			);
		}
	}

	/**
	 * Populate dataset details modal
	 * @param {Object} datasetData - Dataset data
	 * @param {Object} statistics - Dataset statistics
	 * @param {Object} tree - File tree data
	 */
	populateDatasetDetailsModal(datasetData, statistics, tree) {
		const modal = document.getElementById("datasetDetailsModal");
		if (!modal) return;

		// Clear loading state and restore original modal content
		this.clearModalLoading("datasetDetailsModal");

		// Update basic information using the correct selectors from the template
		this.updateElementText(
			modal,
			".dataset-details-name",
			datasetData.name || "Untitled Dataset",
		);
		this.updateElementText(
			modal,
			".dataset-details-description",
			datasetData.description || "No description provided",
		);
		this.updateElementText(
			modal,
			".dataset-details-status",
			datasetData.status || "Unknown",
		);
		this.updateElementText(
			modal,
			".dataset-details-created",
			this.formatDate(datasetData.created_at),
		);
		this.updateElementText(
			modal,
			".dataset-details-updated",
			this.formatDate(datasetData.updated_at),
		);

		// Set up UUID copy functionality
		this.setupUuidCopyButton(modal, datasetData.uuid);

		// Update authors
		this.updateAuthors(modal, datasetData.authors || []);

		// Update statistics
		if (statistics) {
			this.updateElementText(
				modal,
				"#total-files-count",
				statistics.total_files || 0,
			);
			this.updateElementText(
				modal,
				"#captures-count",
				statistics.captures || 0,
			);
			this.updateElementText(
				modal,
				"#artifacts-count",
				statistics.artifacts || 0,
			);
			this.updateElementText(
				modal,
				"#total-size",
				this.formatFileSize(statistics.total_size || 0),
			);
		}

		// Update file tree (if tree container exists)
		this.updateFileTree(modal, tree);

		// Update action buttons based on permissions
		this.updateActionButtons(modal, datasetData);
	}

	/**
	 * Populate capture details modal
	 * @param {Object} captureData - Capture data
	 */
	populateCaptureDetailsModal(captureData) {
		const modal = document.getElementById("captureDetailsModal");
		if (!modal) return;

		// Update basic information
		this.updateElementText(
			modal,
			"#capture-name",
			captureData.name || "Untitled Capture",
		);
		this.updateElementText(
			modal,
			"#capture-type",
			captureData.type || "Unknown",
		);
		this.updateElementText(
			modal,
			"#capture-directory",
			captureData.directory || "Unknown",
		);
		this.updateElementText(
			modal,
			"#capture-channel",
			captureData.channel || "-",
		);
		this.updateElementText(
			modal,
			"#capture-scan-group",
			captureData.scan_group || "-",
		);
		this.updateElementText(
			modal,
			"#capture-created-at",
			this.formatDate(captureData.created_at),
		);
		this.updateElementText(
			modal,
			"#capture-updated-at",
			this.formatDate(captureData.updated_at),
		);

		// Update owner information
		this.updateElementText(
			modal,
			"#capture-owner",
			captureData.owner_name || "Unknown",
		);

		// Update technical details
		this.updateTechnicalDetails(modal, captureData);

		// Update action buttons based on permissions
		this.updateCaptureActionButtons(modal, captureData);
	}

	/**
	 * Update element text content
	 * @param {Element} container - Container element
	 * @param {string} selector - Element selector
	 * @param {string} text - Text content
	 */
	updateElementText(container, selector, text) {
		const element = container.querySelector(selector);
		if (element) {
			element.textContent = text;
		}
	}

	/**
	 * Set up UUID copy button functionality
	 * @param {Element} modal - Modal element
	 * @param {string} uuid - Dataset UUID
	 */
	setupUuidCopyButton(modal, uuid) {
		const copyButton = modal.querySelector(".copy-uuid-btn");
		if (!copyButton || !uuid) return;

		// Store UUID in button data attribute
		copyButton.dataset.uuid = uuid;

		// Remove any existing event listeners to prevent duplicates
		copyButton.removeEventListener("click", this.handleUuidCopy);

		// Add click event listener
		copyButton.addEventListener("click", (e) => this.handleUuidCopy(e, uuid));
	}

	/**
	 * Handle UUID copy to clipboard
	 * @param {Event} event - Click event
	 * @param {string} uuid - UUID to copy
	 */
	async handleUuidCopy(event, uuid) {
		event.preventDefault();
		event.stopPropagation();

		try {
			// Copy to clipboard using the modern Clipboard API
			await navigator.clipboard.writeText(uuid);

			// Show success feedback
			this.showCopyFeedback(event.target, "Copied!");
		} catch (error) {
			console.warn("Clipboard API failed, trying fallback method:", error);

			// Fallback for older browsers
			try {
				this.fallbackCopyToClipboard(uuid);
				this.showCopyFeedback(event.target, "Copied!");
			} catch (fallbackError) {
				console.error("Failed to copy UUID:", fallbackError);
				this.showCopyFeedback(event.target, "Copy failed", "error");
			}
		}
	}

	/**
	 * Fallback copy method for older browsers
	 * @param {string} text - Text to copy
	 */
	fallbackCopyToClipboard(text) {
		const textArea = document.createElement("textarea");
		textArea.value = text;
		textArea.style.position = "fixed";
		textArea.style.left = "-999999px";
		textArea.style.top = "-999999px";
		document.body.appendChild(textArea);
		textArea.focus();
		textArea.select();

		try {
			document.execCommand("copy");
		} finally {
			document.body.removeChild(textArea);
		}
	}

	/**
	 * Show copy feedback to user
	 * @param {Element} button - Button element
	 * @param {string} message - Feedback message
	 * @param {string} type - Feedback type ('success' or 'error')
	 */
	showCopyFeedback(button, message, type = "success") {
		// Find the button element (might be the icon inside)
		const copyButton = button.closest(".copy-uuid-btn") || button;

		// Store original tooltip
		const originalTitle = copyButton.getAttribute("title");
		const originalIcon = copyButton.innerHTML;

		// Update button appearance temporarily
		if (type === "success") {
			copyButton.innerHTML = '<i class="bi bi-check text-success"></i>';
			copyButton.setAttribute("title", message);
		} else {
			copyButton.innerHTML = '<i class="bi bi-x text-danger"></i>';
			copyButton.setAttribute("title", message);
		}

		// Reset after 2 seconds
		setTimeout(() => {
			copyButton.innerHTML = originalIcon;
			copyButton.setAttribute("title", originalTitle);

			// Re-initialize tooltip if using Bootstrap tooltips
			if (window.bootstrap && bootstrap.Tooltip) {
				const tooltip = bootstrap.Tooltip.getInstance(copyButton);
				if (tooltip) {
					tooltip.dispose();
				}
				new bootstrap.Tooltip(copyButton);
			}
		}, 2000);
	}

	/**
	 * Update authors section
	 * @param {Element} modal - Modal element
	 * @param {Array} authors - Authors array
	 */
	updateAuthors(modal, authors) {
		const authorsContainer = modal.querySelector(".dataset-details-author");
		if (!authorsContainer) return;

		if (!authors || authors.length === 0) {
			authorsContainer.innerHTML = '<span class="text-muted">No authors specified</span>';
			return;
		}

		const authorsText = authors
			.map((author) => {
				if (typeof author === "string") {
					return author;
				}
				return author.name || author.email || "Unknown Author";
			})
			.join(", ");

		authorsContainer.textContent = authorsText; // textContent auto-escapes
	}

	/**
	 * Update captures table
	 * @param {Element} modal - Modal element
	 * @param {Array} captures - Captures array
	 */
	async updateCapturesTable(modal, captures) {
		const tableBody = modal.querySelector("#dataset-captures-table tbody");
		if (!tableBody) return;

		try {
			const response = await window.APIClient.post("/users/render-html/", {
				template: "users/components/modal_captures_table.html",
				context: { captures: captures }
			});

			if (response.html) {
				tableBody.innerHTML = response.html;
			}
		} catch (error) {
			console.error("Error rendering captures table:", error);
			tableBody.innerHTML = '<tr><td colspan="5" class="text-center text-danger">Error loading captures</td></tr>';
		}
	}

	/**
	 * Update files table
	 * @param {Element} modal - Modal element
	 * @param {Array} files - Files array
	 */
	async updateFilesTable(modal, files) {
		const tableBody = modal.querySelector("#dataset-files-table tbody");
		if (!tableBody) return;

		try {
			const response = await window.APIClient.post("/users/render-html/", {
				template: "users/components/modal_files_table.html",
				context: { files: files }
			});

			if (response.html) {
				tableBody.innerHTML = response.html;
			}
		} catch (error) {
			console.error("Error rendering files table:", error);
			tableBody.innerHTML = '<tr><td colspan="4" class="text-center text-danger">Error loading files</td></tr>';
		}
	}

	/**
	 * Update permissions section
	 * @param {Element} modal - Modal element
	 * @param {Array} permissions - Permissions array
	 */
	async updatePermissionsSection(modal, permissions) {
		const permissionsContainer = modal.querySelector("#dataset-permissions");
		if (!permissionsContainer) return;

		try {
			// Normalize permissions with badge class and display name
			const normalizedPermissions = permissions.map(permission => ({
				...permission,
				badge_class: this.permissions.getPermissionBadgeClass(permission.permission_level),
				display_name: this.permissions.getPermissionDisplayName(permission.permission_level)
			}));

			const response = await window.APIClient.post("/users/render-html/", {
				template: "users/components/modal_permissions.html",
				context: { permissions: normalizedPermissions }
			});

			if (response.html) {
				permissionsContainer.innerHTML = response.html;
			}
		} catch (error) {
			console.error("Error rendering permissions:", error);
			permissionsContainer.innerHTML = '<span class="text-danger">Error loading permissions</span>';
		}
	}

	/**
	 * Update technical details for capture
	 * @param {Element} modal - Modal element
	 * @param {Object} captureData - Capture data
	 */
	async updateTechnicalDetails(modal, captureData) {
		const technicalDetails = modal.querySelector("#capture-technical-details");
		if (!technicalDetails) return;

		const details = [];

		if (captureData.center_frequency_ghz) {
			details.push(`Center Frequency: ${captureData.center_frequency_ghz} GHz`);
		}

		if (captureData.bandwidth_mhz) {
			details.push(`Bandwidth: ${captureData.bandwidth_mhz} MHz`);
		}

		if (captureData.sample_rate_hz) {
			details.push(`Sample Rate: ${captureData.sample_rate_hz} Hz`);
		}

		if (captureData.duration_seconds) {
			details.push(`Duration: ${captureData.duration_seconds} seconds`);
		}

		try {
			const response = await window.APIClient.post("/users/render-html/", {
				template: "users/components/modal_technical_details.html",
				context: { details: details }
			});

			if (response.html) {
				technicalDetails.innerHTML = response.html;
			}
		} catch (error) {
			console.error("Error rendering technical details:", error);
			technicalDetails.innerHTML = '<span class="text-danger">Error loading details</span>';
		}
	}

	/**
	 * Update action buttons for dataset
	 * @param {Element} modal - Modal element
	 * @param {Object} datasetData - Dataset data
	 */
	updateActionButtons(modal, datasetData) {
		// Share button
		const shareButton = modal.querySelector("#share-dataset-btn");
		if (!shareButton) {
			// Continue to next button
		} else if (!this.permissions.canShare()) {
			window.DOMUtils.hide(shareButton, "display-inline-block");
		} else {
			window.DOMUtils.show(shareButton, "display-inline-block");
			shareButton.setAttribute("data-dataset-uuid", datasetData.uuid);
		}

		// Download button
		const downloadButton = modal.querySelector("#download-dataset-btn");
		if (!downloadButton) {
			// Continue to next button
		} else if (!this.permissions.canDownload()) {
			window.DOMUtils.hide(downloadButton, "display-inline-block");
		} else {
			window.DOMUtils.show(downloadButton, "display-inline-block");
			downloadButton.setAttribute("data-dataset-uuid", datasetData.uuid);
			downloadButton.setAttribute("data-dataset-name", datasetData.name);
		}

		// Edit button
		const editButton = modal.querySelector("#edit-dataset-btn");
		if (!editButton) return;

		if (!this.permissions.canEditMetadata()) {
			window.DOMUtils.hide(editButton, "display-inline-block");
		} else {
			window.DOMUtils.show(editButton, "display-inline-block");
			editButton.href = `/users/edit-dataset/${datasetData.uuid}/`;
		}
	}

	/**
	 * Update action buttons for capture
	 * @param {Element} modal - Modal element
	 * @param {Object} captureData - Capture data
	 */
	updateCaptureActionButtons(modal, captureData) {
		// Download button
		const downloadButton = modal.querySelector("#download-capture-btn");
		if (!downloadButton) {
			// Continue to next button
		} else if (!this.permissions.canDownload()) {
			window.DOMUtils.hide(downloadButton, "display-inline-block");
		} else {
			window.DOMUtils.show(downloadButton, "display-inline-block");
			downloadButton.setAttribute("data-capture-uuid", captureData.uuid);
			downloadButton.setAttribute("data-capture-name", captureData.name);
		}

		// Visualize button
		const visualizeButton = modal.querySelector("#visualize-capture-btn");
		if (!visualizeButton) return;

		if (!this.permissions.canView()) {
			window.DOMUtils.hide(visualizeButton, "display-inline-block");
		} else {
			window.DOMUtils.show(visualizeButton, "display-inline-block");
			visualizeButton.setAttribute("data-capture-uuid", captureData.uuid);
		}
	}

	/**
	 * Show modal loading state
	 * @param {string} modalId - Modal ID
	 */
	showModalLoading(modalId) {
		const modal = document.getElementById(modalId);
		if (!modal) return;

		const modalBody = modal.querySelector(".modal-body");
		if (modalBody) {
			// Store original content before showing loading
			if (!modalBody.dataset.originalContent) {
				modalBody.dataset.originalContent = modalBody.innerHTML;
			}

			const loadingHtml = `
				<div class="text-center py-4">
					<div class="spinner-border text-primary" style="width: 3rem; height: 3rem;" role="status">
						<span class="visually-hidden">Loading details...</span>
					</div>
					<p class="mt-3 text-muted">Loading details...</p>
				</div>
			`;
			modalBody.innerHTML = loadingHtml;
		}
	}

	/**
	 * Clear modal loading state and restore original content
	 * @param {string} modalId - Modal ID
	 */
	clearModalLoading(modalId) {
		const modal = document.getElementById(modalId);
		if (!modal) return;

		const modalBody = modal.querySelector(".modal-body");
		if (modalBody?.dataset.originalContent) {
			// Restore original content
			modalBody.innerHTML = modalBody.dataset.originalContent;
			// Clean up the stored content
			delete modalBody.dataset.originalContent;
		}
	}

	/**
	 * Show modal error
	 * @param {string} modalId - Modal ID
	 * @param {string} message - Error message
	 */
	async showModalError(modalId, message) {
		const modal = document.getElementById(modalId);
		if (!modal) return;

		const modalBody = modal.querySelector(".modal-body");
		if (modalBody) {
			try {
				const response = await window.APIClient.post("/users/render-html/", {
					template: "users/components/error_alert.html",
					context: {
						message: message,
						alert_type: "danger",
						icon: "exclamation-triangle"
					}
				});

				if (response.html) {
					modalBody.innerHTML = response.html;
				}
			} catch (error) {
				console.error("Error rendering error message:", error);
				// Fallback
				modalBody.textContent = message;
			}
		}

		// Show modal even with error
		this.openModal(modalId);
	}

	/**
	 * Open modal
	 * @param {string} modalId - Modal ID
	 */
	openModal(modalId) {
		const modal = document.getElementById(modalId);
		if (!modal) return;

		const bootstrapModal = new bootstrap.Modal(modal);
		bootstrapModal.show();
	}

	/**
	 * Close modal
	 * @param {string} modalId - Modal ID
	 */
	closeModal(modalId) {
		const modal = document.getElementById(modalId);
		if (!modal) return;

		const bootstrapModal = bootstrap.Modal.getInstance(modal);
		if (!bootstrapModal) return;

		bootstrapModal.hide();
	}

	/**
	 * Handle dataset details modal show
	 * @param {Element} modal - Modal element
	 * @param {Event} event - Bootstrap modal event
	 */
	handleDatasetDetailsModalShow(modal, event) {
		// Get the triggering element (the element that opened the modal)
		const triggerElement = event.relatedTarget;

		if (!triggerElement) {
			console.warn("No trigger element found for dataset details modal");
			this.showModalError(
				"datasetDetailsModal",
				"Unable to load dataset details",
			);
			return;
		}

		// Extract dataset UUID from the triggering element
		const datasetUuid = triggerElement.getAttribute("data-dataset-uuid");

		if (!datasetUuid) {
			console.warn("No dataset UUID found on trigger element:", triggerElement);
			this.showModalError("datasetDetailsModal", "Dataset UUID not found");
			return;
		}

		// Load dataset details
		this.loadDatasetDetailsForModal(datasetUuid);
	}

	/**
	 * Load dataset details for modal
	 * @param {string} datasetUuid - Dataset UUID
	 */
	async loadDatasetDetailsForModal(datasetUuid) {
		try {
			// Show loading state
			this.showModalLoading("datasetDetailsModal");

			// Fetch dataset details
			const response = await window.APIClient.get(
				`/users/dataset-details/?dataset_uuid=${datasetUuid}`,
			);

			// Extract dataset data from the response
			const datasetData = response.dataset;
			const statistics = response.statistics;
			const tree = response.tree;

			// Populate modal with data
			this.populateDatasetDetailsModal(datasetData, statistics, tree);
		} catch (error) {
			console.error("Error loading dataset details:", error);
			this.showModalError(
				"datasetDetailsModal",
				"Failed to load dataset details",
			);
		}
	}

	/**
	 * Update file tree
	 * @param {Element} modal - Modal element
	 * @param {Object} tree - File tree data
	 */
	async updateFileTree(modal, tree) {
		const tableBody = modal.querySelector("#dataset-file-tree-table tbody");
		if (!tableBody || !tree) return;

		// Build normalized rows for server-side rendering
		const rows = this.buildTreeRows(tree, 0);

		try {
			const response = await window.APIClient.post("/users/render-html/", {
				template: "users/components/modal_file_tree.html",
				context: { rows: rows }
			});

			if (response.html) {
				tableBody.innerHTML = response.html;
			}
		} catch (error) {
			console.error("Error rendering file tree:", error);
			tableBody.innerHTML = '<tr><td colspan="5" class="text-center text-danger">Error loading file tree</td></tr>';
		}
	}

	/**
	 * Build tree rows for server-side rendering
	 * @param {Object} node - Tree node
	 * @param {number} depth - Current depth for indentation
	 * @returns {Array<Object>} Array of row objects for template
	 */
	buildTreeRows(node, depth = 0) {
		const rows = [];

		// Add files in this directory first
		if (node.files && Array.isArray(node.files)) {
			for (const file of node.files) {
				rows.push({
					indent_level: depth,
					indent_range: [...Array(depth).keys()], // For template loop
					icon: "bi-file-earmark",
					icon_color: "text-primary",
					name: file.name,
					type: file.media_type || file.type || "File",
					size: this.formatFileSize(file.size || 0),
					created_at: this.formatDate(file.created_at),
					has_chevron: false
				});
			}
		}

		// Add child directories
		if (node.children && typeof node.children === "object") {
			for (const childNode of Object.values(node.children)) {
				if (childNode.type === "directory") {
					// Add directory row
					rows.push({
						indent_level: depth,
						indent_range: [...Array(depth).keys()], // For template loop
						icon: "bi-folder",
						icon_color: "text-warning",
						name: childNode.name + "/",
						type: "Directory",
						size: this.formatFileSize(childNode.size || 0),
						created_at: this.formatDate(childNode.created_at),
						has_chevron: true
					});

					// Recursively add children
					const childRows = this.buildTreeRows(childNode, depth + 1);
					rows.push(...childRows);
				}
			}
		}

		return rows;
	}

	/**
	 * Format file size for display
	 * @param {number} bytes - File size in bytes
	 * @returns {string} Formatted file size
	 */
	formatFileSize(bytes) {
		if (bytes === 0) return "0 Bytes";

		const k = 1024;
		const sizes = ["Bytes", "KB", "MB", "GB", "TB"];
		const i = Math.floor(Math.log(bytes) / Math.log(k));

		return `${Number.parseFloat((bytes / k ** i).toFixed(2))} ${sizes[i]}`;
	}

	/**
	 * Format date for display
	 * @param {string} dateString - Date string
	 * @returns {string} Formatted date
	 */
	formatDate(dateString) {
		if (!dateString) return "Unknown";

		try {
			const date = new Date(dateString);
			return date.toLocaleDateString("en-US", {
				year: "numeric",
				month: "short",
				day: "numeric",
				hour: "2-digit",
				minute: "2-digit",
			});
		} catch (error) {
			return "Invalid date";
		}
	}

	/**
	 * Initialize details buttons for dynamically loaded content
	 * @param {Element} container - Container element to search within
	 */
	initializeDetailsButtonsForContainer(container) {
		// Initialize dataset details buttons in the container
		const datasetDetailsButtons = container.querySelectorAll(
			".dataset-details-btn",
		);
		for (const button of datasetDetailsButtons) {
			if (!button.dataset.detailsSetup) {
				button.dataset.detailsSetup = "true";
				button.addEventListener("click", (e) => {
					e.preventDefault();
					e.stopPropagation();

					const datasetUuid = button.getAttribute("data-dataset-uuid");
					this.handleDatasetDetails(datasetUuid);
				});
			}
		}

		// Initialize capture details buttons in the container
		const captureDetailsButtons = container.querySelectorAll(
			".capture-details-btn",
		);
		for (const button of captureDetailsButtons) {
			if (!button.dataset.detailsSetup) {
				button.dataset.detailsSetup = "true";
				button.addEventListener("click", (e) => {
					e.preventDefault();
					e.stopPropagation();

					const captureUuid = button.getAttribute("data-capture-uuid");
					this.handleCaptureDetails(captureUuid);
				});
			}
		}
	}

	/**
	 * Cleanup resources
	 */
	cleanup() {
		// Remove event listeners and clean up any resources
		const detailsButtons = document.querySelectorAll(
			".dataset-details-btn, .capture-details-btn",
		);
		for (const button of detailsButtons) {
			button.removeEventListener("click", this.handleDatasetDetails);
			button.removeEventListener("click", this.handleCaptureDetails);
		}
	}
}

// Make class available globally
window.DetailsActionManager = DetailsActionManager;

// Export for ES6 modules (Jest testing)
export { DetailsActionManager };
