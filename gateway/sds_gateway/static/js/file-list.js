/* File List Page JavaScript - Refactored to use Components */

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

		// Initialize dropdowns for any existing static dropdowns
		this.initializeDropdowns();
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
			modalId: "capture-modal",
			modalBodyId: "capture-modal-body",
			modalTitleId: "capture-modal-label",
		});

		this.tableManager = new FileListCapturesTableManager({
			tableId: "captures-table",
			loadingIndicatorId: "loading-indicator",
			tableContainerSelector: ".table-responsive",
			resultsCountId: "results-count",
			modalHandler: this.modalManager,
			dropdownInitializer: () => this.initializeDropdowns(),
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
				// Reset classes
				icon.className = "bi sort-icon";

				if (currentSort === sortField) {
					// Add active class and appropriate direction icon
					icon.classList.add("active");
					if (currentOrder === "desc") {
						icon.classList.add("bi-caret-down-fill");
					} else {
						icon.classList.add("bi-caret-up-fill");
					}
				} else {
					// Inactive columns get default down arrow
					icon.classList.add("bi-caret-down-fill");
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
		// Get current URL parameters
		const urlParams = new URLSearchParams(window.location.search);
		const currentSearch = urlParams.get("search");

		// Reset all filter inputs except search
		if (this.elements.startDate) this.elements.startDate.value = "";
		if (this.elements.endDate) this.elements.endDate.value = "";
		if (this.elements.centerFreqMin) this.elements.centerFreqMin.value = "";
		if (this.elements.centerFreqMax) this.elements.centerFreqMax.value = "";

		// Reset interaction tracking
		this.userInteractedWithFrequency = false;

		// Reset frequency slider if it exists
		if (window.frequencyRangeSlider?.noUiSlider) {
			window.frequencyRangeSlider.noUiSlider.set([0, 10]);
		}

		// Create new URL parameters with only search and sort parameters preserved
		const newParams = new URLSearchParams();
		if (currentSearch) {
			newParams.set("search", currentSearch);
		}
		newParams.set("sort_by", this.currentSortBy);
		newParams.set("sort_order", this.currentSortOrder);

		// Update URL and trigger search
		window.history.pushState(
			{},
			"",
			`${window.location.pathname}?${newParams.toString()}`,
		);
		this.performSearch();
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

	/**
	 * Initialize dropdowns with body container for proper positioning
	 */
	initializeDropdowns() {
		const dropdownButtons = document.querySelectorAll(".btn-icon-dropdown");

		if (dropdownButtons.length === 0) {
			return;
		}

		dropdownButtons.forEach((toggle, index) => {
			// Check if dropdown is already initialized
			if (toggle._dropdown) {
				return;
			}

			const dropdown = new bootstrap.Dropdown(toggle, {
				container: "body",
				boundary: "viewport",
				popperConfig: {
					modifiers: [
						{
							name: "preventOverflow",
							options: {
								boundary: "viewport",
							},
						},
					],
				},
			});

			// Manually move dropdown to body when shown
			toggle.addEventListener("show.bs.dropdown", () => {
				const dropdownMenu = toggle.nextElementSibling;
				if (dropdownMenu?.classList.contains("dropdown-menu")) {
					document.body.appendChild(dropdownMenu);
				}
			});
		});
	}
}

/**
 * Enhanced CapturesTableManager for file list specific functionality
 * Extends the base CapturesTableManager from components.js
 */
class FileListCapturesTableManager extends CapturesTableManager {
	constructor(options) {
		super(options);
		this.resultsCountElement = document.getElementById(options.resultsCountId);
		this.dropdownInitializer = options.dropdownInitializer;
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

		// Initialize dropdowns with body container after table is updated
		if (this.dropdownInitializer) {
			this.dropdownInitializer();
		}
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
	 * Overrides the base class method to include file-specific columns
	 */
	renderRow(capture, index) {
		// Sanitize all data before rendering
		const safeData = {
			uuid: ComponentUtils.escapeHtml(capture.uuid || ""),
			name: ComponentUtils.escapeHtml(capture.name || ""),
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

		// Handle author display with proper fallback
		let authorDisplay = "-";
		if (capture.owner) {
			if (typeof capture.owner === "string") {
				// Handle string format (email or name)
				authorDisplay = ComponentUtils.escapeHtml(capture.owner);
			} else if (capture.owner.name) {
				// Handle object format with name
				authorDisplay = ComponentUtils.escapeHtml(capture.owner.name);
			} else if (capture.owner.email) {
				// Handle object format with email fallback
				authorDisplay = ComponentUtils.escapeHtml(capture.owner.email);
			}
		}

		// Display name with fallback to "Unnamed Capture"
		const nameDisplay = safeData.name || "Unnamed Capture";

		return `
			<tr class="capture-row" data-clickable="true" data-uuid="${safeData.uuid}">
				<td>
					<a href="#" class="capture-link"
					   data-uuid="${safeData.uuid}"
					   data-name="${safeData.name}"
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
					   aria-label="View details for ${nameDisplay}">
						${nameDisplay}
					</a>
				</td>
				<td>${channelDisplay}</td>
				<td class="text-nowrap">
					${window.ComponentUtils.formatDateForModal(capture.capture?.created_at || capture.created_at)}
				</td>
				<td>${typeDisplay}</td>
				<td>${authorDisplay}</td>
				<td>${capture.center_frequency_ghz ? `${capture.center_frequency_ghz.toFixed(3)} GHz` : "-"}</td>
				<td>${capture.sample_rate_mhz ? `${capture.sample_rate_mhz.toFixed(1)} MHz` : "-"}</td>
				<td class="text-center">
					<div class="dropdown">
						<button class="btn btn-sm btn-light dropdown-toggle btn-icon-dropdown d-flex align-items-center justify-content-center mx-auto"
								type="button"
								data-bs-toggle="dropdown"
								data-bs-boundary="viewport"
								aria-expanded="false"
								aria-label="Actions for capture ${nameDisplay}"
								style="width: 32px; height: 32px; padding: 0;">
							<i class="bi bi-three-dots-vertical"></i>
						</button>
						<ul class="dropdown-menu">
							<li>
								<button class="dropdown-item capture-details-btn"
										type="button"
										data-uuid="${safeData.uuid}"
										data-name="${safeData.name}"
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
										data-channels="${capture.channels ? JSON.stringify(capture.channels) : ""}">
									Edit
								</button>
							</li>
							<li>
								<button class="dropdown-item download-capture-btn"
										type="button"
										data-capture-uuid="${safeData.uuid}"
										data-capture-name="${safeData.name}">
									Download
								</button>
							</li>
						</ul>
					</div>
				</td>
			</tr>
		`;
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
