/* Reusable Components for SDS Gateway */

/**
 * Utility functions for security and common operations
 */
const ComponentUtils = {
	/**
	 * Escapes HTML to prevent XSS attacks
	 * @param {string} text - Text to escape
	 * @returns {string} Escaped HTML
	 */
	escapeHtml(text) {
		if (!text) return "";
		const div = document.createElement("div");
		div.textContent = text;
		return div.innerHTML;
	},

	/**
	 * Formats file size in human readable format
	 * @param {number} bytes - File size in bytes
	 * @returns {string} Formatted file size
	 */
	formatFileSize(bytes) {
		if (bytes === 0) return "0 Bytes";
		const k = 1024;
		const sizes = ["Bytes", "KB", "MB", "GB", "TB"];
		const i = Math.floor(Math.log(bytes) / Math.log(k));
		return `${Number.parseFloat((bytes / k ** i).toFixed(2))} ${sizes[i]}`;
	},

	/**
	 * Formats date for display with date and time on separate lines
	 * @param {string} dateString - ISO date string or formatted date string
	 * @returns {string} Formatted date with HTML structure
	 */
	formatDate(dateString) {
		if (!dateString) return "<div>-</div>";

		let date;

		// Try to parse the date string
		if (typeof dateString === "string") {
			// Handle different date formats
			if (dateString.includes("T")) {
				// ISO format: 2023-12-25T14:30:45.123Z
				date = new Date(dateString);
			} else if (dateString.includes("/") && dateString.includes(":")) {
				// Already formatted: 12/25/2023 2:30:45 PM
				date = new Date(dateString);
			} else {
				// Try to parse as-is
				date = new Date(dateString);
			}
		} else {
			date = new Date(dateString);
		}

		if (!date || Number.isNaN(date.getTime())) {
			return "<div>-</div>";
		}

		const month = String(date.getMonth() + 1).padStart(2, "0");
		const day = String(date.getDate()).padStart(2, "0");
		const year = date.getFullYear();
		const hours = date.getHours();
		const minutes = String(date.getMinutes()).padStart(2, "0");
		const seconds = String(date.getSeconds()).padStart(2, "0");
		const ampm = hours >= 12 ? "PM" : "AM";
		const displayHours = hours % 12 || 12;

		return `<div>${month}/${day}/${year}</div><small class="text-muted">${displayHours}:${minutes}:${seconds} ${ampm}</small>`;
	},

	/**
	 * Formats date for display (simple version)
	 * @param {string} dateString - ISO date string
	 * @returns {string} Formatted date
	 */
	formatDateSimple(dateString) {
		try {
			const date = new Date(dateString);
			return date.toString() !== "Invalid Date"
				? date.toLocaleDateString("en-US", {
						month: "2-digit",
						day: "2-digit",
						year: "numeric",
					})
				: "";
		} catch (e) {
			return "";
		}
	},
};

/**
 * TableManager - Handles table operations like sorting, pagination, and updates
 */
class TableManager {
	constructor(config) {
		this.tableId = config.tableId;
		this.table = document.getElementById(this.tableId);
		this.tbody = this.table?.querySelector("tbody");
		this.loadingIndicator = document.getElementById(config.loadingIndicatorId);
		this.paginationContainer = document.getElementById(
			config.paginationContainerId,
		);
		this.currentSort = { by: "created_at", order: "desc" };
		this.onRowClick = config.onRowClick;

		this.initializeSorting();
	}

	initializeSorting() {
		if (!this.table) return;

		const sortableHeaders = this.table.querySelectorAll("th.sortable");
		for (const header of sortableHeaders) {
			header.style.cursor = "pointer";
			header.addEventListener("click", () => {
				this.handleSort(header);
			});
		}

		this.updateSortIcons();
	}

	handleSort(header) {
		const field = header.getAttribute("data-sort");
		const currentSort = new URLSearchParams(window.location.search).get(
			"sort_by",
		);
		const currentOrder =
			new URLSearchParams(window.location.search).get("sort_order") || "desc";

		let newOrder = "asc";
		if (currentSort === field && currentOrder === "asc") {
			newOrder = "desc";
		}

		this.currentSort = { by: field, order: newOrder };
		this.updateURL({ sort_by: field, sort_order: newOrder, page: "1" });
	}

	updateSortIcons() {
		const urlParams = new URLSearchParams(window.location.search);
		const currentSort = urlParams.get("sort_by") || "created_at";
		const currentOrder = urlParams.get("sort_order") || "desc";

		const sortableHeaders = this.table?.querySelectorAll("th.sortable");
		for (const header of sortableHeaders || []) {
			const icon = header.querySelector(".sort-icon");
			const field = header.getAttribute("data-sort");

			if (icon) {
				// Reset classes
				icon.className = "bi sort-icon";

				if (field === currentSort) {
					// Add active class and appropriate direction icon
					icon.classList.add("active");
					icon.classList.add(
						currentOrder === "asc" ? "bi-caret-up-fill" : "bi-caret-down-fill",
					);
				} else {
					// Inactive columns get default down arrow
					icon.classList.add("bi-caret-down-fill");
				}
			}
		}
	}

	showLoading() {
		if (this.loadingIndicator) {
			this.loadingIndicator.classList.remove("d-none");
		}
	}

	hideLoading() {
		if (this.loadingIndicator) {
			this.loadingIndicator.classList.add("d-none");
		}
	}

	showError(message) {
		const tbody = document.querySelector("tbody");
		if (tbody) {
			tbody.innerHTML = `
				<tr>
					<td colspan="8" class="text-center text-danger py-4">
						<i class="fas fa-exclamation-triangle"></i> ${ComponentUtils.escapeHtml(message)}
						<br><small class="text-muted">Try refreshing the page or contact support if the problem persists.</small>
					</td>
				</tr>
			`;
		}
	}

	updateTable(data, hasResults) {
		if (!this.tbody) return;

		if (!hasResults || !data || data.length === 0) {
			this.tbody.innerHTML = `
                <tr>
                    <td colspan="8" class="text-center text-muted py-4">No results found.</td>
                </tr>
            `;
			return;
		}

		this.tbody.innerHTML = data
			.map((item, index) => this.renderRow(item, index))
			.join("");
		this.attachRowClickHandlers();
	}

	renderRow(item, index) {
		// This should be overridden by specific implementations
		return `<tr><td colspan="9">Override renderRow method</td></tr>`;
	}

	attachRowClickHandlers() {
		if (!this.onRowClick) return;

		const rows = this.tbody?.querySelectorAll('tr[data-clickable="true"]');
		for (const row of rows || []) {
			row.addEventListener("click", (e) => {
				if (e.target.closest("button, a")) return; // Don't trigger on buttons/links
				this.onRowClick(row);
			});
		}
	}

	updateURL(params) {
		const urlParams = new URLSearchParams(window.location.search);
		for (const [key, value] of Object.entries(params)) {
			if (value) {
				urlParams.set(key, value);
			} else {
				urlParams.delete(key);
			}
		}

		const newUrl = `${window.location.pathname}?${urlParams.toString()}`;
		window.history.pushState({}, "", newUrl);
	}
}

/**
 * CapturesTableManager - Specific implementation for captures table
 */
class CapturesTableManager extends TableManager {
	constructor(config) {
		super(config);
		this.modalHandler = config.modalHandler;
		this.tableContainerSelector = config.tableContainerSelector;
		this.eventDelegationHandler = null;
		this.initializeEventDelegation();
	}

	/**
	 * Initialize event delegation for better performance and memory management
	 */
	initializeEventDelegation() {
		// Remove existing handler if it exists
		if (this.eventDelegationHandler) {
			document.removeEventListener("click", this.eventDelegationHandler);
		}

		// Create single persistent event handler using delegation
		this.eventDelegationHandler = (e) => {
			// Ignore Bootstrap dropdown toggles
			if (
				e.target.matches('[data-bs-toggle="dropdown"]') ||
				e.target.closest('[data-bs-toggle="dropdown"]')
			) {
				return;
			}

			// Handle capture details button clicks from actions dropdown
			if (
				e.target.matches(".capture-details-btn") ||
				e.target.closest(".capture-details-btn")
			) {
				e.preventDefault();
				const button = e.target.matches(".capture-details-btn")
					? e.target
					: e.target.closest(".capture-details-btn");
				this.openCaptureModal(button);
				return;
			}

			// Handle download capture button clicks from actions dropdown
			if (
				e.target.matches(".download-capture-btn") ||
				e.target.closest(".download-capture-btn")
			) {
				e.preventDefault();
				const button = e.target.matches(".download-capture-btn")
					? e.target
					: e.target.closest(".download-capture-btn");
				this.handleDownloadCapture(button);
				return;
			}

			// Handle capture link clicks
			if (
				e.target.matches(".capture-link") ||
				e.target.closest(".capture-link")
			) {
				e.preventDefault();
				const link = e.target.matches(".capture-link")
					? e.target
					: e.target.closest(".capture-link");
				this.openCaptureModal(link);
				return;
			}

			// Handle view button clicks
			if (
				e.target.matches(".view-capture-btn") ||
				e.target.closest(".view-capture-btn")
			) {
				e.preventDefault();
				const button = e.target.matches(".view-capture-btn")
					? e.target
					: e.target.closest(".view-capture-btn");
				this.openCaptureModal(button);
				return;
			}
		};

		// Add the persistent event listener
		document.addEventListener("click", this.eventDelegationHandler);
	}

	/**
	 * Handle download capture action
	 */
	handleDownloadCapture(button) {
		const captureUuid = button.dataset.captureUuid;
		const captureName =
			button.dataset.captureName || button.dataset.captureUuid;

		if (!captureUuid) {
			console.error("No capture UUID found for download");
			return;
		}

		// Show loading state
		const originalContent = button.innerHTML;
		button.innerHTML = '<i class="bi bi-hourglass-split"></i> Processing...';
		button.disabled = true;

		// Make API request
		fetch(`/users/capture-download/${captureUuid}/`, {
			method: "POST",
			headers: {
				"Content-Type": "application/json",
				"X-CSRFToken": this.getCSRFToken(),
			},
		})
			.then((response) => response.json())
			.then((data) => {
				if (data.status === "success") {
					button.innerHTML =
						'<i class="bi bi-check-circle text-success"></i> Download Requested';
					this.showDownloadSuccessMessage(data.message);
				} else {
					button.innerHTML =
						'<i class="bi bi-exclamation-triangle text-danger"></i> Request Failed';
					this.showDownloadErrorMessage(
						data.detail ||
							data.message ||
							"Download request failed. Please try again.",
					);
				}
			})
			.catch((error) => {
				console.error("Download error:", error);
				button.innerHTML =
					'<i class="bi bi-exclamation-triangle text-danger"></i> Request Failed';
				this.showDownloadErrorMessage(
					"An error occurred while processing your request.",
				);
			})
			.finally(() => {
				// Reset button after 3 seconds
				setTimeout(() => {
					button.innerHTML = originalContent;
					button.disabled = false;
				}, 3000);
			});
	}

	/**
	 * Show download success message
	 */
	showDownloadSuccessMessage(message) {
		// Try to find an existing alert container or create one
		let alertContainer = document.querySelector(".alert-container");
		if (!alertContainer) {
			alertContainer = document.createElement("div");
			alertContainer.className = "alert-container";
			// Insert at the top of the main content area
			const mainContent =
				document.querySelector(".container-fluid") || document.body;
			mainContent.insertBefore(alertContainer, mainContent.firstChild);
		}

		const alertHtml = `
			<div class="alert alert-success alert-dismissible fade show" role="alert">
				<i class="bi bi-check-circle-fill me-2"></i>
				${ComponentUtils.escapeHtml(message)}
				<button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
			</div>
		`;

		alertContainer.innerHTML = alertHtml;

		// Auto-dismiss after 5 seconds
		setTimeout(() => {
			const alert = alertContainer.querySelector(".alert");
			if (alert) {
				alert.remove();
			}
		}, 5000);
	}

	/**
	 * Show download error message
	 */
	showDownloadErrorMessage(message) {
		// Try to find an existing alert container or create one
		let alertContainer = document.querySelector(".alert-container");
		if (!alertContainer) {
			alertContainer = document.createElement("div");
			alertContainer.className = "alert-container";
			// Insert at the top of the main content area
			const mainContent =
				document.querySelector(".container-fluid") || document.body;
			mainContent.insertBefore(alertContainer, mainContent.firstChild);
		}

		const alertHtml = `
			<div class="alert alert-danger alert-dismissible fade show" role="alert">
				<i class="bi bi-exclamation-triangle-fill me-2"></i>
				${ComponentUtils.escapeHtml(message)}
				<button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
			</div>
		`;

		alertContainer.innerHTML = alertHtml;

		// Auto-dismiss after 8 seconds (longer for error messages)
		setTimeout(() => {
			const alert = alertContainer.querySelector(".alert");
			if (alert) {
				alert.remove();
			}
		}, 8000);
	}

	renderRow(capture, index) {
		// Sanitize all data before rendering
		const safeData = {
			uuid: ComponentUtils.escapeHtml(capture.uuid || ""),
			channel: ComponentUtils.escapeHtml(capture.channel || ""),
			scanGroup: ComponentUtils.escapeHtml(capture.scan_group || ""),
			captureType: ComponentUtils.escapeHtml(capture.capture_type || ""),
			captureTypeDisplay: ComponentUtils.escapeHtml(
				capture.capture_type_display || "",
			),
			topLevelDir: ComponentUtils.escapeHtml(capture.top_level_dir || ""),
			indexName: ComponentUtils.escapeHtml(capture.index_name || ""),
			owner: ComponentUtils.escapeHtml(capture.owner || ""),
			origin: ComponentUtils.escapeHtml(capture.origin || ""),
			dataset: ComponentUtils.escapeHtml(capture.dataset || ""),
			createdAt: ComponentUtils.escapeHtml(capture.created_at || ""),
			updatedAt: ComponentUtils.escapeHtml(capture.updated_at || ""),
			isPublic: ComponentUtils.escapeHtml(capture.is_public || ""),
			isDeleted: ComponentUtils.escapeHtml(capture.is_deleted || ""),
			centerFrequencyGhz: ComponentUtils.escapeHtml(
				capture.center_frequency_ghz || "",
			),
		};

		// Handle composite vs single capture display
		let channelDisplay = safeData.channel;
		let typeDisplay = safeData.captureTypeDisplay || safeData.captureType;

		if (capture.is_multi_channel) {
			// For composite captures, show all channels
			if (capture.channels && Array.isArray(capture.channels)) {
				channelDisplay = capture.channels
					.map((ch) => ComponentUtils.escapeHtml(ch.channel || ch))
					.join(", ");
			}
			// Use capture_type_display if available, otherwise fall back to captureType
			typeDisplay = capture.capture_type_display || safeData.captureType;
		}

		return `
            <tr class="capture-row" data-clickable="true" data-uuid="${safeData.uuid}">
                <td>
                    <a href="#" class="capture-link"
                       data-uuid="${safeData.uuid}"
                       data-channel="${safeData.channel}"
                       data-scan-group="${safeData.scanGroup}"
                       data-capture-type="${safeData.captureType}"
                       data-top-level-dir="${safeData.topLevelDir}"
                       data-index-name="${safeData.indexName}"
                       data-owner="${safeData.owner}"
                       data-origin="${safeData.origin}"
                       data-dataset="${safeData.dataset}"
                       data-created-at="${safeData.createdAt}"
                       data-updated-at="${safeData.updatedAt}"
                       data-is-public="${safeData.isPublic}"
                       data-is-deleted="${safeData.isDeleted}"
                       data-center-frequency-ghz="${safeData.centerFrequencyGhz}"
                       data-is-multi-channel="${capture.is_multi_channel || false}"
                       data-channels="${capture.channels ? JSON.stringify(capture.channels) : ""}"
                       aria-label="View details for ${safeData.uuid || "unknown capture"}">
                        ${safeData.uuid}
                    </a>
                </td>
                <td>${channelDisplay}</td>
                <td class="text-nowrap">${ComponentUtils.formatDate(capture.created_at)}</td>
                <td>${typeDisplay}</td>
                <td>${capture.files_count || "0"}</td>
                <td>${capture.center_frequency_ghz ? `${capture.center_frequency_ghz.toFixed(3)} GHz` : "-"}</td>
                <td>${capture.sample_rate_mhz ? `${capture.sample_rate_mhz.toFixed(1)} MHz` : "-"}</td>
            </tr>
        `;
	}

	/**
	 * Attach row click handlers - now uses event delegation
	 */
	attachRowClickHandlers() {
		// Event delegation is handled in initializeEventDelegation()
		// This method is kept for compatibility but doesn't need to do anything
	}

	/**
	 * Open capture modal with XSS protection
	 */
	openCaptureModal(linkElement) {
		if (this.modalHandler) {
			this.modalHandler.openCaptureModal(linkElement);
		}
	}

	/**
	 * Get CSRF token for API requests
	 */
	getCSRFToken() {
		const token = document.querySelector("[name=csrfmiddlewaretoken]");
		return token ? token.value : "";
	}

	/**
	 * Cleanup method for proper resource management
	 */
	destroy() {
		if (this.eventDelegationHandler) {
			document.removeEventListener("click", this.eventDelegationHandler);
			this.eventDelegationHandler = null;
		}
	}
}

/**
 * FilterManager - Handles form-based filtering with URL state management
 */
class FilterManager {
	constructor(config) {
		this.formId = config.formId;
		this.form = document.getElementById(this.formId);
		this.applyButton = document.getElementById(config.applyButtonId);
		this.clearButton = document.getElementById(config.clearButtonId);
		this.onFilterChange = config.onFilterChange;

		this.initializeEventListeners();
		this.loadFromURL();
	}

	initializeEventListeners() {
		if (this.applyButton) {
			this.applyButton.addEventListener("click", (e) => {
				e.preventDefault();
				this.applyFilters();
			});
		}

		if (this.clearButton) {
			this.clearButton.addEventListener("click", (e) => {
				e.preventDefault();
				this.clearFilters();
			});
		}

		// Auto-apply on form submission
		if (this.form) {
			this.form.addEventListener("submit", (e) => {
				e.preventDefault();
				this.applyFilters();
			});
		}
	}

	getFilterValues() {
		if (!this.form) return {};

		const formData = new FormData(this.form);
		const filters = {};

		for (const [key, value] of formData.entries()) {
			if (value && value.trim() !== "") {
				filters[key] = value.trim();
			}
		}

		return filters;
	}

	applyFilters() {
		const filters = this.getFilterValues();
		this.updateURL(filters);

		if (this.onFilterChange) {
			this.onFilterChange(filters);
		}
	}

	clearFilters() {
		if (!this.form) return;

		// Clear all form inputs
		const inputs = this.form.querySelectorAll("input, select, textarea");
		for (const input of inputs) {
			if (input.type === "checkbox" || input.type === "radio") {
				input.checked = false;
			} else {
				input.value = "";
			}
		}

		// Clear URL parameters
		this.updateURL({});

		if (this.onFilterChange) {
			this.onFilterChange({});
		}
	}

	loadFromURL() {
		if (!this.form) return;

		const urlParams = new URLSearchParams(window.location.search);
		const inputs = this.form.querySelectorAll("input, select, textarea");

		for (const input of inputs) {
			const value = urlParams.get(input.name);
			if (value !== null) {
				if (input.type === "checkbox" || input.type === "radio") {
					input.checked = value === "true" || value === input.value;
				} else {
					input.value = value;
				}
			}
		}
	}

	updateURL(filters) {
		const urlParams = new URLSearchParams(window.location.search);

		// Remove old filter parameters
		const formData = new FormData(this.form || document.createElement("form"));
		for (const key of formData.keys()) {
			urlParams.delete(key);
		}

		// Add new filter parameters
		for (const [key, value] of Object.entries(filters)) {
			if (value) {
				urlParams.set(key, value);
			}
		}

		// Reset to first page when filters change
		urlParams.set("page", "1");

		const newUrl = `${window.location.pathname}?${urlParams.toString()}`;
		window.history.pushState({}, "", newUrl);
	}
}

/**
 * SearchManager - Handles search functionality with debouncing
 */
class SearchManager {
	constructor(config) {
		this.searchInput = document.getElementById(config.searchInputId);
		this.searchButton = document.getElementById(config.searchButtonId);
		this.clearButton = document.getElementById(config.clearButtonId);
		this.onSearch = config.onSearch;
		this.debounceDelay = config.debounceDelay || 300;
		this.debounceTimer = null;

		this.initializeEventListeners();
	}

	initializeEventListeners() {
		if (this.searchInput) {
			this.searchInput.addEventListener("input", () => {
				this.debounceSearch();
			});

			this.searchInput.addEventListener("keypress", (e) => {
				if (e.key === "Enter") {
					e.preventDefault();
					this.performSearch();
				}
			});
		}

		if (this.searchButton) {
			this.searchButton.addEventListener("click", (e) => {
				e.preventDefault();
				this.performSearch();
			});
		}

		if (this.clearButton) {
			this.clearButton.addEventListener("click", (e) => {
				e.preventDefault();
				this.clearSearch();
			});
		}
	}

	debounceSearch() {
		if (this.debounceTimer) {
			clearTimeout(this.debounceTimer);
		}

		this.debounceTimer = setTimeout(() => {
			this.performSearch();
		}, this.debounceDelay);
	}

	performSearch() {
		const query = this.searchInput?.value || "";

		if (this.onSearch) {
			this.onSearch(query);
		}
	}

	clearSearch() {
		if (this.searchInput) {
			this.searchInput.value = "";
		}

		this.performSearch();
	}
}

/**
 * ModalManager - Handles modal operations
 */
class ModalManager {
	constructor(config) {
		this.modalId = config.modalId;
		this.modal = document.getElementById(this.modalId);
		this.modalTitle = this.modal?.querySelector(".modal-title");
		this.modalBody = this.modal?.querySelector(".modal-body");

		if (this.modal && window.bootstrap) {
			this.bootstrapModal = new bootstrap.Modal(this.modal);
		}
	}

	show(title, content) {
		if (!this.modal) return;

		if (this.modalTitle) {
			this.modalTitle.textContent = title;
		}

		if (this.modalBody) {
			this.modalBody.innerHTML = content;
		}

		if (this.bootstrapModal) {
			this.bootstrapModal.show();
		}
	}

	hide() {
		if (this.bootstrapModal) {
			this.bootstrapModal.hide();
		}
	}

	openCaptureModal(linkElement) {
		if (!linkElement) return;

		try {
			// Get all data attributes from the link with sanitization
			const data = {
				uuid: ComponentUtils.escapeHtml(
					linkElement.getAttribute("data-uuid") || "",
				),
				name: ComponentUtils.escapeHtml(
					linkElement.getAttribute("data-name") || "",
				),
				channel: ComponentUtils.escapeHtml(
					linkElement.getAttribute("data-channel") || "",
				),
				scanGroup: ComponentUtils.escapeHtml(
					linkElement.getAttribute("data-scan-group") || "",
				),
				captureType: ComponentUtils.escapeHtml(
					linkElement.getAttribute("data-capture-type") || "",
				),
				topLevelDir: ComponentUtils.escapeHtml(
					linkElement.getAttribute("data-top-level-dir") || "",
				),
				owner: ComponentUtils.escapeHtml(
					linkElement.getAttribute("data-owner") || "",
				),
				origin: ComponentUtils.escapeHtml(
					linkElement.getAttribute("data-origin") || "",
				),
				dataset: ComponentUtils.escapeHtml(
					linkElement.getAttribute("data-dataset") || "",
				),
				createdAt: linkElement.getAttribute("data-created-at") || "",
				updatedAt: linkElement.getAttribute("data-updated-at") || "",
				isPublic: linkElement.getAttribute("data-is-public") || "",
				centerFrequencyGhz:
					linkElement.getAttribute("data-center-frequency-ghz") || "",
				isMultiChannel: linkElement.getAttribute("data-is-multi-channel") || "",
				channels: linkElement.getAttribute("data-channels") || "",
			};

			// Parse owner field safely
			const ownerDisplay = data.owner
				? data.owner.split("'").find((part) => part.includes("@")) || "N/A"
				: "N/A";

			// Check if this is a composite capture
			const isComposite =
				data.isMultiChannel === "True" || data.isMultiChannel === "true";

			let modalContent = `
				<div class="mb-4">
					<div class="d-flex align-items-center mb-3">
						<h6 class="mb-0 fw-bold">
							<i class="bi bi-info-circle me-2"></i>Basic Information
						</h6>
					</div>
					<div class="mb-3">
						<label for="capture-name-input" class="form-label fw-medium">
							<strong>Name:</strong>
						</label>
						<div class="input-group">
							<input type="text"
								   class="form-control"
								   id="capture-name-input"
								   value="${data.name || ""}"
								   placeholder="Enter capture name"
								   maxlength="255"
								   data-uuid="${data.uuid}">
							<button class="btn btn-outline-secondary"
									type="button"
									id="edit-name-btn"
									title="Edit capture name">
								<i class="bi bi-pencil"></i>
							</button>
						</div>
						<div class="form-text">Click the edit button to modify the capture name</div>
					</div>
					<div class="row">
						<div class="col-md-6">
							<p class="mb-2">
								<span class="fw-medium text-muted">Capture Type:</span>
								<span class="ms-2">${data.captureType || "N/A"}</span>
							</p>
							<p class="mb-2">
								<span class="fw-medium text-muted">Origin:</span>
								<span class="ms-2">${data.origin || "N/A"}</span>
							</p>
						</div>
						<div class="col-md-6">
							<p class="mb-2">
								<span class="fw-medium text-muted">Owner:</span>
								<span class="ms-2">${ownerDisplay}</span>
							</p>
						</div>
					</div>
			`;

			// Handle composite vs single capture display
			if (isComposite) {
				modalContent += `
					<div class="mb-2">
						<span class="fw-medium text-muted">Channels:</span>
						<span class="ms-2">${data.channel || "N/A"}</span>
					</div>
				`;
			} else {
				modalContent += `
					<div class="mb-2">
						<span class="fw-medium text-muted">Channel:</span>
						<span class="ms-2">${data.channel || "N/A"}</span>
					</div>
				`;
			}

			modalContent += `
				</div>
				<div class="mb-4">
					<div class="d-flex align-items-center mb-3">
						<h6 class="mb-0 fw-bold">
							<i class="bi bi-gear me-2"></i>Technical Details
						</h6>
					</div>
					<div class="row">
						<div class="col-md-6">
							<p class="mb-2">
								<span class="fw-medium text-muted">Scan Group:</span>
								<span class="ms-2">${data.scanGroup || "N/A"}</span>
							</p>
							<p class="mb-2">
								<span class="fw-medium text-muted">Dataset:</span>
								<span class="ms-2">${data.dataset || "N/A"}</span>
							</p>
							<p class="mb-2">
								<span class="fw-medium text-muted">Is Public:</span>
								<span class="ms-2">${data.isPublic === "True" ? "Yes" : "No"}</span>
							</p>
						</div>
						<div class="col-md-6">
							<p class="mb-2">
								<span class="fw-medium text-muted">Top Level Directory:</span>
								<span class="ms-2 text-break">${data.topLevelDir || "N/A"}</span>
							</p>
							<p class="mb-2">
								<span class="fw-medium text-muted">Center Frequency:</span>
								<span class="ms-2">
									${data.centerFrequencyGhz && data.centerFrequencyGhz !== "None" ? `${Number.parseFloat(data.centerFrequencyGhz).toFixed(3)} GHz` : "N/A"}
								</span>
							</p>
						</div>
					</div>
				</div>
				<div class="mb-4">
					<div class="d-flex align-items-center mb-3">
						<h6 class="mb-0 fw-bold">
							<i class="bi bi-clock me-2"></i>Timestamps
						</h6>
					</div>
					<div class="row">
						<div class="col-md-6">
							<p class="mb-2">
								<span class="fw-medium text-muted">Created At:</span>
								<br>
								<small class="text-muted">
									${data.createdAt && data.createdAt !== "None" ? `${new Date(data.createdAt).toLocaleString()} UTC` : "N/A"}
								</small>
							</p>
						</div>
						<div class="col-md-6">
							<p class="mb-2">
								<span class="fw-medium text-muted">Updated At:</span>
								<br>
								<small class="text-muted">
									${data.updatedAt && data.updatedAt !== "None" ? `${new Date(data.updatedAt).toLocaleString()} UTC` : "N/A"}
								</small>
							</p>
						</div>
					</div>
				</div>
				<!-- Files section placeholder -->
				<div id="files-section-placeholder" class="mt-4">
					<div class="d-flex justify-content-center py-3">
						<div class="spinner-border spinner-border-sm me-2" role="status" style="color: #005a9c;">
							<span class="visually-hidden">Loading files...</span>
						</div>
						<span class="text-muted">Loading files...</span>
					</div>
				</div>
			`;

			// Add composite-specific information if available
			if (isComposite && data.channels) {
				try {
					// Convert Python dict syntax to valid JSON
					let channelsData;
					if (typeof data.channels === "string") {
						// Handle Python dict syntax: {'key': 'value'} -> {"key": "value"}
						const pythonDict = data.channels
							.replace(/'/g, '"') // Replace single quotes with double quotes
							.replace(/True/g, "true") // Replace Python True with JSON true
							.replace(/False/g, "false") // Replace Python False with JSON false
							.replace(/None/g, "null"); // Replace Python None with JSON null

						channelsData = JSON.parse(pythonDict);
					} else {
						channelsData = data.channels;
					}

					if (Array.isArray(channelsData) && channelsData.length > 0) {
						modalContent += `
							<div class="mt-4">
								<h6>Channel Details</h6>
								<div class="accordion" id="channelsAccordion">
						`;

						for (let i = 0; i < channelsData.length; i++) {
							const channel = channelsData[i];
							const channelId = `channel-${i}`;

							// Format channel metadata as key-value pairs
							let metadataDisplay = "N/A";
							if (
								channel.channel_metadata &&
								typeof channel.channel_metadata === "object"
							) {
								const metadata = channel.channel_metadata;
								const metadataItems = [];

								// Helper function to format values dynamically
								const formatValue = (value, fieldName = "") => {
									if (value === null || value === undefined) {
										return "N/A";
									}

									if (typeof value === "boolean") {
										return value ? "Yes" : "No";
									}

									// Handle string representations of booleans
									if (typeof value === "string") {
										if (value.toLowerCase() === "true") {
											return "Yes";
										}
										if (value.toLowerCase() === "false") {
											return "No";
										}
									}

									if (typeof value === "number") {
										const absValue = Math.abs(value);
										const valueStr = value.toString();
										const timeIndicators = [
											"computer_time",
											"start_bound",
											"end_bound",
											"init_utc_timestamp",
										];
										// Only format as timestamp if the field name contains "time"
										if (
											timeIndicators.includes(fieldName.toLowerCase()) &&
											valueStr.length >= 10 &&
											valueStr.length <= 13
										) {
											// Convert to milliseconds if it's in seconds
											const timestamp =
												valueStr.length === 10 ? value * 1000 : value;
											return new Date(timestamp).toLocaleString();
										}

										// Only format for Giga (1e9) and Mega (1e6) ranges
										if (absValue >= 1e9) {
											return `${(value / 1e9).toFixed(3)} GHz`;
										}
										if (absValue >= 1e6) {
											return `${(value / 1e6).toFixed(1)} MHz`;
										}
										return value.toString();
									}

									if (Array.isArray(value)) {
										return value
											.map((item) => formatValue(item, fieldName))
											.join(", ");
									}

									if (typeof value === "object") {
										return JSON.stringify(value);
									}

									return String(value);
								};

								// Helper function to format field names
								const formatFieldName = (fieldName) => {
									return fieldName
										.replace(/_/g, " ")
										.replace(/\b\w/g, (l) => l.toUpperCase());
								};

								// Loop through all metadata fields
								if (Object.keys(metadata).length > 0) {
									for (const [key, value] of Object.entries(metadata)) {
										if (value !== undefined && value !== null) {
											const formattedValue = formatValue(value, key);
											const formattedKey = formatFieldName(key);
											metadataItems.push(
												`<strong>${formattedKey}:</strong> ${formattedValue}`,
											);
										}
									}
								} else {
									metadataItems.push("<em>No metadata available</em>");
								}

								if (metadataItems.length > 0) {
									metadataDisplay = metadataItems.join("<br>");
								}
							}

							modalContent += `
								<div class="accordion-item">
									<h2 class="accordion-header" id="heading-${channelId}">
										<button class="accordion-button ${i === 0 ? "" : "collapsed"}" type="button"
												data-bs-toggle="collapse"
												data-bs-target="#collapse-${channelId}"
												aria-expanded="${i === 0 ? "true" : "false"}"
												aria-controls="collapse-${channelId}">
											<strong>${ComponentUtils.escapeHtml(channel.channel || "N/A")}</strong>
											<small class="text-muted ms-2">(Click to expand metadata)</small>
										</button>
									</h2>
									<div id="collapse-${channelId}"
										 class="accordion-collapse collapse ${i === 0 ? "show" : ""}"
										 aria-labelledby="heading-${channelId}"
										 data-bs-parent="#channelsAccordion">
										<div class="accordion-body">
											<div style="max-width: 100%; word-wrap: break-word;">
												${metadataDisplay}
											</div>
										</div>
									</div>
								</div>
							`;
						}

						modalContent += `
								</div>
							</div>
						`;
					}
				} catch (e) {
					console.error("Could not parse channels data for modal:", e);
					console.error(
						"Raw channels data that failed to parse:",
						data.channels,
					);

					// Show a fallback message in the modal
					modalContent += `
						<div class="mt-4">
							<h6>Channel Details</h6>
							<div class="alert alert-warning">
								<i class="fas fa-exclamation-triangle"></i>
								Unable to display channel details due to data format issues.
								<br><small>Raw data: ${ComponentUtils.escapeHtml(String(data.channels).substring(0, 100))}...</small>
							</div>
						</div>
					`;
				}
			}

			const title = `Capture Details - ${data.channel || "Unknown"}`;
			this.show(title, modalContent);

			// Setup name editing handlers after modal content is loaded
			this.setupNameEditingHandlers();

			// Load and display files for this capture
			this.loadCaptureFiles(data.uuid);
		} catch (error) {
			console.error("Error opening capture modal:", error);
			this.show("Error", "Error displaying capture details");
		}
	}

	/**
	 * Setup handlers for name editing functionality
	 */
	setupNameEditingHandlers() {
		const nameInput = document.getElementById("capture-name-input");
		const editBtn = document.getElementById("edit-name-btn");
		const saveBtn = document.getElementById("save-capture-btn");

		if (!nameInput || !editBtn || !saveBtn) return;

		// Initially disable the input
		nameInput.disabled = true;
		let originalName = nameInput.value;
		let isEditing = false;

		// Edit button handler
		editBtn.addEventListener("click", () => {
			if (!isEditing) {
				// Start editing
				nameInput.disabled = false;
				nameInput.focus();
				nameInput.select();
				editBtn.innerHTML = '<i class="bi bi-x-lg"></i>';
				editBtn.title = "Cancel editing";
				saveBtn.style.display = "inline-block";
				isEditing = true;
			} else {
				// Cancel editing
				nameInput.value = originalName;
				nameInput.disabled = true;
				editBtn.innerHTML = '<i class="bi bi-pencil"></i>';
				editBtn.title = "Edit capture name";
				saveBtn.style.display = "none";
				isEditing = false;
			}
		});

		// Save button handler
		saveBtn.addEventListener("click", async () => {
			const newName = nameInput.value.trim();
			const uuid = nameInput.getAttribute("data-uuid");

			if (!uuid) {
				console.error("No UUID found for capture");
				return;
			}

			// Disable buttons during save
			editBtn.disabled = true;
			saveBtn.disabled = true;
			saveBtn.innerHTML =
				'<span class="spinner-border spinner-border-sm me-2"></span>Saving...';

			try {
				await this.updateCaptureName(uuid, newName);

				// Success - update UI
				originalName = newName;
				nameInput.disabled = true;
				editBtn.innerHTML = '<i class="bi bi-pencil"></i>';
				editBtn.title = "Edit capture name";
				saveBtn.style.display = "none";
				isEditing = false;

				// Update the table display
				this.updateTableNameDisplay(uuid, newName);

				// Show success message
				this.showSuccessMessage("Capture name updated successfully!");
			} catch (error) {
				console.error("Error updating capture name:", error);
				this.showErrorMessage(
					"Failed to update capture name. Please try again.",
				);
			} finally {
				// Re-enable buttons
				editBtn.disabled = false;
				saveBtn.disabled = false;
				saveBtn.innerHTML = "Save Changes";
			}
		});

		// Handle Enter key to save
		nameInput.addEventListener("keypress", (e) => {
			if (e.key === "Enter" && !nameInput.disabled) {
				saveBtn.click();
			}
		});

		// Handle Escape key to cancel
		nameInput.addEventListener("keydown", (e) => {
			if (e.key === "Escape" && !nameInput.disabled) {
				editBtn.click();
			}
		});
	}

	/**
	 * Update capture name via API
	 */
	async updateCaptureName(uuid, newName) {
		const response = await fetch(`/api/v1/assets/captures/${uuid}/`, {
			method: "PATCH",
			headers: {
				"Content-Type": "application/json",
				"X-CSRFToken": this.getCSRFToken(),
			},
			body: JSON.stringify({ name: newName }),
		});

		if (!response.ok) {
			const errorData = await response.json();
			throw new Error(errorData.detail || "Failed to update capture name");
		}

		return response.json();
	}

	/**
	 * Update the table display with the new name
	 */
	updateTableNameDisplay(uuid, newName) {
		// Find all elements with this UUID and update their display
		const captureLinks = document.querySelectorAll(`[data-uuid="${uuid}"]`);

		for (const link of captureLinks) {
			// Update data attribute
			link.dataset.name = newName;

			// Update display text if it's a capture link
			if (link.classList.contains("capture-link")) {
				link.textContent = newName || "Unnamed Capture";
				link.setAttribute(
					"aria-label",
					`View details for capture ${newName || uuid}`,
				);
				link.setAttribute("title", `View capture details: ${newName || uuid}`);
			}
		}
	}

	/**
	 * Clear existing alert messages from the modal
	 */
	clearAlerts() {
		const modalBody = document.getElementById("capture-modal-body");
		if (modalBody) {
			const existingAlerts = modalBody.querySelectorAll(".alert");
			for (const alert of existingAlerts) {
				alert.remove();
			}
		}
	}

	/**
	 * Show success message
	 */
	showSuccessMessage(message) {
		// Clear existing alerts first
		this.clearAlerts();

		// Create a temporary alert
		const alert = document.createElement("div");
		alert.className = "alert alert-success alert-dismissible fade show";
		alert.innerHTML = `
			${message}
			<button type="button" class="btn-close" data-bs-dismiss="alert"></button>
		`;

		// Insert at the top of the modal body
		const modalBody = document.getElementById("capture-modal-body");
		if (modalBody) {
			modalBody.insertBefore(alert, modalBody.firstChild);

			// Auto-dismiss after 3 seconds
			setTimeout(() => {
				if (alert.parentNode) {
					alert.remove();
				}
			}, 3000);
		}
	}

	/**
	 * Show error message
	 */
	showErrorMessage(message) {
		// Clear existing alerts first
		this.clearAlerts();

		// Create a temporary alert
		const alert = document.createElement("div");
		alert.className = "alert alert-danger alert-dismissible fade show";
		alert.innerHTML = `
			${message}
			<button type="button" class="btn-close" data-bs-dismiss="alert"></button>
		`;

		// Insert at the top of the modal body
		const modalBody = document.getElementById("capture-modal-body");
		if (modalBody) {
			modalBody.insertBefore(alert, modalBody.firstChild);

			// Auto-dismiss after 5 seconds
			setTimeout(() => {
				if (alert.parentNode) {
					alert.remove();
				}
			}, 5000);
		}
	}

	/**
	 * Load and display files associated with the capture
	 */
	async loadCaptureFiles(captureUuid) {
		try {
			const response = await fetch(`/api/v1/assets/captures/${captureUuid}/`, {
				method: "GET",
				headers: {
					"Content-Type": "application/json",
					"X-CSRFToken": this.getCSRFToken(),
				},
			});

			if (!response.ok) {
				throw new Error(`HTTP error! status: ${response.status}`);
			}

			const captureData = await response.json();
			const files = captureData.files || [];

			// Add files accordion to the modal
			this.addFilesAccordion(files);
		} catch (error) {
			console.error("Error loading capture files:", error);
			this.addFilesAccordion([], "Error loading files");
		}
	}

	/**
	 * Add files accordion to the modal
	 */
	addFilesAccordion(files, errorMessage = null) {
		const filesPlaceholder = document.getElementById(
			"files-section-placeholder",
		);
		if (!filesPlaceholder) return;

		// Create files accordion section
		const filesSection = `
			<div class="accordion" id="filesAccordion">
				<div class="accordion-item">
					<h2 class="accordion-header" id="filesHeading">
						<button class="accordion-button collapsed"
								type="button"
								data-bs-toggle="collapse"
								data-bs-target="#filesCollapse"
								aria-expanded="false"
								aria-controls="filesCollapse">
							<i class="bi bi-file-earmark me-2"></i>
							Files (${files.length})
						</button>
					</h2>
					<div id="filesCollapse"
						 class="accordion-collapse collapse"
						 aria-labelledby="filesHeading"
						 data-bs-parent="#filesAccordion">
						<div class="accordion-body">
							${this.renderFilesContent(files, errorMessage)}
						</div>
					</div>
				</div>
			</div>
		`;

		// Replace the placeholder content with the files accordion
		filesPlaceholder.innerHTML = filesSection;
	}

	/**
	 * Render the content for the files accordion
	 */
	renderFilesContent(files, errorMessage = null) {
		if (errorMessage) {
			return `
				<div class="alert alert-warning">
					<i class="bi bi-exclamation-triangle me-2"></i>
					${errorMessage}
				</div>
			`;
		}

		if (files.length === 0) {
			return `
				<div class="text-muted text-center py-3">
					<i class="bi bi-inbox me-2"></i>
					No files associated with this capture
				</div>
			`;
		}

		// Create file browser structure matching SpectrumX theme
		let filesHtml = `
			<div class="file-browser">
				<div class="file-browser-header">
					<span class="selection-info">
						<i class="bi bi-files me-2"></i>
						${files.length} file${files.length !== 1 ? "s" : ""} found
					</span>
				</div>
				<ul role="tree" aria-label="Capture files">
		`;

		// Group files by directory for hierarchical display
		const filesByDirectory = {};
		for (const file of files) {
			const directory = file.directory || file.relative_path || "/";
			if (!filesByDirectory[directory]) {
				filesByDirectory[directory] = [];
			}
			filesByDirectory[directory].push(file);
		}

		// Sort directories
		const sortedDirectories = Object.keys(filesByDirectory).sort();

		sortedDirectories.forEach((directory, index) => {
			const directoryFiles = filesByDirectory[directory];
			const directoryName =
				directory === "/"
					? "Root Directory"
					: directory.split("/").pop() || directory;

			if (sortedDirectories.length > 1) {
				// Show directory as a collapsible folder if there are multiple directories
				filesHtml += `
					<li role="treeitem" aria-expanded="false">
						<span tabindex="0" data-type="folder" data-name="${ComponentUtils.escapeHtml(directoryName)}"
							  onclick="this.closest('li').setAttribute('aria-expanded', this.closest('li').getAttribute('aria-expanded') === 'false' ? 'true' : 'false');
							          this.querySelector('.folder-icon').className = this.closest('li').getAttribute('aria-expanded') === 'true' ? 'bi bi-folder2-open folder-icon' : 'bi bi-folder-fill folder-icon';
							          this.closest('li').querySelector('ul').style.display = this.closest('li').getAttribute('aria-expanded') === 'true' ? 'block' : 'none';"
							  style="cursor: pointer;">
							<div class="item-content">
								<i class="bi bi-folder-fill folder-icon" aria-hidden="true"></i> ${ComponentUtils.escapeHtml(directoryName)}
								<small class="text-muted ms-2">(${directoryFiles.length} file${directoryFiles.length !== 1 ? "s" : ""})</small>
							</div>
						</span>
						<ul role="group" style="display: none;">
				`;

				// Add individual files within this directory
				for (const file of directoryFiles) {
					const fileName = ComponentUtils.escapeHtml(
						file.name || "Unnamed File",
					);
					const fileUuid = ComponentUtils.escapeHtml(file.uuid || "");
					const fileExtension = fileName.includes(".")
						? fileName.split(".").pop().toLowerCase()
						: "";

					// Get appropriate icon based on file extension
					let fileIcon = "bi-file-earmark";
					switch (fileExtension) {
						case "pdf":
							fileIcon = "bi-file-earmark-pdf";
							break;
						case "json":
							fileIcon = "bi-file-earmark-code";
							break;
						case "csv":
						case "xlsx":
							fileIcon = "bi-file-earmark-spreadsheet";
							break;
						case "txt":
						case "md":
							fileIcon = "bi-file-earmark-text";
							break;
						case "zip":
						case "tar":
						case "gz":
							fileIcon = "bi-file-earmark-zip";
							break;
						case "bin":
						case "dat":
							fileIcon = "bi-file-earmark-binary";
							break;
						case "jpg":
						case "jpeg":
						case "png":
						case "gif":
							fileIcon = "bi-file-earmark-image";
							break;
						default:
							fileIcon = "bi-file-earmark";
					}

					filesHtml += `
						<li role="treeitem">
							<span tabindex="0" data-type="file" data-name="${fileName}" data-extension="${fileExtension}"
								  onclick="window.fileListController.modalManager.loadFileMetadata('${fileUuid}', '${fileName}')"
								  style="cursor: pointer;">
								<div class="item-content">
									<i class="bi ${fileIcon}" aria-hidden="true"></i> ${fileName}
									${file.size ? `<small class="text-muted ms-2">(${ComponentUtils.formatFileSize(file.size)})</small>` : ""}
								</div>
							</span>
							<!-- File metadata section (initially hidden) -->
							<div id="file-metadata-${fileUuid}" style="display: none; margin-left: 2rem; margin-top: 0.5rem; padding: 1rem; background-color: #f8f9fa; border-radius: 0.375rem;">
								<h6 class="mb-3"><i class="bi bi-info-circle me-2"></i>File Metadata</h6>
								<div class="metadata-content">
									<div class="d-flex justify-content-center py-2">
										<div class="spinner-border spinner-border-sm me-2" role="status">
											<span class="visually-hidden">Loading...</span>
										</div>
										<span class="text-muted">Click to load metadata...</span>
									</div>
								</div>
							</div>
						</li>
					`;
				}

				filesHtml += `
						</ul>
					</li>
				`;
			} else {
				// If there's only one directory, show files directly without folder structure
				for (const file of directoryFiles) {
					const fileName = ComponentUtils.escapeHtml(
						file.name || "Unnamed File",
					);
					const fileUuid = ComponentUtils.escapeHtml(file.uuid || "");
					const fileExtension = fileName.includes(".")
						? fileName.split(".").pop().toLowerCase()
						: "";

					// Get appropriate icon based on file extension
					let fileIcon = "bi-file-earmark";
					switch (fileExtension) {
						case "pdf":
							fileIcon = "bi-file-earmark-pdf";
							break;
						case "json":
							fileIcon = "bi-file-earmark-code";
							break;
						case "csv":
						case "xlsx":
							fileIcon = "bi-file-earmark-spreadsheet";
							break;
						case "txt":
						case "md":
							fileIcon = "bi-file-earmark-text";
							break;
						case "zip":
						case "tar":
						case "gz":
							fileIcon = "bi-file-earmark-zip";
							break;
						case "bin":
						case "dat":
							fileIcon = "bi-file-earmark-binary";
							break;
						case "jpg":
						case "jpeg":
						case "png":
						case "gif":
							fileIcon = "bi-file-earmark-image";
							break;
						default:
							fileIcon = "bi-file-earmark";
					}

					filesHtml += `
						<li role="treeitem">
							<span tabindex="0" data-type="file" data-name="${fileName}" data-extension="${fileExtension}"
								  onclick="window.fileListController.modalManager.loadFileMetadata('${fileUuid}', '${fileName}')"
								  style="cursor: pointer;">
								<div class="item-content">
									<i class="bi ${fileIcon}" aria-hidden="true"></i> ${fileName}
									${file.size ? `<small class="text-muted ms-2">(${ComponentUtils.formatFileSize(file.size)})</small>` : ""}
								</div>
							</span>
							<!-- File metadata section (initially hidden) -->
							<div id="file-metadata-${fileUuid}" style="display: none; margin-left: 2rem; margin-top: 0.5rem; padding: 1rem; background-color: #f8f9fa; border-radius: 0.375rem;">
								<h6 class="mb-3"><i class="bi bi-info-circle me-2"></i>File Metadata</h6>
								<div class="metadata-content">
									<div class="d-flex justify-content-center py-2">
										<div class="spinner-border spinner-border-sm me-2" role="status">
											<span class="visually-hidden">Loading...</span>
										</div>
										<span class="text-muted">Click to load metadata...</span>
									</div>
								</div>
							</div>
						</li>
					`;
				}
			}
		});

		filesHtml += `
				</ul>
			</div>
		`;

		// Add CSS for folder expand/collapse animation
		filesHtml += `
			<style>
				.file-browser [role="treeitem"][aria-expanded="false"] > ul {
					display: none;
				}
				.file-browser [role="treeitem"][aria-expanded="true"] > ul {
					display: block;
				}
				.file-browser [data-type="folder"] {
					cursor: pointer;
				}
				.file-browser [data-type="folder"]:hover {
					background-color: rgba(0, 0, 0, 0.05);
				}
				.file-browser [data-type="file"]:hover {
					background-color: rgba(0, 0, 0, 0.05);
				}
			</style>
		`;

		return filesHtml;
	}

	/**
	 * Format file metadata for display
	 */
	formatFileMetadata(file) {
		const metadata = [];

		// Primary file information - most useful for users
		if (file.size) {
			metadata.push(
				`<strong>Size:</strong> ${ComponentUtils.formatFileSize(file.size)} (${file.size.toLocaleString()} bytes)`,
			);
		}

		if (file.media_type) {
			metadata.push(
				`<strong>Media Type:</strong> ${ComponentUtils.escapeHtml(file.media_type)}`,
			);
		}

		if (file.created_at) {
			metadata.push(
				`<strong>Created:</strong> ${new Date(file.created_at).toLocaleString()}`,
			);
		}

		if (file.updated_at) {
			metadata.push(
				`<strong>Updated:</strong> ${new Date(file.updated_at).toLocaleString()}`,
			);
		}

		// File properties and attributes
		if (file.name) {
			metadata.push(
				`<strong>Name:</strong> ${ComponentUtils.escapeHtml(file.name)}`,
			);
		}

		if (file.directory || file.relative_path) {
			metadata.push(
				`<strong>Directory:</strong> ${ComponentUtils.escapeHtml(file.directory || file.relative_path)}`,
			);
		}

		// Removed permissions display
		// if (file.permissions) {
		// 	metadata.push(`<strong>Permissions:</strong> <span style="color: #005a9c; font-family: monospace;">${ComponentUtils.escapeHtml(file.permissions)}</span>`);
		// }

		if (file.owner?.username) {
			metadata.push(
				`<strong>Owner:</strong> ${ComponentUtils.escapeHtml(file.owner.username)}`,
			);
		}

		if (file.expiration_date) {
			metadata.push(
				`<strong>Expires:</strong> ${new Date(file.expiration_date).toLocaleDateString()}`,
			);
		}

		if (file.bucket_name) {
			metadata.push(
				`<strong>Storage Bucket:</strong> ${ComponentUtils.escapeHtml(file.bucket_name)}`,
			);
		}

		// Removed checksum display
		// if (file.sum_blake3) {
		// 	metadata.push(`<strong>Checksum:</strong> <span style="color: #005a9c; font-family: monospace;">${ComponentUtils.escapeHtml(file.sum_blake3)}</span>`);
		// }

		// Associated resources
		if (file.capture?.name) {
			metadata.push(
				`<strong>Associated Capture:</strong> ${ComponentUtils.escapeHtml(file.capture.name)}`,
			);
		}

		if (file.dataset?.name) {
			metadata.push(
				`<strong>Associated Dataset:</strong> ${ComponentUtils.escapeHtml(file.dataset.name)}`,
			);
		}

		// Additional metadata if available
		if (file.metadata && typeof file.metadata === "object") {
			for (const [key, value] of Object.entries(file.metadata)) {
				if (value !== null && value !== undefined) {
					const formattedKey = key
						.replace(/_/g, " ")
						.replace(/\b\w/g, (l) => l.toUpperCase());
					let formattedValue;

					// Format different types of values
					if (typeof value === "boolean") {
						formattedValue = value ? "Yes" : "No";
					} else if (typeof value === "number") {
						formattedValue = value.toLocaleString();
					} else if (typeof value === "object") {
						formattedValue = `<span style="color: #005a9c; font-family: monospace;">${JSON.stringify(value, null, 2)}</span>`;
					} else {
						formattedValue = ComponentUtils.escapeHtml(String(value));
					}

					metadata.push(`<strong>${formattedKey}:</strong> ${formattedValue}`);
				}
			}
		}

		if (metadata.length === 0) {
			return '<p class="text-muted mb-0">No metadata available for this file.</p>';
		}

		return `<div class="metadata-list">${metadata.join("<br>")}</div>`;
	}

	/**
	 * Get CSRF token for API requests
	 */
	getCSRFToken() {
		const token = document.querySelector("[name=csrfmiddlewaretoken]");
		return token ? token.value : "";
	}

	/**
	 * Load and display file metadata for a specific file in the modal
	 */
	async loadFileMetadata(fileUuid, fileName) {
		const fileMetadataSection = document.getElementById(
			`file-metadata-${fileUuid}`,
		);
		const metadataContent =
			fileMetadataSection?.querySelector(".metadata-content");

		if (!fileMetadataSection || !metadataContent) return;

		// Toggle visibility
		if (fileMetadataSection.style.display === "none") {
			fileMetadataSection.style.display = "block";

			// Check if metadata is already loaded
			if (metadataContent.innerHTML.includes("Click to load metadata...")) {
				// Show loading state
				metadataContent.innerHTML = `
					<div class="d-flex justify-content-center py-2">
						<div class="spinner-border spinner-border-sm me-2" role="status">
							<span class="visually-hidden">Loading...</span>
						</div>
						<span class="text-muted">Loading metadata...</span>
					</div>
				`;

				try {
					const response = await fetch(`/api/v1/assets/files/${fileUuid}/`, {
						method: "GET",
						headers: {
							"Content-Type": "application/json",
							"X-CSRFToken": this.getCSRFToken(),
						},
					});

					if (!response.ok) {
						throw new Error(`HTTP error! status: ${response.status}`);
					}

					const fileData = await response.json();

					// Format and display the metadata
					const formattedMetadata = this.formatFileMetadata(fileData);
					metadataContent.innerHTML = formattedMetadata;
				} catch (error) {
					console.error("Error loading file metadata:", error);
					metadataContent.innerHTML = `
						<div class="alert alert-warning mb-0">
							<i class="bi bi-exclamation-triangle me-2"></i>
							Failed to load metadata for ${ComponentUtils.escapeHtml(fileName)}.
							<br><small>Error: ${ComponentUtils.escapeHtml(error.message)}</small>
						</div>
					`;
				}
			}
		} else {
			fileMetadataSection.style.display = "none";
		}
	}
}

/**
 * PaginationManager - Handles pagination controls
 */
class PaginationManager {
	constructor(config) {
		this.containerId = config.containerId;
		this.container = document.getElementById(this.containerId);
		this.onPageChange = config.onPageChange;
	}

	update(pagination) {
		if (!this.container || !pagination) return;

		this.container.innerHTML = "";

		if (pagination.num_pages <= 1) return;

		const ul = document.createElement("ul");
		ul.className = "pagination justify-content-center";

		// Previous button
		if (pagination.has_previous) {
			ul.innerHTML += `
                <li class="page-item">
                    <a class="page-link" href="#" data-page="${pagination.number - 1}" aria-label="Previous">
                        <span aria-hidden="true">&laquo;</span>
                    </a>
                </li>
            `;
		}

		// Page numbers
		const startPage = Math.max(1, pagination.number - 2);
		const endPage = Math.min(pagination.num_pages, pagination.number + 2);

		for (let i = startPage; i <= endPage; i++) {
			ul.innerHTML += `
                <li class="page-item ${i === pagination.number ? "active" : ""}">
                    <a class="page-link" href="#" data-page="${i}">${i}</a>
                </li>
            `;
		}

		// Next button
		if (pagination.has_next) {
			ul.innerHTML += `
                <li class="page-item">
                    <a class="page-link" href="#" data-page="${pagination.number + 1}" aria-label="Next">
                        <span aria-hidden="true">&raquo;</span>
                    </a>
                </li>
            `;
		}

		this.container.appendChild(ul);

		// Add click handlers
		const links = ul.querySelectorAll("a.page-link");
		for (const link of links) {
			link.addEventListener("click", (e) => {
				e.preventDefault();
				const page = Number.parseInt(e.target.dataset.page);
				if (page && this.onPageChange) {
					this.onPageChange(page);
				}
			});
		}
	}
}

// Make classes available globally
window.ComponentUtils = ComponentUtils;
window.TableManager = TableManager;
window.CapturesTableManager = CapturesTableManager;
window.FilterManager = FilterManager;
window.SearchManager = SearchManager;
window.ModalManager = ModalManager;
window.PaginationManager = PaginationManager;

// Export classes for module use
if (typeof module !== "undefined" && module.exports) {
	module.exports = {
		ComponentUtils,
		TableManager,
		CapturesTableManager,
		FilterManager,
		SearchManager,
		ModalManager,
		PaginationManager,
	};
}
