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

/**
 * @param {object} target - Handler instance (AssetSearchHandler or DatasetSearchHandler)
 * @param {object} config
 */
function applySearchCoreElements(target, config) {
	const searchEls = getConfiguredSearchElements(config);
	target.searchForm = searchEls.searchForm;
	target.searchButton = searchEls.searchButton;
	target.clearButton = searchEls.clearButton;
}

window.getConfiguredSearchElements = getConfiguredSearchElements;
window.applySearchCoreElements = applySearchCoreElements;
