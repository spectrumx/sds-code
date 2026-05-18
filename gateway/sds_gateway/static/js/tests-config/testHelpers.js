/**
 * Shared Jest helpers for static/js tests (DOMUtils mocks, microtask flush).
 */

/** @returns {Record<string, jest.Mock>} */
function createMockDOMUtils(overrides = {}) {
	return {
		show: jest.fn(),
		hide: jest.fn(),
		showMessage: jest.fn().mockResolvedValue(true),
		showError: jest.fn().mockResolvedValue(true),
		renderLoading: jest.fn().mockResolvedValue(true),
		renderContent: jest.fn().mockResolvedValue(true),
		renderTable: jest.fn().mockResolvedValue(true),
		renderSelectOptions: jest.fn().mockResolvedValue(true),
		renderPagination: jest.fn().mockResolvedValue(true),
		renderDropdown: jest.fn().mockResolvedValue("<div>Mock Dropdown</div>"),
		...overrides,
	};
}

function installMinimalDocumentMocks() {
	document.getElementById = jest.fn(() => null);
	document.querySelector = jest.fn(() => null);
	document.querySelectorAll = jest.fn(() => []);
}

function flushMicrotasks() {
	return new Promise((resolve) => setTimeout(resolve, 0));
}

module.exports = {
	createMockDOMUtils,
	installMinimalDocumentMocks,
	flushMicrotasks,
};
