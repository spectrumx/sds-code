/* Reusable Components for SDS Gateway */
/* Note: there seems to be some duplicated code between this file and file-list.js.
 * I'm leaving it here for now in case of conflicts with other work.
 * These files need some refactoring in the future.
 */
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

	handleSort(field) {
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
		this.updateURL({ sort_by: field, sort_order: newOrder });
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

	updateTable(data, hasResults) {
		if (!this.tbody) return;

		if (!hasResults || !data || data.length === 0) {
			this.tbody.innerHTML = `
                <tr>
                    <td colspan="9" class="text-center text-muted py-4">No results found.</td>
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
	}

	renderRow(capture, index) {
		// Handle composite vs single capture display
		let channelDisplay = capture.channel || "";
		let typeDisplay = capture.capture_type || "";

		if (capture.is_multi_channel) {
			// For composite captures, show all channels
			if (capture.channels && Array.isArray(capture.channels)) {
				channelDisplay = capture.channels
					.map((ch) => ch.channel || ch)
					.join(", ");
			}
			typeDisplay = capture.capture_type_display || capture.capture_type || "";
		}

		return `
            <tr class="capture-row" data-clickable="true" data-uuid="${capture.uuid || ""}">
                <th scope="row">${index + 1}</th>
                <td>
                    <a href="#" class="capture-link"
                       data-uuid="${capture.uuid || ""}"
                       data-channel="${capture.channel || ""}"
                       data-scan-group="${capture.scan_group || ""}"
                       data-capture-type="${capture.capture_type || ""}"
                       data-top-level-dir="${capture.top_level_dir || ""}"
                       data-created-at="${capture.created_at || ""}"
                       data-is-multi-channel="${capture.is_multi_channel || false}"
                       data-channels="${capture.channels ? JSON.stringify(capture.channels) : ""}"
                       aria-label="View details for ${capture.uuid || "unknown capture"}">
                        ${capture.uuid || ""}
                    </a>
                </td>
                <td>${channelDisplay}</td>
                <td>${capture.created_at ? this.formatDate(capture.created_at) : ""}</td>
                <td>${typeDisplay}</td>
                <td>${capture.files_count || "0"}</td>
                <td>${capture.center_frequency_ghz ? `${capture.center_frequency_ghz.toFixed(3)} GHz` : "-"}</td>
                <td>${capture.sample_rate_mhz ? `${capture.sample_rate_mhz.toFixed(1)} MHz` : "-"}</td>
            </tr>
        `;
	}

	formatDate(dateString) {
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
	}

	attachRowClickHandlers() {
		super.attachRowClickHandlers();

		// Attach specific handlers for capture links
		const captureLinks = this.tbody?.querySelectorAll(".capture-link");
		for (const link of captureLinks || []) {
			link.addEventListener("click", (e) => {
				e.preventDefault();
				if (this.modalHandler) {
					this.modalHandler.openCaptureModal(link);
				}
			});
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

		const data = linkElement.dataset;
		// Check if this is a composite capture
		const isComposite =
			data.isMultiChannel === "true" || data.isMultiChannel === "True";

		let content = `
            <div class="row">
                <div class="col-sm-4"><strong>UUID:</strong></div>
                <div class="col-sm-8"><code>${data.uuid || "N/A"}</code></div>
            </div>
            <div class="row">
            <div class="row">
                <div class="col-sm-4"><strong>${isComposite ? "Channels:" : "Channel:"}</strong></div>
                <div class="col-sm-8">${data.channel || "N/A"}</div>
            </div>
            <div class="row">
                <div class="col-sm-4"><strong>Scan Group:</strong></div>
                <div class="col-sm-8">${data.scanGroup || "N/A"}</div>
            </div>
            <div class="row">
                <div class="col-sm-4"><strong>Directory:</strong></div>
                <div class="col-sm-8"><code>${data.topLevelDir || "N/A"}</code></div>
            </div>
            <div class="row">
                <div class="col-sm-4"><strong>Created:</strong></div>
                <div class="col-sm-8">${data.createdAt ? new Date(data.createdAt).toLocaleString() : "N/A"}</div>
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
					content += `
						<div class="row mt-3">
							<div class="col-12">
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

						content += `
							<div class="accordion-item">
								<h2 class="accordion-header" id="heading-${channelId}">
									<button class="accordion-button ${i === 0 ? "" : "collapsed"}" type="button"
											data-bs-toggle="collapse"
											data-bs-target="#collapse-${channelId}"
											aria-expanded="${i === 0 ? "true" : "false"}"
											aria-controls="collapse-${channelId}">
										<strong>${channel.channel || "N/A"}</strong>
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

					content += `
								</div>
							</div>
						</div>
					`;
				}
			} catch (e) {
				console.warn("Could not parse channels data:", e);
			}
		}

		const title = `Capture Details - ${data.channel || "Unknown"}`;
		this.show(title, content);
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
window.TableManager = TableManager;
window.CapturesTableManager = CapturesTableManager;
window.FilterManager = FilterManager;
window.SearchManager = SearchManager;
window.ModalManager = ModalManager;
window.PaginationManager = PaginationManager;

// Export classes for module use
if (typeof module !== "undefined" && module.exports) {
	module.exports = {
		TableManager,
		CapturesTableManager,
		FilterManager,
		SearchManager,
		ModalManager,
		PaginationManager,
	};
}
