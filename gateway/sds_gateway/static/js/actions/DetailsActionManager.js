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
				return;
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
			const datasetData = await APIClient.get(
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
			const captureData = await APIClient.get(
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
			HTMLInjectionManager.injectHTML(
				authorsContainer,
				'<span class="text-muted">No authors specified</span>',
			);
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

		HTMLInjectionManager.injectHTML(
			authorsContainer,
			HTMLInjectionManager.escapeHtml(authorsText),
		);
	}

	/**
	 * Update captures table
	 * @param {Element} modal - Modal element
	 * @param {Array} captures - Captures array
	 */
	updateCapturesTable(modal, captures) {
		const tableBody = modal.querySelector("#dataset-captures-table tbody");
		if (!tableBody) return;

		if (captures.length === 0) {
			HTMLInjectionManager.injectHTML(
				tableBody,
				'<tr><td colspan="5" class="text-center text-muted">No captures in dataset</td></tr>',
			);
			return;
		}

		const rows = captures
			.map((capture) => {
				return HTMLInjectionManager.createTableRow(
					capture,
					`
				<tr>
					<td>{{type}}</td>
					<td>{{directory}}</td>
					<td>{{channel}}</td>
					<td>{{scan_group}}</td>
					<td>{{created_at}}</td>
				</tr>
			`,
					{ dateFormat: "en-US" },
				);
			})
			.join("");

		HTMLInjectionManager.injectHTML(tableBody, rows, { escape: false });
	}

	/**
	 * Update files table
	 * @param {Element} modal - Modal element
	 * @param {Array} files - Files array
	 */
	updateFilesTable(modal, files) {
		const tableBody = modal.querySelector("#dataset-files-table tbody");
		if (!tableBody) return;

		if (files.length === 0) {
			HTMLInjectionManager.injectHTML(
				tableBody,
				'<tr><td colspan="4" class="text-center text-muted">No files in dataset</td></tr>',
			);
			return;
		}

		const rows = files
			.map((file) => {
				return HTMLInjectionManager.createTableRow(
					file,
					`
				<tr>
					<td>{{name}}</td>
					<td>{{media_type}}</td>
					<td>{{relative_path}}</td>
					<td>{{size}}</td>
				</tr>
			`,
				);
			})
			.join("");

		HTMLInjectionManager.injectHTML(tableBody, rows, { escape: false });
	}

	/**
	 * Update permissions section
	 * @param {Element} modal - Modal element
	 * @param {Array} permissions - Permissions array
	 */
	updatePermissionsSection(modal, permissions) {
		const permissionsContainer = modal.querySelector("#dataset-permissions");
		if (!permissionsContainer) return;

		if (permissions.length === 0) {
			HTMLInjectionManager.injectHTML(
				permissionsContainer,
				'<span class="text-muted">No shared permissions</span>',
			);
			return;
		}

		const permissionsHtml = permissions
			.map((permission) => {
				const badgeClass = PermissionsManager.getPermissionBadgeClass(
					permission.permission_level,
				);
				const displayName = PermissionsManager.getPermissionDisplayName(
					permission.permission_level,
				);
				const userInfo = permission.user_name
					? `${HTMLInjectionManager.escapeHtml(permission.user_name)} (${HTMLInjectionManager.escapeHtml(permission.user_email)})`
					: HTMLInjectionManager.escapeHtml(permission.user_email);

				return `
				<div class="d-flex justify-content-between align-items-center mb-2">
					<span>${userInfo}</span>
					<span class="badge ${badgeClass}">${displayName}</span>
				</div>
			`;
			})
			.join("");

		HTMLInjectionManager.injectHTML(permissionsContainer, permissionsHtml, {
			escape: false,
		});
	}

	/**
	 * Update technical details for capture
	 * @param {Element} modal - Modal element
	 * @param {Object} captureData - Capture data
	 */
	updateTechnicalDetails(modal, captureData) {
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

		if (details.length === 0) {
			HTMLInjectionManager.injectHTML(
				technicalDetails,
				'<span class="text-muted">No technical details available</span>',
			);
		} else {
			HTMLInjectionManager.injectHTML(
				technicalDetails,
				`<ul class="list-unstyled mb-0">${details.map((detail) => `<li>${HTMLInjectionManager.escapeHtml(detail)}</li>`).join("")}</ul>`,
				{ escape: false },
			);
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
		if (shareButton) {
			if (!this.permissions.canShare()) {
				shareButton.style.display = "none";
			} else {
				shareButton.style.display = "inline-block";
				shareButton.setAttribute("data-dataset-uuid", datasetData.uuid);
			}
		}

		// Download button
		const downloadButton = modal.querySelector("#download-dataset-btn");
		if (downloadButton) {
			if (!this.permissions.canDownload()) {
				downloadButton.style.display = "none";
			} else {
				downloadButton.style.display = "inline-block";
				downloadButton.setAttribute("data-dataset-uuid", datasetData.uuid);
				downloadButton.setAttribute("data-dataset-name", datasetData.name);
			}
		}

		// Edit button
		const editButton = modal.querySelector("#edit-dataset-btn");
		if (editButton) {
			if (!this.permissions.canEditMetadata()) {
				editButton.style.display = "none";
			} else {
				editButton.style.display = "inline-block";
				editButton.href = `/users/edit-dataset/${datasetData.uuid}/`;
			}
		}

		// Delete button
		const deleteButton = modal.querySelector("#delete-dataset-btn");
		if (deleteButton) {
			if (!this.permissions.canDelete()) {
				deleteButton.style.display = "none";
			} else {
				deleteButton.style.display = "inline-block";
				deleteButton.setAttribute("data-dataset-uuid", datasetData.uuid);
			}
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
		if (downloadButton) {
			if (!this.permissions.canDownload()) {
				downloadButton.style.display = "none";
			} else {
				downloadButton.style.display = "inline-block";
				downloadButton.setAttribute("data-capture-uuid", captureData.uuid);
				downloadButton.setAttribute("data-capture-name", captureData.name);
			}
		}

		// Visualize button
		const visualizeButton = modal.querySelector("#visualize-capture-btn");
		if (visualizeButton) {
			if (!this.permissions.canView()) {
				visualizeButton.style.display = "none";
			} else {
				visualizeButton.style.display = "inline-block";
				visualizeButton.setAttribute("data-capture-uuid", captureData.uuid);
			}
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
					${HTMLInjectionManager.createLoadingSpinner("Loading details...", { size: "lg" })}
				</div>
			`;
			HTMLInjectionManager.injectHTML(modalBody, loadingHtml, {
				escape: false,
			});
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
			HTMLInjectionManager.injectHTML(
				modalBody,
				modalBody.dataset.originalContent,
				{ escape: false },
			);
			// Clean up the stored content
			delete modalBody.dataset.originalContent;
		}
	}

	/**
	 * Show modal error
	 * @param {string} modalId - Modal ID
	 * @param {string} message - Error message
	 */
	showModalError(modalId, message) {
		const modal = document.getElementById(modalId);
		if (!modal) return;

		const modalBody = modal.querySelector(".modal-body");
		if (modalBody) {
			const errorHtml = `
				<div class="alert alert-danger" role="alert">
					<i class="bi bi-exclamation-triangle me-2"></i>
					${HTMLInjectionManager.escapeHtml(message)}
				</div>
			`;
			HTMLInjectionManager.injectHTML(modalBody, errorHtml, { escape: false });
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
		if (modal) {
			const bootstrapModal = new bootstrap.Modal(modal);
			bootstrapModal.show();
		}
	}

	/**
	 * Close modal
	 * @param {string} modalId - Modal ID
	 */
	closeModal(modalId) {
		const modal = document.getElementById(modalId);
		if (modal) {
			const bootstrapModal = bootstrap.Modal.getInstance(modal);
			if (bootstrapModal) {
				bootstrapModal.hide();
			}
		}
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
			const response = await APIClient.get(
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
	updateFileTree(modal, tree) {
		const tableBody = modal.querySelector("#dataset-file-tree-table tbody");
		if (!tableBody || !tree) return;

		// Clear existing content
		tableBody.innerHTML = "";

		// Render the tree structure
		const rows = this.renderTreeNode(tree, 0);

		if (rows.length === 0) {
			HTMLInjectionManager.injectHTML(
				tableBody,
				'<tr><td colspan="5" class="text-center text-muted py-4">No files found</td></tr>',
			);
		} else {
			HTMLInjectionManager.injectHTML(tableBody, rows.join(""), {
				escape: false,
			});
		}
	}

	/**
	 * Render a tree node and its children recursively
	 * @param {Object} node - Tree node
	 * @param {number} depth - Current depth for indentation
	 * @returns {Array<string>} Array of HTML row strings
	 */
	renderTreeNode(node, depth = 0) {
		const rows = [];
		const indent = "&nbsp;".repeat(depth * 4);

		// Render files in this directory first
		if (node.files && Array.isArray(node.files)) {
			for (const file of node.files) {
				const icon = '<i class="bi bi-file-earmark text-primary"></i>';
				const name = `${indent}${icon} ${HTMLInjectionManager.escapeHtml(file.name)}`;
				const type = HTMLInjectionManager.escapeHtml(
					file.media_type || file.type || "File",
				);
				const size = this.formatFileSize(file.size || 0);
				const createdAt = this.formatDate(file.created_at);

				rows.push(`
					<tr>
						<td></td>
						<td>${name}</td>
						<td>${type}</td>
						<td>${size}</td>
						<td>${createdAt}</td>
					</tr>
				`);
			}
		}

		// Render child directories
		if (node.children && typeof node.children === "object") {
			for (const childNode of Object.values(node.children)) {
				if (childNode.type === "directory") {
					// Render directory row
					const icon = '<i class="bi bi-folder text-warning"></i>';
					const name = `${indent}${icon} ${HTMLInjectionManager.escapeHtml(childNode.name)}/`;
					const type = "Directory";
					const size = this.formatFileSize(childNode.size || 0);
					const createdAt = this.formatDate(childNode.created_at);

					rows.push(`
						<tr>
							<td><i class="bi bi-chevron-down text-muted"></i></td>
							<td>${name}</td>
							<td>${type}</td>
							<td>${size}</td>
							<td>${createdAt}</td>
						</tr>
					`);

					// Recursively render children
					const childRows = this.renderTreeNode(childNode, depth + 1);
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
