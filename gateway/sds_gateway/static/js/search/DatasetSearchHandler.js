/**
 * Dataset Search Handler
 * Handles search functionality for published datasets
 */
class DatasetSearchHandler {
	/**
	 * Initialize dataset search handler
	 * @param {Object} config - Configuration object
	 */
	constructor(config) {
		this.searchForm = document.getElementById(config.searchFormId);
		this.searchButton = document.getElementById(config.searchButtonId);
		this.clearButton = document.getElementById(config.clearButtonId);
		this.resultsContainer = document.getElementById(config.resultsContainerId);
		this.resultsTbody = document.getElementById(config.resultsTbodyId);
		this.resultsCount = document.getElementById(config.resultsCountId);

		this.initializeEventListeners();
	}

	/**
	 * Initialize event listeners
	 */
	initializeEventListeners() {
		// Search form submission
		if (this.searchForm) {
			this.searchForm.addEventListener("submit", (e) => {
				e.preventDefault();
				this.handleSearch();
			});
		}

		// Clear button
		if (this.clearButton) {
			this.clearButton.addEventListener("click", (e) => {
				e.preventDefault();
				this.handleClear();
			});
		}

		// Enter key listener for search inputs
		this.initializeEnterKeyListener();
	}

	/**
	 * Initialize enter key listener for search inputs
	 */
	initializeEnterKeyListener() {
		if (!this.searchForm) {
			return;
		}

		const searchInputs = this.searchForm.querySelectorAll("input[type='text'], input[type='number']");
		for (const input of searchInputs) {
			input.addEventListener("keypress", (e) => {
				if (e.key === "Enter") {
					e.preventDefault();
					this.handleSearch();
				}
			});
		}
	}

	/**
	 * Handle search form submission
	 */
	handleSearch() {
		if (!this.searchForm) {
			return;
		}

		// Get form data
		const formData = new FormData(this.searchForm);
		const params = new URLSearchParams();

		// Add non-empty form values to params
		for (const [key, value] of formData.entries()) {
			if (value && value.trim() !== "") {
				params.append(key, value.trim());
			}
		}

		// Build URL with search parameters
		const searchUrl = `${window.location.pathname}?${params.toString()}`;

		// Navigate to search URL (this will trigger a page reload with results)
		window.location.href = searchUrl;
	}

	/**
	 * Handle clear button click
	 */
	handleClear() {
		if (!this.searchForm) {
			return;
		}

		// Clear all form inputs
		const inputs = this.searchForm.querySelectorAll("input, select, textarea");
		for (const input of inputs) {
			if (input.type === "checkbox" || input.type === "radio") {
				input.checked = false;
			} else {
				input.value = "";
			}
		}

		// Navigate to base search URL (no parameters)
		window.location.href = window.location.pathname;
	}
}

// Export for use in other scripts
if (typeof window !== "undefined") {
	window.DatasetSearchHandler = DatasetSearchHandler;
}

