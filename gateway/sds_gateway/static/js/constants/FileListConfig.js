/**
 * File / capture list page constants.
 * Migrated from deprecated/file-list.js (CONFIG).
 */
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

if (typeof module !== "undefined" && module.exports) {
	module.exports = { FileListConfig: window.FileListConfig };
}
