/**
 * Debounced search with AbortController (historically named SearchManager on window).
 * Migrated from deprecated/components.js.
 */

class SearchManager {
	constructor(config) {
		this.searchInput = document.getElementById(config.searchInputId);
		this.searchButton = document.getElementById(config.searchButtonId);
		this.clearButton = document.getElementById("clear-search-btn");
		this.onSearch = config.onSearch;
		this.onSearchStart = config.onSearchStart;
		this.debounceDelay = config.debounceDelay || 500;
		this.debounceTimer = null;
		this.abortController = new AbortController();

		this.initializeEventListeners();
		this.updateClearButtonVisibility();
	}

	initializeEventListeners() {
		if (this.searchInput) {
			this.searchInput.addEventListener("input", () => {
				this.debounceSearch();
				this.updateClearButtonVisibility();
			});

			this.searchInput.addEventListener("keypress", (e) => {
				if (e.key === "Enter") {
					e.preventDefault();
					this.debounceSearch();
				}
			});
		}

		if (this.searchButton) {
			this.searchButton.addEventListener("click", (e) => {
				e.preventDefault();
				this.debounceSearch();
			});
		}

		if (this.clearButton) {
			this.clearButton.addEventListener("click", (e) => {
				e.preventDefault();
				this.clearSearch();
			});
		}
	}

	updateClearButtonVisibility() {
		if (this.clearButton) {
			this.clearButton.style.display = this.searchInput?.value
				? "block"
				: "none";
		}
	}

	debounceSearch() {
		// Show loading indicator immediately for visual confirmation
		if (this.onSearchStart) {
			this.onSearchStart();
		}

		if (this.debounceTimer) {
			clearTimeout(this.debounceTimer);
		}

		this.debounceTimer = setTimeout(() => {
			this.performSearch();
		}, this.debounceDelay);
	}

	performSearch() {
		// Cancel any previous request and create a new abort controller
		this.abortController.abort();
		this.abortController = new AbortController();

		const query = this.searchInput?.value || "";

		if (this.onSearch) {
			this.onSearch(query, this.abortController.signal);
		}
	}

	clearSearch() {
		if (this.searchInput) {
			this.searchInput.value = "";
			this.updateClearButtonVisibility();
		}

		this.debounceSearch();
	}

	/**
	 * Get the current abort signal for fetch requests
	 */
	getAbortSignal() {
		return this.abortController.signal;
	}
}

if (typeof window !== "undefined") {
	window.SearchManager = SearchManager;
	window.DebouncedSearchManager = SearchManager;
}
if (typeof module !== "undefined" && module.exports) {
	module.exports = { SearchManager, DebouncedSearchManager: SearchManager };
}

