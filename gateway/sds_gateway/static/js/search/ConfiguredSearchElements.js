/**
 * Shared DOM bindings for search forms (dataset list, asset picker, etc.).
 * @param {Object} config
 * @returns {{ searchForm: HTMLElement|null, searchButton: HTMLElement|null, clearButton: HTMLElement|null }}
 */
function getConfiguredSearchElements(config) {
	return {
		searchForm: document.getElementById(config.searchFormId),
		searchButton: document.getElementById(config.searchButtonId),
		clearButton: document.getElementById(config.clearButtonId),
	};
}

window.getConfiguredSearchElements = getConfiguredSearchElements;
