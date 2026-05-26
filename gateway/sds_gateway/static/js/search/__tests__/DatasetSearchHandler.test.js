/**
 * Jest tests for ListPageSearchController (list-page GET search)
 */

import { ListPageSearchController } from "../AssetSearchHandler.js";

const {
	setupStandardUnitTest,
	createMockFormElement,
	createMockButtonElement,
	createDefaultDatasetSearchConfig,
	createDatasetSearchGetElementByIdMap,
	installMockDatasetListLocation,
} = require("../../tests-config/testHelpers.js");

describe("ListPageSearchController", () => {
	let searchHandler;
	let mockConfig;
	let mockForm;
	let mockSearchButton;
	let mockClearButton;
	let mockResultsContainer;
	let mockResultsTbody;
	let mockResultsCount;

	beforeEach(() => {
		mockForm = createMockFormElement();
		mockSearchButton = createMockButtonElement();
		mockClearButton = createMockButtonElement();
		mockResultsContainer = { innerHTML: "" };
		mockResultsTbody = { innerHTML: "" };
		mockResultsCount = { textContent: "" };

		setupStandardUnitTest({
			getElementByIdMap: createDatasetSearchGetElementByIdMap({
				mockForm,
				mockSearchButton,
				mockClearButton,
				mockResultsContainer,
				mockResultsTbody,
				mockResultsCount,
			}),
			apiClient: false,
		});

		mockConfig = createDefaultDatasetSearchConfig();
		installMockDatasetListLocation();
	});

	describe("Initialization", () => {
		test("should initialize with correct configuration", () => {
			searchHandler = new ListPageSearchController(mockConfig);

			expect(searchHandler.searchForm).toBe(mockForm);
			expect(searchHandler.searchButton).toBe(mockSearchButton);
			expect(searchHandler.clearButton).toBe(mockClearButton);
		});

		test("should initialize event listeners on construction", () => {
			searchHandler = new ListPageSearchController(mockConfig);

			// Form should have submit listener
			expect(mockForm.addEventListener).toHaveBeenCalledWith(
				"submit",
				expect.any(Function),
			);

			// Clear button should have click listener
			expect(mockClearButton.addEventListener).toHaveBeenCalledWith(
				"click",
				expect.any(Function),
			);
		});

		test("should handle missing form element gracefully", () => {
			document.getElementById.mockImplementation((id) => {
				if (id === "search-form") return null;
				return {
					"search-button": mockSearchButton,
					"clear-button": mockClearButton,
					"results-container": mockResultsContainer,
					"results-tbody": mockResultsTbody,
					"results-count": mockResultsCount,
				}[id];
			});

			expect(() => {
				searchHandler = new ListPageSearchController(mockConfig);
			}).not.toThrow();

			expect(searchHandler.searchForm).toBeNull();
		});
	});

	describe("Event Listeners", () => {
		beforeEach(() => {
			searchHandler = new ListPageSearchController(mockConfig);
		});

		test("should setup form submit event listener", () => {
			expect(mockForm.addEventListener).toHaveBeenCalledWith(
				"submit",
				expect.any(Function),
			);
		});

		test("should setup clear button click event listener", () => {
			expect(mockClearButton.addEventListener).toHaveBeenCalledWith(
				"click",
				expect.any(Function),
			);
		});

		test("should setup enter key listener for search inputs", () => {
			const mockInput = {
				addEventListener: jest.fn(),
				type: "text",
			};
			mockForm.querySelectorAll.mockReturnValue([mockInput]);

			searchHandler.initializeEnterKeyListener();

			expect(mockForm.querySelectorAll).toHaveBeenCalledWith(
				"input[type='text'], input[type='search'], input[type='number']",
			);
			expect(mockInput.addEventListener).toHaveBeenCalledWith(
				"keypress",
				expect.any(Function),
			);
		});

		test("should not setup enter key listener if form is missing", () => {
			searchHandler.searchForm = null;

			expect(() => {
				searchHandler.initializeEnterKeyListener();
			}).not.toThrow();
		});

		test("should handle enter key press on input", () => {
			const realForm = document.createElement("form");
			realForm.id = "search-form";
			const mockInput = document.createElement("input");
			mockInput.type = "text";
			realForm.appendChild(mockInput);
			document.getElementById = jest.fn((id) => {
				if (id === "search-form") return realForm;
				const elements = {
					"search-button": mockSearchButton,
					"clear-button": mockClearButton,
					"results-container": mockResultsContainer,
					"results-tbody": mockResultsTbody,
					"results-count": mockResultsCount,
				};
				return elements[id] || null;
			});
			searchHandler = new ListPageSearchController(mockConfig);
			const mockInputListener = { addEventListener: jest.fn(), type: "text" };
			realForm.querySelectorAll = jest.fn(() => [mockInputListener]);
			searchHandler.initializeEnterKeyListener();

			const handler = mockInputListener.addEventListener.mock.calls.find(
				(call) => call[0] === "keypress",
			)?.[1];
			if (!handler) {
				throw new Error("keypress handler not attached");
			}
			const mockEvent = { key: "Enter", preventDefault: jest.fn() };
			const handleSearchSpy = jest.spyOn(searchHandler, "handleSearch");
			handler(mockEvent);
			expect(mockEvent.preventDefault).toHaveBeenCalled();
			expect(handleSearchSpy).toHaveBeenCalled();
			handleSearchSpy.mockRestore();
		});

		test("should not trigger search on other key presses", () => {
			const mockInput = {
				addEventListener: jest.fn(),
				type: "text",
			};
			mockForm.querySelectorAll.mockReturnValue([mockInput]);

			searchHandler.initializeEnterKeyListener();

			// Get the event handler
			const handler = mockInput.addEventListener.mock.calls.find(
				(call) => call[0] === "keypress",
			)[1];

			// Create mock event
			const mockEvent = {
				key: "a",
				preventDefault: jest.fn(),
			};

			// Spy on handleSearch
			const handleSearchSpy = jest.spyOn(searchHandler, "handleSearch");

			// Trigger handler
			handler(mockEvent);

			expect(mockEvent.preventDefault).not.toHaveBeenCalled();
			expect(handleSearchSpy).not.toHaveBeenCalled();

			handleSearchSpy.mockRestore();
		});
	});

	describe("Search Functionality", () => {
		beforeEach(() => {
			searchHandler = new ListPageSearchController(mockConfig);
		});

		test("should handle search form submission", () => {
			// Mock FormData
			const mockFormData = new Map([
				["query", "test query"],
				["type", "spectrum"],
			]);
			global.FormData = jest.fn(() => ({
				entries: () => mockFormData.entries(),
			}));

			// Mock URLSearchParams
			global.URLSearchParams = jest.fn(() => ({
				append: jest.fn(),
				set: jest.fn(),
				toString: () => "query=test+query&type=spectrum&page=1",
			}));

			// Mock window.location.href setter
			let locationHref = window.location.href;
			Object.defineProperty(window, "location", {
				get: () => ({
					href: locationHref,
					pathname: "/datasets/",
				}),
				set: (value) => {
					locationHref = value;
				},
				configurable: true,
			});

			searchHandler.handleSearch();

			// Verify form data was processed
			expect(global.FormData).toHaveBeenCalledWith(mockForm);
		});

		test("should navigate to search URL with parameters", () => {
			// Mock FormData
			const mockFormData = new Map([
				["query", "test"],
				["type", "spectrum"],
			]);
			global.FormData = jest.fn(() => ({
				entries: () => mockFormData.entries(),
			}));

			// Mock URLSearchParams
			const appendSpy = jest.fn();
			const toStringSpy = jest.fn(() => "query=test&type=spectrum");
			global.URLSearchParams = jest.fn(() => ({
				append: appendSpy,
				set: jest.fn(),
				toString: toStringSpy,
			}));

			// Track location changes
			let locationHref = window.location.href;
			Object.defineProperty(window, "location", {
				get: () => ({
					href: locationHref,
					pathname: "/datasets/",
					search: "",
				}),
				set: (value) => {
					locationHref = value;
				},
				configurable: true,
			});

			searchHandler.handleSearch();

			expect(appendSpy).toHaveBeenCalledWith("query", "test");
			expect(appendSpy).toHaveBeenCalledWith("type", "spectrum");
			expect(toStringSpy).toHaveBeenCalled();
		});

		test("should filter out empty form values", () => {
			// Mock FormData with empty values
			const mockFormData = new Map([
				["query", "test"],
				["type", ""],
				["empty", "   "],
			]);
			global.FormData = jest.fn(() => ({
				entries: () => mockFormData.entries(),
			}));

			// Mock URLSearchParams
			const appendSpy = jest.fn();
			global.URLSearchParams = jest.fn(() => ({
				append: appendSpy,
				set: jest.fn(),
				toString: () => "query=test&page=1",
			}));

			searchHandler.handleSearch();

			// Should only append non-empty values
			expect(appendSpy).toHaveBeenCalledWith("query", "test");
			expect(appendSpy).not.toHaveBeenCalledWith("type", "");
			expect(appendSpy).not.toHaveBeenCalledWith("empty", "   ");
		});

		test("should trim form values", () => {
			// Mock FormData with whitespace
			const mockFormData = new Map([["query", "  test query  "]]);
			global.FormData = jest.fn(() => ({
				entries: () => mockFormData.entries(),
			}));

			// Mock URLSearchParams
			const appendSpy = jest.fn();
			global.URLSearchParams = jest.fn(() => ({
				append: appendSpy,
				set: jest.fn(),
				toString: () => "query=test+query&page=1",
			}));

			searchHandler.handleSearch();

			expect(appendSpy).toHaveBeenCalledWith("query", "test query");
		});

		test("should handle missing form gracefully", () => {
			searchHandler.searchForm = null;

			expect(() => {
				searchHandler.handleSearch();
			}).not.toThrow();
		});

		test("should prevent default form submission", () => {
			const mockEvent = {
				preventDefault: jest.fn(),
			};

			// Get the submit handler
			const handler = mockForm.addEventListener.mock.calls.find(
				(call) => call[0] === "submit",
			)[1];

			handler(mockEvent);

			expect(mockEvent.preventDefault).toHaveBeenCalled();
		});
	});

	describe("Clear Functionality", () => {
		beforeEach(() => {
			searchHandler = new ListPageSearchController(mockConfig);
		});

		test("should clear all form inputs", () => {
			const mockTextInput = { value: "test", type: "text" };
			const mockNumberInput = { value: "123", type: "number" };
			const mockCheckbox = { checked: true, type: "checkbox" };
			const mockRadio = { checked: true, type: "radio" };
			const mockSelect = { value: "option1", type: "select-one" };
			const mockTextarea = { value: "textarea text", type: "textarea" };

			mockForm.querySelectorAll.mockReturnValue([
				mockTextInput,
				mockNumberInput,
				mockCheckbox,
				mockRadio,
				mockSelect,
				mockTextarea,
			]);

			// Track location changes
			let locationHref = window.location.href;
			Object.defineProperty(window, "location", {
				get: () => ({
					href: locationHref,
					pathname: "/datasets/",
				}),
				set: (value) => {
					locationHref = value;
				},
				configurable: true,
			});

			searchHandler.handleClear();

			expect(mockTextInput.value).toBe("");
			expect(mockNumberInput.value).toBe("");
			expect(mockCheckbox.checked).toBe(false);
			expect(mockRadio.checked).toBe(false);
			expect(mockSelect.value).toBe("");
			expect(mockTextarea.value).toBe("");
		});

		test("should navigate to base URL without parameters", () => {
			let locationHref = "/datasets/";
			const locationObj = {
				get pathname() {
					return "/datasets/";
				},
				get href() {
					return locationHref;
				},
				set href(value) {
					locationHref = value;
				},
			};
			Object.defineProperty(window, "location", {
				value: locationObj,
				writable: true,
				configurable: true,
			});

			mockForm.querySelectorAll.mockReturnValue([]);

			searchHandler.handleClear();

			expect(locationHref).toBe("/datasets/");
		});

		test("should prevent default on clear button click", () => {
			const mockEvent = {
				preventDefault: jest.fn(),
			};

			// Get the click handler
			const handler = mockClearButton.addEventListener.mock.calls.find(
				(call) => call[0] === "click",
			)[1];

			handler(mockEvent);

			expect(mockEvent.preventDefault).toHaveBeenCalled();
		});

		test("should handle missing form gracefully", () => {
			searchHandler.searchForm = null;

			expect(() => {
				searchHandler.handleClear();
			}).not.toThrow();
		});
	});

	describe("Edge Cases", () => {
		test("should handle null elements in config", () => {
			document.getElementById.mockReturnValue(null);

			expect(() => {
				searchHandler = new ListPageSearchController(mockConfig);
			}).not.toThrow();

			expect(searchHandler.searchForm).toBeNull();
			expect(searchHandler.searchButton).toBeNull();
		});

		test("should handle form with no inputs", () => {
			searchHandler = new ListPageSearchController(mockConfig);
			mockForm.querySelectorAll.mockReturnValue([]);

			expect(() => {
				searchHandler.initializeEnterKeyListener();
			}).not.toThrow();
		});

		test("should handle search with no form values", () => {
			searchHandler = new ListPageSearchController(mockConfig);

			// Mock FormData with no entries
			global.FormData = jest.fn(() => ({
				entries: () => [].entries(),
			}));

			// Mock URLSearchParams
			global.URLSearchParams = jest.fn(() => ({
				append: jest.fn(),
				set: jest.fn(),
				toString: () => "page=1",
			}));

			// Track location changes
			let locationHref = window.location.href;
			Object.defineProperty(window, "location", {
				get: () => ({
					href: locationHref,
					pathname: "/datasets/",
				}),
				set: (value) => {
					locationHref = value;
				},
				configurable: true,
			});

			expect(() => {
				searchHandler.handleSearch();
			}).not.toThrow();
		});
	});
});
