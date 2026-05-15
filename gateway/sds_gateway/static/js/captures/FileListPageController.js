/**
 * Orchestrates capture list page (file list).
 * Migrated from deprecated/file-list.js (FileListController).
 */

// Ensure PageController base exists before class declaration (Jest/CommonJS).
if (typeof window !== "undefined" && !window.PageController && typeof require !== "undefined") {
	try {
		// eslint-disable-next-line global-require, import/no-dynamic-require
		const mod = require("../core/PageController.js");
		if (mod?.PageController) window.PageController = mod.PageController;
	} catch (_) {}
}

// Support both browser globals and CommonJS.
const PageControllerBase =
	(typeof window !== "undefined" && window.PageController) ||
	(typeof PageController !== "undefined" ? PageController : null);

function ensureFileListConfig() {
	if (typeof window === "undefined") return;
	if (window.FileListConfig) return;

	// In Jest/node, the config module is available via CommonJS exports.
	if (typeof require !== "undefined") {
		try {
			// eslint-disable-next-line global-require, import/no-dynamic-require
			const mod = require("../constants/FileListConfig.js");
			if (mod?.FileListConfig) {
				window.FileListConfig = mod.FileListConfig;
				return;
			}
		} catch (_) {}
	}

	// Final fallback: defaults (should be overridden by constants/FileListConfig.js in browser).
	window.FileListConfig = {
		DEBOUNCE_DELAY: 500,
		DEFAULT_SORT_BY: "created_at",
		DEFAULT_SORT_ORDER: "desc",
		MIN_LOADING_TIME: 500,
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
}

class FileListPageController extends (PageControllerBase || class {}) {
	constructor() {
		super();
		ensureFileListConfig();
		this.selectedCaptureIds = new Set();
		this.userInteractedWithFrequency = false;
		this.urlParams = new URLSearchParams(window.location.search);
		this.currentSortBy =
			this.urlParams.get("sort_by") || window.FileListConfig.DEFAULT_SORT_BY;
		this.currentSortOrder =
			this.urlParams.get("sort_order") || window.FileListConfig.DEFAULT_SORT_ORDER;

		// Cache DOM elements
		if (typeof this.init === "function") {
			this.init();
		} else {
			// Fallback if PageControllerBase wasn't available for any reason
			this.cacheElements();
			this.initializeComponents();
			this.initializeEventHandlers();
			this.initializeFromURL();
		}

		// Initialize dropdowns for any existing static dropdowns
		this.initializeDropdowns();
	}

	/**
	 * Cache frequently accessed DOM elements
	 */
	cacheElements() {
		this.elements = {
			searchInput: document.getElementById(window.FileListConfig.ELEMENT_IDS.SEARCH_INPUT),
			startDate: document.getElementById(window.FileListConfig.ELEMENT_IDS.START_DATE),
			endDate: document.getElementById(window.FileListConfig.ELEMENT_IDS.END_DATE),
			centerFreqMin: document.getElementById(
				window.FileListConfig.ELEMENT_IDS.CENTER_FREQ_MIN,
			),
			centerFreqMax: document.getElementById(
				window.FileListConfig.ELEMENT_IDS.CENTER_FREQ_MAX,
			),
			applyFilters: document.getElementById(window.FileListConfig.ELEMENT_IDS.APPLY_FILTERS),
			clearFilters: document.getElementById(window.FileListConfig.ELEMENT_IDS.CLEAR_FILTERS),
			itemsPerPage: document.getElementById(window.FileListConfig.ELEMENT_IDS.ITEMS_PER_PAGE),
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
		if (window.__FILE_LIST_PAGE_LIFECYCLE__ && !window.pageLifecycleManager) {
			window.pageLifecycleManager = new PageLifecycleManager(
				window.__FILE_LIST_PAGE_LIFECYCLE__,
			);
		}

		if (!window.listRefreshManager && window.ListRefreshManager) {
			const lr = window.__FILE_LIST_LIST_REFRESH__ || {};
			window.listRefreshManager = new ListRefreshManager({
				containerSelector: lr.containerSelector || "#capture-list-ajax-wrapper",
				modalsContainerSelector:
					lr.modalsContainerSelector || "#capture-list-modals-container",
				url: lr.url || window.location.pathname,
				itemType: lr.itemType || "capture",
			});
		}
		this.listRefreshManager = window.listRefreshManager;

		this.modalManager = new ModalManager({
			modalId: "asset-details-modal",
			modalBodyId: "asset-details-modal-body",
			modalTitleId: "asset-details-modal-label",
		});

		if (typeof ModalManager.attachDocumentCaptureClickDelegation === "function") {
			this._detachCaptureClicks =
				ModalManager.attachDocumentCaptureClickDelegation(this.modalManager);
		}

		this.searchManager = new SearchManager({
			searchInputId: window.FileListConfig.ELEMENT_IDS.SEARCH_INPUT,
			searchButtonId: "search-btn",
			clearButtonId: "reset-search-btn",
			searchFormId: "search-form",
			onSearchStart: () => {},
			onSearch: (_query, signal) => this.performSearch(signal),
			debounceDelay: window.FileListConfig.DEBOUNCE_DELAY,
		});
	}

	/**
	 * Initialize all event handlers
	 */
	initializeEventHandlers() {
		this.initializeAccordions();
		this.initializeFrequencyHandling();
		this.initializeItemsPerPageHandler();
		this.initializeAddToDatasetButton();
		this.initializeCaptureSelectionDelegation();
	}

	destroy() {
		try {
			this._detachCaptureClicks?.();
		} catch (_) {}
		if (this._checkboxChangeHandler) {
			document.removeEventListener("change", this._checkboxChangeHandler);
			this._checkboxChangeHandler = null;
		}
		if (this._rowClickHandler && this._selectionTable) {
			this._selectionTable.removeEventListener(
				"click",
				this._rowClickHandler,
				true,
			);
			this._rowClickHandler = null;
			this._selectionTable = null;
		}
		super.destroy();
	}

	/**
	 * Selection-mode checkboxes + row toggles (server-rendered table; survives list HTML refresh).
	 */
	initializeCaptureSelectionDelegation() {
		this._checkboxChangeHandler = (e) => {
			if (!e.target.matches(".capture-select-checkbox")) return;
			const uuid = e.target.getAttribute("data-capture-uuid");
			if (!uuid) return;
			if (e.target.checked) {
				this.selectedCaptureIds.add(uuid);
			} else {
				this.selectedCaptureIds.delete(uuid);
			}
			this.syncBulkAddToDatasetButton();
		};
		document.addEventListener("change", this._checkboxChangeHandler);

		const table = document.getElementById("captures-table");
		if (!table) return;
		this._selectionTable = table;
		this._rowClickHandler = (e) => {
			if (!table.classList.contains("selection-mode-active")) return;
			if (
				e.target.closest(
					"button, a, [data-bs-toggle='dropdown'], .capture-select-checkbox",
				)
			) {
				return;
			}
			const row = e.target.closest("tr");
			if (!row) return;
			const checkbox = row.querySelector(".capture-select-checkbox");
			if (!checkbox) return;
			const uuid = checkbox.getAttribute("data-capture-uuid");
			if (!uuid) return;
			if (this.selectedCaptureIds.has(uuid)) {
				this.selectedCaptureIds.delete(uuid);
				checkbox.checked = false;
			} else {
				this.selectedCaptureIds.add(uuid);
				checkbox.checked = true;
			}
			this.syncBulkAddToDatasetButton();
			e.preventDefault();
			e.stopPropagation();
		};
		table.addEventListener("click", this._rowClickHandler, true);
	}

	/**
	 * Selection mode: one button to enter; when on, show Cancel and Add
	 */
	initializeAddToDatasetButton() {
		const mainBtn = document.getElementById("add-captures-to-dataset-btn");
		const table = document.getElementById("captures-table");
		const modeButtonsWrap = document.getElementById(
			"add-to-dataset-mode-buttons",
		);
		const cancelBtn = document.getElementById("add-to-dataset-cancel-btn");
		const addBtn = document.getElementById("add-to-dataset-add-btn");
		if (!mainBtn || !table) return;

		const enterSelectionMode = () => {
			table.classList.add("selection-mode-active");
			mainBtn.classList.add("d-none");
			mainBtn.setAttribute("aria-pressed", "true");
			if (modeButtonsWrap) modeButtonsWrap.classList.remove("d-none");
			this.syncBulkAddToDatasetButton();
		};

		mainBtn.addEventListener("click", enterSelectionMode);

		if (cancelBtn) {
			cancelBtn.addEventListener("click", () => this.exitSelectionMode());
		}

		if (addBtn) {
			addBtn.addEventListener("click", () => {
				const ids = Array.from(this.tableManager?.selectedCaptureIds ?? []);
				if (ids.length === 0) {
					if (window.showAlert) {
						window.showAlert(
							"Select at least one capture before adding to a dataset.",
							"warning",
						);
					}
					return;
				}
				const modal = document.getElementById("quickAddToDatasetModal");
				if (modal) {
					modal.dataset.captureUuids = JSON.stringify(ids);
					const bsModal = bootstrap.Modal.getOrCreateInstance(modal);
					bsModal.show();
				}
			});
		}
	}

	/**
	 * Exit bulk-add selection mode: hide the mode controls, uncheck all selected
	 * captures, and clear the selection set.
	 */
	exitSelectionMode() {
		const mainBtn = document.getElementById("add-captures-to-dataset-btn");
		const table = document.getElementById("captures-table");
		const modeButtonsWrap = document.getElementById(
			"add-to-dataset-mode-buttons",
		);
		table?.classList.remove("selection-mode-active");
		mainBtn?.classList.remove("d-none");
		mainBtn?.setAttribute("aria-pressed", "false");
		modeButtonsWrap?.classList.add("d-none");

		for (const uuid of this.selectedCaptureIds) {
			const cb = document.querySelector(
				`.capture-select-checkbox[data-capture-uuid="${uuid}"]`,
			);
			if (cb) cb.checked = false;
		}
		this.selectedCaptureIds.clear();
		this.syncBulkAddToDatasetButton();
	}

	/**
	 * While selection mode is active, disable bulk "Add" until at least one capture is selected.
	 */
	syncBulkAddToDatasetButton() {
		const addBtn = document.getElementById("add-to-dataset-add-btn");
		const table = document.getElementById("captures-table");
		if (!addBtn || !table?.classList.contains("selection-mode-active")) {
			return;
		}
		const n = this.selectedCaptureIds?.size ?? 0;
		addBtn.disabled = n === 0;
		addBtn.title =
			n === 0
				? "Select at least one capture to add to a dataset"
				: "Add selected captures to a dataset";
		addBtn.setAttribute(
			"aria-label",
			n === 0
				? "Add to dataset — select at least one capture first"
				: `Add ${n} selected capture${n === 1 ? "" : "s"} to a dataset`,
		);
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
		const searchParams = new URLSearchParams(window.location.search);

		const searchQuery = this.elements.searchInput?.value.trim() || "";
		const startDate = this.elements.startDate?.value || "";
		let endDate = this.elements.endDate?.value || "";

		if (searchQuery) {
			searchParams.set("search", searchQuery);
		} else {
			searchParams.delete("search");
		}

		if (startDate) {
			searchParams.set("date_start", startDate);
		} else {
			searchParams.delete("date_start");
		}

		if (endDate) {
			searchParams.set("date_end", `${endDate}T23:59:59`);
		} else {
			searchParams.delete("date_end");
		}

		if (this.userInteractedWithFrequency) {
			if (this.elements.centerFreqMin?.value) {
				searchParams.set("min_freq", this.elements.centerFreqMin.value);
			} else {
				searchParams.delete("min_freq");
			}
			if (this.elements.centerFreqMax?.value) {
				searchParams.set("max_freq", this.elements.centerFreqMax.value);
			} else {
				searchParams.delete("max_freq");
			}
		}

		if (this.elements.itemsPerPage?.value) {
			searchParams.set("items_per_page", this.elements.itemsPerPage.value);
		}

		searchParams.set("sort_by", this.currentSortBy);
		searchParams.set("sort_order", this.currentSortOrder);

		if (!searchParams.get("page")) {
			searchParams.set("page", "1");
		}

		return searchParams;
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
	async performSearch(signal) {
		void signal;
		try {
			const startTime = Date.now();
			const searchParams = this.buildSearchParams();
			const params = Object.fromEntries(searchParams.entries());

			await this.listRefreshManager.loadTable(params, {
				showLoading: true,
				loadingMessage: "Loading captures...",
			});

			const elapsedTime = Date.now() - startTime;
			if (elapsedTime < window.FileListConfig.MIN_LOADING_TIME) {
				await new Promise((resolve) =>
					setTimeout(resolve, window.FileListConfig.MIN_LOADING_TIME - elapsedTime),
				);
			}

			this.updateBrowserHistory(searchParams);
		} catch (error) {
			if (error.name === "AbortError") {
				console.log("Previous search request was cancelled");
				return;
			}

			console.error("Search error:", error);
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
		const frequencyRangeSlider = document.getElementById(
			"frequency-range-slider",
		);
		if (frequencyRangeSlider?.noUiSlider) {
			frequencyRangeSlider.noUiSlider.set([0, 10]);
		}

		// Also reset the display values
		const lowerValue = document.getElementById("frequency-range-lower");
		const upperValue = document.getElementById("frequency-range-upper");
		if (lowerValue) lowerValue.textContent = "0 GHz";
		if (upperValue) upperValue.textContent = "10 GHz";

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
			const minFreq = Number.parseFloat(this.urlParams.get("min_freq"));
			const maxFreq = Number.parseFloat(this.urlParams.get("max_freq"));
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
		window.DOMUtils?.initIconDropdowns(document);
	}
}

if (typeof module !== "undefined" && module.exports) {
	module.exports = { FileListPageController };
}

const _isJestRuntime =
	typeof process !== "undefined" &&
	Boolean(process.env && process.env.JEST_WORKER_ID);

if (
	typeof window !== "undefined" &&
	typeof document !== "undefined" &&
	!_isJestRuntime
) {
	window.initializeFrequencySlider = function initializeFrequencySlider() {
		if (window.fileListController?.initializeFrequencyFromURL) {
			window.fileListController.initializeFrequencyFromURL();
		}
	};

	const _bootFileListPage = () => {
		try {
			window.fileListController = new FileListPageController();
		} catch (error) {
			console.error("Error initializing file list page:", error);
		}
	};

	if (document.readyState === "loading") {
		document.addEventListener("DOMContentLoaded", _bootFileListPage);
	} else {
		_bootFileListPage();
	}
}
