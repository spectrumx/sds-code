/* File List Page JavaScript - Refactored with Components */

/**
 * Utility functions for security and common operations
 */
const FileListUtils = {
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
	 * Formats date for display
	 * @param {string} dateString - ISO date string
	 * @returns {string} Formatted date
	 */
	formatDate(dateString) {
		if (!dateString) return "";
		const date = new Date(dateString);
		return date.toString() !== "Invalid Date"
			? date.toLocaleDateString("en-US", {
					month: "2-digit",
					day: "2-digit",
					year: "numeric",
				})
			: "";
	},
};

/**
 * Configuration constants
 */
const CONFIG = {
	DEBOUNCE_DELAY: 300,
	DEFAULT_SORT_BY: "created_at",
	DEFAULT_SORT_ORDER: "desc",
	ELEMENT_IDS: {
		SEARCH_INPUT: "search-input",
		START_DATE: "start_date",
		END_DATE: "end_date",
		CENTER_FREQ_MIN: "centerFreqMinInput",
		CENTER_FREQ_MAX: "centerFreqMaxInput",
		APPLY_FILTERS: "apply-filters-btn",
		CLEAR_FILTERS: "clear-filters-btn",
		ITEMS_PER_PAGE: "items-per-page",
	},
};

/**
 * Main controller class for the file list page
 */
class FileListController {
	constructor() {
		this.userInteractedWithFrequency = false;
		this.urlParams = new URLSearchParams(window.location.search);
		this.currentSortBy =
			this.urlParams.get("sort_by") || CONFIG.DEFAULT_SORT_BY;
		this.currentSortOrder =
			this.urlParams.get("sort_order") || CONFIG.DEFAULT_SORT_ORDER;

		// Cache DOM elements
		this.cacheElements();

		// Initialize components
		this.initializeComponents();

		// Initialize functionality
		this.initializeEventHandlers();
		this.initializeFromURL();

		// Initial setup
		this.updateSortIcons();
		this.tableManager.attachRowClickHandlers();
	}

	/**
	 * Cache frequently accessed DOM elements
	 */
	cacheElements() {
		this.elements = {
			searchInput: document.getElementById(CONFIG.ELEMENT_IDS.SEARCH_INPUT),
			startDate: document.getElementById(CONFIG.ELEMENT_IDS.START_DATE),
			endDate: document.getElementById(CONFIG.ELEMENT_IDS.END_DATE),
			centerFreqMin: document.getElementById(
				CONFIG.ELEMENT_IDS.CENTER_FREQ_MIN,
			),
			centerFreqMax: document.getElementById(
				CONFIG.ELEMENT_IDS.CENTER_FREQ_MAX,
			),
			applyFilters: document.getElementById(CONFIG.ELEMENT_IDS.APPLY_FILTERS),
			clearFilters: document.getElementById(CONFIG.ELEMENT_IDS.CLEAR_FILTERS),
			itemsPerPage: document.getElementById(CONFIG.ELEMENT_IDS.ITEMS_PER_PAGE),
			sortableHeaders: document.querySelectorAll("th.sortable"),
			frequencyButton: document.querySelector(
				'[data-bs-target="#collapseFrequency"]',
			),
			frequencyCollapse: document.getElementById("collapseFrequency"),
			dateButton: document.querySelector('[data-bs-target="#collapseDate"]'),
			dateCollapse: document.getElementById("collapseDate"),
		};
	}

	/**
	 * Initialize component managers
	 */
	initializeComponents() {
		this.modalManager = new ModalManager({
			modalId: "channelModal",
			modalBodyId: "channelModalBody",
			modalTitleId: "channelModalLabel",
		});

		this.tableManager = new FileListCapturesTableManager({
			tableId: "captures-table",
			loadingIndicatorId: "loading-indicator",
			tableContainerSelector: ".table-responsive",
			resultsCountId: "results-count",
			modalHandler: this.modalManager,
		});

		this.searchManager = new SearchManager({
			searchInputId: CONFIG.ELEMENT_IDS.SEARCH_INPUT,
			searchButtonId: "search-btn",
			clearButtonId: "reset-search-btn",
			searchFormId: "search-form",
			onSearch: () => this.performSearch(),
			debounceDelay: CONFIG.DEBOUNCE_DELAY,
		});

		this.paginationManager = new PaginationManager({
			containerId: "captures-pagination",
			onPageChange: (page) => this.handlePageChange(page),
		});
	}

	/**
	 * Initialize all event handlers
	 */
	initializeEventHandlers() {
		this.initializeTableSorting();
		this.initializeAccordions();
		this.initializeFrequencyHandling();
		this.initializeItemsPerPageHandler();
	}

	/**
	 * Initialize values from URL parameters
	 */
	initializeFromURL() {
		// Set initial date values from URL
		if (this.urlParams.get("date_start") && this.elements.startDate) {
			this.elements.startDate.value = this.urlParams.get("date_start");
		}
		if (this.urlParams.get("date_end") && this.elements.endDate) {
			this.elements.endDate.value = this.urlParams.get("date_end");
		}

		// Set frequency values if they exist in URL
		this.initializeFrequencyFromURL();
	}

	/**
	 * Handle page change events
	 */
	handlePageChange(page) {
		const urlParams = new URLSearchParams(window.location.search);
		urlParams.set("page", page.toString());
		window.location.search = urlParams.toString();
	}

	/**
	 * Build search parameters from form inputs
	 */
	buildSearchParams() {
		const searchParams = new URLSearchParams();

		const searchQuery = this.elements.searchInput?.value.trim() || "";
		const startDate = this.elements.startDate?.value || "";
		let endDate = this.elements.endDate?.value || "";

		// If end date is set, include the full day
		if (endDate) {
			endDate = `${endDate}T23:59:59`;
		}

		// Add search parameters
		if (searchQuery) searchParams.set("search", searchQuery);
		if (startDate) searchParams.set("date_start", startDate);
		if (endDate) searchParams.set("date_end", endDate);

		// Only add frequency parameters if user has explicitly interacted
		if (this.userInteractedWithFrequency) {
			if (this.elements.centerFreqMin?.value) {
				searchParams.set("min_freq", this.elements.centerFreqMin.value);
			}
			if (this.elements.centerFreqMax?.value) {
				searchParams.set("max_freq", this.elements.centerFreqMax.value);
			}
		}

		searchParams.set("sort_by", this.currentSortBy);
		searchParams.set("sort_order", this.currentSortOrder);

		return searchParams;
	}

	/**
	 * Execute search API call
	 */
	async executeSearch(searchParams) {
		const apiUrl = `${window.location.pathname.replace(/\/$/, "")}/api/?${searchParams.toString()}`;

		const response = await fetch(apiUrl, {
			method: "GET",
			headers: {
				Accept: "application/json",
			},
			credentials: "same-origin",
		});

		if (!response.ok) {
			throw new Error(`HTTP ${response.status}: ${response.statusText}`);
		}

		const text = await response.text();
		try {
			return JSON.parse(text);
		} catch (e) {
			throw new Error("Invalid JSON response from server");
		}
	}

	/**
	 * Update UI with search results
	 */
	updateUI(data) {
		if (data.error) {
			throw new Error(`Server error: ${data.error}`);
		}

		this.tableManager.updateTable(data.captures || [], data.has_results);
	}

	/**
	 * Update browser history without page refresh
	 */
	updateBrowserHistory(searchParams) {
		const newUrl = `${window.location.pathname}?${searchParams.toString()}`;
		window.history.pushState({}, "", newUrl);
	}

	/**
	 * Main search function - now broken down into smaller methods
	 */
	async performSearch() {
		try {
			this.tableManager.showLoading();

			const searchParams = this.buildSearchParams();
			const data = await this.executeSearch(searchParams);
			this.updateUI(data);
			this.updateBrowserHistory(searchParams);
		} catch (error) {
			console.error("Search error:", error);
			this.tableManager.showError(`Search failed: ${error.message}`);
		} finally {
			this.tableManager.hideLoading();
		}
	}

	/**
	 * Initialize table sorting functionality
	 */
	initializeTableSorting() {
		if (!this.elements.sortableHeaders) return;

		for (const header of this.elements.sortableHeaders) {
			header.style.cursor = "pointer";
			header.addEventListener("click", () => this.handleSort(header));
		}
	}

	/**
	 * Handle sort click events
	 */
	handleSort(header) {
		try {
			const sortField = header.getAttribute("data-sort");
			const currentSort = this.urlParams.get("sort_by");
			const currentOrder = this.urlParams.get("sort_order") || "desc";

			// Determine new sort order
			let newOrder = "asc";
			if (currentSort === sortField && currentOrder === "asc") {
				newOrder = "desc";
			}

			// Build new URL with sort parameters
			const urlParams = new URLSearchParams(window.location.search);
			urlParams.set("sort_by", sortField);
			urlParams.set("sort_order", newOrder);
			urlParams.set("page", "1");

			// Navigate to sorted results
			window.location.search = urlParams.toString();
		} catch (error) {
			console.error("Error handling sort:", error);
		}
	}

	/**
	 * Update sort icons to show current sort state
	 */
	updateSortIcons() {
		if (!this.elements.sortableHeaders) return;

		const currentSort = this.urlParams.get("sort_by") || CONFIG.DEFAULT_SORT_BY;
		const currentOrder = this.urlParams.get("sort_order") || "desc";

		for (const header of this.elements.sortableHeaders) {
			const sortField = header.getAttribute("data-sort");
			const icon = header.querySelector(".sort-icon");

			if (icon) {
				if (currentSort === sortField) {
					if (currentOrder === "desc") {
						icon.className = "bi bi-sort-down sort-icon";
					} else {
						icon.className = "bi bi-sort-up sort-icon";
					}
				} else {
					icon.className = "bi bi-arrow-down-up sort-icon";
				}
			}
		}
	}

	/**
	 * Initialize accordion behavior
	 */
	initializeAccordions() {
		// Frequency filter accordion
		if (this.elements.frequencyButton && this.elements.frequencyCollapse) {
			this.elements.frequencyButton.addEventListener("click", (e) => {
				e.preventDefault();
				this.toggleAccordion(
					this.elements.frequencyButton,
					this.elements.frequencyCollapse,
				);
			});
		}

		// Date filter accordion
		if (this.elements.dateButton && this.elements.dateCollapse) {
			this.elements.dateButton.addEventListener("click", (e) => {
				e.preventDefault();
				this.toggleAccordion(
					this.elements.dateButton,
					this.elements.dateCollapse,
				);
			});
		}
	}

	/**
	 * Helper function to toggle accordion state
	 */
	toggleAccordion(button, collapse) {
		const isCollapsed = button.classList.contains("collapsed");

		if (isCollapsed) {
			button.classList.remove("collapsed");
			button.setAttribute("aria-expanded", "true");
			collapse.classList.add("show");
		} else {
			button.classList.add("collapsed");
			button.setAttribute("aria-expanded", "false");
			collapse.classList.remove("show");
		}
	}

	/**
	 * Initialize frequency handling
	 */
	initializeFrequencyHandling() {
		// Add event listeners to track user interaction with frequency inputs
		if (this.elements.centerFreqMin) {
			this.elements.centerFreqMin.addEventListener("change", () => {
				this.userInteractedWithFrequency = true;
			});
		}

		if (this.elements.centerFreqMax) {
			this.elements.centerFreqMax.addEventListener("change", () => {
				this.userInteractedWithFrequency = true;
			});
		}

		// Apply filters button
		if (this.elements.applyFilters) {
			this.elements.applyFilters.addEventListener("click", (e) => {
				e.preventDefault();
				this.performSearch();
			});
		}

		// Clear filters button
		if (this.elements.clearFilters) {
			this.elements.clearFilters.addEventListener("click", (e) => {
				e.preventDefault();
				this.clearAllFilters();
			});
		}
	}

	/**
	 * Clear all filter inputs
	 */
	clearAllFilters() {
		// Reset all filter inputs
		if (this.elements.searchInput) this.elements.searchInput.value = "";
		if (this.elements.startDate) this.elements.startDate.value = "";
		if (this.elements.endDate) this.elements.endDate.value = "";
		if (this.elements.centerFreqMin) this.elements.centerFreqMin.value = "";
		if (this.elements.centerFreqMax) this.elements.centerFreqMax.value = "";

		// Reset interaction tracking
		this.userInteractedWithFrequency = false;

		// Redirect to base URL to show original table state
		window.location.href = window.location.pathname;
	}

	/**
	 * Initialize items per page handler
	 */
	initializeItemsPerPageHandler() {
		if (this.elements.itemsPerPage) {
			this.elements.itemsPerPage.addEventListener("change", (e) => {
				const urlParams = new URLSearchParams(window.location.search);
				urlParams.set("items_per_page", e.target.value);
				urlParams.set("page", "1");
				window.location.search = urlParams.toString();
			});
		}
	}

	/**
	 * Initialize frequency range from URL parameters
	 */
	initializeFrequencyFromURL() {
		if (!this.elements.centerFreqMin || !this.elements.centerFreqMax) return;

		const minFreq = Number.parseFloat(this.urlParams.get("min_freq"));
		const maxFreq = Number.parseFloat(this.urlParams.get("max_freq"));

		if (!Number.isNaN(minFreq)) {
			this.elements.centerFreqMin.value = minFreq;
			this.userInteractedWithFrequency = true;
		}
		if (!Number.isNaN(maxFreq)) {
			this.elements.centerFreqMax.value = maxFreq;
			this.userInteractedWithFrequency = true;
		}

		// Update noUiSlider if it exists
		if (this.userInteractedWithFrequency) {
			this.initializeFrequencySlider();
		}
	}

	initializeFrequencySlider() {
		try {
			const frequencyRangeSlider = document.getElementById(
				"frequency-range-slider",
			);
			if (frequencyRangeSlider?.noUiSlider) {
				const currentValues = frequencyRangeSlider.noUiSlider.get();
				const newMin = !Number.isNaN(minFreq)
					? minFreq
					: Number.parseFloat(currentValues[0]);
				const newMax = !Number.isNaN(maxFreq)
					? maxFreq
					: Number.parseFloat(currentValues[1]);

				frequencyRangeSlider.noUiSlider.set([newMin, newMax]);
			}
		} catch (error) {
			console.error("Error initializing frequency slider:", error);
		}
	}
}

/**
 * Enhanced CapturesTableManager for file list specific functionality
 */
class FileListCapturesTableManager extends CapturesTableManager {
	constructor(options) {
		super(options);
		this.resultsCountElement = document.getElementById(options.resultsCountId);
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
	 * Update table with new data
	 */
	updateTable(captures, hasResults) {
		const tbody = document.querySelector("tbody");
		if (!tbody) return;

		// Update results count
		this.updateResultsCount(captures, hasResults);

		if (!hasResults || captures.length === 0) {
			tbody.innerHTML = `
				<tr>
					<td colspan="8" class="text-center text-muted py-4">No captures found.</td>
				</tr>
			`;
			return;
		}

		// Build table HTML efficiently
		const tableHTML = captures
			.map((capture, index) => this.renderRow(capture, index))
			.join("");
		tbody.innerHTML = tableHTML;
	}

	/**
	 * Update results count display
	 */
	updateResultsCount(captures, hasResults) {
		if (this.resultsCountElement) {
			const count = hasResults && captures ? captures.length : 0;
			const pluralSuffix = count === 1 ? "" : "s";
			this.resultsCountElement.textContent = `${count} capture${pluralSuffix} found`;
		}
	}

	/**
	 * Render individual table row with XSS protection
	 */
	renderRow(capture, index) {
		// Sanitize all data before rendering
		const safeData = {
			uuid: FileListUtils.escapeHtml(capture.uuid || ""),
			channel: FileListUtils.escapeHtml(capture.channel || ""),
			scanGroup: FileListUtils.escapeHtml(capture.scan_group || ""),
			captureType: FileListUtils.escapeHtml(capture.capture_type || ""),
			topLevelDir: FileListUtils.escapeHtml(capture.top_level_dir || ""),
			indexName: FileListUtils.escapeHtml(capture.index_name || ""),
			owner: FileListUtils.escapeHtml(capture.owner || ""),
			origin: FileListUtils.escapeHtml(capture.origin || ""),
			dataset: FileListUtils.escapeHtml(capture.dataset || ""),
			createdAt: FileListUtils.escapeHtml(capture.created_at || ""),
			updatedAt: FileListUtils.escapeHtml(capture.updated_at || ""),
			isPublic: FileListUtils.escapeHtml(capture.is_public || ""),
			isDeleted: FileListUtils.escapeHtml(capture.is_deleted || ""),
			centerFrequencyGhz: FileListUtils.escapeHtml(
				capture.center_frequency_ghz || "",
			),
		};

		return `
			<tr class="capture-row">
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
					   aria-label="View details for ${safeData.uuid || "unknown capture"}">
						${safeData.uuid}
					</a>
				</td>
				<td>${safeData.channel}</td>
				<td>${FileListUtils.formatDate(capture.created_at)}</td>
				<td>${safeData.captureType}</td>
				<td>${capture.files_count || "0"}${capture.total_file_size ? ` / ${FileListUtils.formatFileSize(capture.total_file_size)}` : ""}</td>
				<td>${capture.center_frequency_ghz ? `${capture.center_frequency_ghz.toFixed(3)} GHz` : "-"}</td>
				<td>${capture.sample_rate_mhz ? `${capture.sample_rate_mhz.toFixed(1)} MHz` : "-"}</td>
				<td>
					<div class="dropdown">
						<button class="btn btn-sm btn-light dropdown-toggle btn-icon-dropdown" type="button" data-bs-toggle="dropdown" aria-expanded="false" aria-label="Actions for ${safeData.uuid || "unknown capture"}">
							<i class="bi bi-three-dots-vertical" aria-hidden="true"></i>
						</button>
						<ul class="dropdown-menu">
							<li><button class="dropdown-item view-capture-btn" type="button"
								   data-uuid="${safeData.uuid}"
								   data-channel="${safeData.channel}"
								   data-scan-group="${safeData.scanGroup}"
								   data-capture-type="${safeData.captureType}"
								   data-top-level-dir="${safeData.topLevelDir}"
								   data-owner="${safeData.owner}"
								   data-origin="${safeData.origin}"
								   data-dataset="${safeData.dataset}"
								   data-created-at="${safeData.createdAt}"
								   data-updated-at="${safeData.updatedAt}"
								   data-is-public="${safeData.isPublic}"
								   data-center-frequency-ghz="${safeData.centerFrequencyGhz}">View</button></li>
							<li><button class="dropdown-item" type="button">Download</button></li>
						</ul>
					</div>
				</td>
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
	openCaptureModal(link) {
		try {
			// Get all data attributes from the link with sanitization
			const data = {
				uuid: FileListUtils.escapeHtml(link.getAttribute("data-uuid") || ""),
				channel: FileListUtils.escapeHtml(
					link.getAttribute("data-channel") || "",
				),
				scanGroup: FileListUtils.escapeHtml(
					link.getAttribute("data-scan-group") || "",
				),
				captureType: FileListUtils.escapeHtml(
					link.getAttribute("data-capture-type") || "",
				),
				topLevelDir: FileListUtils.escapeHtml(
					link.getAttribute("data-top-level-dir") || "",
				),
				owner: FileListUtils.escapeHtml(link.getAttribute("data-owner") || ""),
				origin: FileListUtils.escapeHtml(
					link.getAttribute("data-origin") || "",
				),
				dataset: FileListUtils.escapeHtml(
					link.getAttribute("data-dataset") || "",
				),
				createdAt: link.getAttribute("data-created-at") || "",
				updatedAt: link.getAttribute("data-updated-at") || "",
				isPublic: link.getAttribute("data-is-public") || "",
				centerFrequencyGhz:
					link.getAttribute("data-center-frequency-ghz") || "",
			};

			// Parse owner field safely
			const ownerDisplay = data.owner
				? data.owner.split("'").find((part) => part.includes("@")) || "N/A"
				: "N/A";

			const modalContent = `
				<div class="mb-4">
					<h6>Basic Information</h6>
					<p><strong>UUID:</strong> ${data.uuid || "N/A"}</p>
					<p><strong>Channel:</strong> ${data.channel || "N/A"}</p>
					<p><strong>Capture Type:</strong> ${data.captureType || "N/A"}</p>
					<p><strong>Origin:</strong> ${data.origin || "N/A"}</p>
					<p><strong>Owner:</strong> ${ownerDisplay}</p>
				</div>
				<div class="mb-4">
					<h6>Technical Details</h6>
					<p><strong>Scan Group:</strong> ${data.scanGroup || "N/A"}</p>
					<p><strong>Top Level Directory:</strong> ${data.topLevelDir || "N/A"}</p>
					<p><strong>Dataset:</strong> ${data.dataset || "N/A"}</p>
					<p><strong>Center Frequency:</strong> ${data.centerFrequencyGhz && data.centerFrequencyGhz !== "None" ? `${Number.parseFloat(data.centerFrequencyGhz).toFixed(3)} GHz` : "N/A"}</p>
					<p><strong>Is Public:</strong> ${data.isPublic === "True" ? "Yes" : "No"}</p>
				</div>
				<div>
					<h6>Timestamps</h6>
					<p><strong>Created At:</strong> ${data.createdAt && data.createdAt !== "None" ? `${new Date(data.createdAt).toLocaleString()} UTC` : "N/A"}</p>
					<p><strong>Updated At:</strong> ${data.updatedAt && data.updatedAt !== "None" ? `${new Date(data.updatedAt).toLocaleString()} UTC` : "N/A"}</p>
				</div>
			`;

			const title = `Capture Details - ${data.channel || "Unknown"}`;
			this.modalHandler.show(title, modalContent);
		} catch (error) {
			console.error("Error opening capture modal:", error);
			this.showError("Error displaying capture details");
		}
	}

	/**
	 * Show error message with improved styling
	 */
	showError(message) {
		const tbody = document.querySelector("tbody");
		if (tbody) {
			tbody.innerHTML = `
				<tr>
					<td colspan="8" class="text-center text-danger py-4">
						<i class="fas fa-exclamation-triangle"></i> ${FileListUtils.escapeHtml(message)}
						<br><small class="text-muted">Try refreshing the page or contact support if the problem persists.</small>
					</td>
				</tr>
			`;
		}
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

// Expose frequency slider initialization function globally for backward compatibility
window.initializeFrequencySlider = () => {
	// This function is called from the template
	if (window.fileListController) {
		window.fileListController.initializeFrequencyFromURL();
	}
};

// Initialize the application when DOM is loaded
document.addEventListener("DOMContentLoaded", () => {
	try {
		window.fileListController = new FileListController();
	} catch (error) {
		console.error("Error initializing file list controller:", error);
	}
});
