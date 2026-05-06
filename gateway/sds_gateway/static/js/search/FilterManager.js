/**
 * Filter form state and URL sync.
 * Migrated from deprecated/components.js.
 */

class FilterManager {
	constructor(config) {
		this.formId = config.formId;
		this.form = document.getElementById(this.formId);
		this.applyButton = document.getElementById(config.applyButtonId);
		this.clearButton = document.getElementById(config.clearButtonId);
		this.onFilterChange = config.onFilterChange;
		this.searchInputId = config.searchInputId || "search-input";

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

		// Get all form inputs except the search input
		const inputs = this.form.querySelectorAll("input, select, textarea");
		for (const input of inputs) {
			// Skip the search input
			if (input.id === this.searchInputId) {
				continue;
			}

			// Clear other inputs
			if (input.type === "checkbox" || input.type === "radio") {
				input.checked = false;
			} else {
				input.value = "";
			}
		}

		// Get current URL parameters
		const urlParams = new URLSearchParams(window.location.search);
		const searchValue = urlParams.get("search");
		const sortBy = urlParams.get("sort_by") || "created_at";
		const sortOrder = urlParams.get("sort_order") || "desc";

		// Clear all parameters except search and sort
		urlParams.forEach((_, key) => {
			if (key !== "search" && key !== "sort_by" && key !== "sort_order") {
				urlParams.delete(key);
			}
		});

		// Ensure sort parameters are set
		urlParams.set("sort_by", sortBy);
		urlParams.set("sort_order", sortOrder);
		urlParams.set("page", "1");

		// Update URL
		const newUrl = `${window.location.pathname}?${urlParams.toString()}`;
		window.history.pushState({}, "", newUrl);

		// Trigger filter change callback
		if (this.onFilterChange) {
			const filters = {
				sort_by: sortBy,
				sort_order: sortOrder,
			};
			if (searchValue) {
				filters.search = searchValue;
			}
			this.onFilterChange(filters);
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

		// Preserve search parameter if it exists
		const searchValue = urlParams.get("search");

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

		// Restore search parameter if it existed
		if (searchValue) {
			urlParams.set("search", searchValue);
		}

		// Reset to first page when filters change
		urlParams.set("page", "1");

		const newUrl = `${window.location.pathname}?${urlParams.toString()}`;
		window.history.pushState({}, "", newUrl);
	}
}

if (typeof window !== "undefined") {
	window.FilterManager = FilterManager;
}
if (typeof module !== "undefined" && module.exports) {
	module.exports = { FilterManager };
}

