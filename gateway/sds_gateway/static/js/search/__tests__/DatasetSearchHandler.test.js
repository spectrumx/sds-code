/**
 * Jest tests for DatasetSearchHandler
 * Tests search functionality for published datasets
 */

// Import the DatasetSearchHandler class
import { DatasetSearchHandler } from "../DatasetSearchHandler.js";

describe("DatasetSearchHandler", () => {
	let searchHandler;
	let mockConfig;
	let mockForm;
	let mockSearchButton;
	let mockClearButton;
	let mockResultsContainer;
	let mockResultsTbody;
	let mockResultsCount;

	beforeEach(() => {
		// Reset mocks
		jest.clearAllMocks();

		// Mock DOM elements
		mockForm = {
			addEventListener: jest.fn(),
			querySelectorAll: jest.fn(() => []),
		};

		mockSearchButton = {
			addEventListener: jest.fn(),
		};

		mockClearButton = {
			addEventListener: jest.fn(),
		};

		mockResultsContainer = {
			innerHTML: "",
		};

		mockResultsTbody = {
			innerHTML: "",
		};

		mockResultsCount = {
			textContent: "",
		};

		// Mock document methods
		document.getElementById = jest.fn((id) => {
			const elements = {
				"search-form": mockForm,
				"search-button": mockSearchButton,
				"clear-button": mockClearButton,
				"results-container": mockResultsContainer,
				"results-tbody": mockResultsTbody,
				"results-count": mockResultsCount,
			};
			return elements[id] || null;
		});

		document.querySelector = jest.fn(() => null);
		document.querySelectorAll = jest.fn(() => []);

		// Mock config
		mockConfig = {
			searchFormId: "search-form",
			searchButtonId: "search-button",
			clearButtonId: "clear-button",
			resultsContainerId: "results-container",
			resultsTbodyId: "results-tbody",
			resultsCountId: "results-count",
		};

		// Mock window.location
		Object.defineProperty(window, "location", {
			value: {
				href: "http://localhost:8000/datasets/",
				pathname: "/datasets/",
				search: "",
			},
			writable: true,
		});
	});

	describe("Initialization", () => {
		test("should initialize with correct configuration", () => {
			searchHandler = new DatasetSearchHandler(mockConfig);

			expect(searchHandler.searchForm).toBe(mockForm);
			expect(searchHandler.searchButton).toBe(mockSearchButton);
			expect(searchHandler.clearButton).toBe(mockClearButton);
			expect(searchHandler.resultsContainer).toBe(mockResultsContainer);
			expect(searchHandler.resultsTbody).toBe(mockResultsTbody);
			expect(searchHandler.resultsCount).toBe(mockResultsCount);
		});

		test("should initialize event listeners on construction", () => {
			searchHandler = new DatasetSearchHandler(mockConfig);

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
				searchHandler = new DatasetSearchHandler(mockConfig);
			}).not.toThrow();

			expect(searchHandler.searchForm).toBeNull();
		});
	});

	describe("Event Listeners", () => {
		beforeEach(() => {
			searchHandler = new DatasetSearchHandler(mockConfig);
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
				"input[type='text'], input[type='number']",
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
				key: "Enter",
				preventDefault: jest.fn(),
			};

			// Spy on handleSearch
			const handleSearchSpy = jest.spyOn(searchHandler, "handleSearch");

			// Trigger handler
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
			searchHandler = new DatasetSearchHandler(mockConfig);
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
				toString: () => "query=test+query&type=spectrum",
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
				toString: toStringSpy,
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
				toString: () => "query=test",
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
				toString: () => "query=test+query",
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
			searchHandler = new DatasetSearchHandler(mockConfig);
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
				searchHandler = new DatasetSearchHandler(mockConfig);
			}).not.toThrow();

			expect(searchHandler.searchForm).toBeNull();
			expect(searchHandler.searchButton).toBeNull();
		});

		test("should handle form with no inputs", () => {
			searchHandler = new DatasetSearchHandler(mockConfig);
			mockForm.querySelectorAll.mockReturnValue([]);

			expect(() => {
				searchHandler.initializeEnterKeyListener();
			}).not.toThrow();
		});

		test("should handle search with no form values", () => {
			searchHandler = new DatasetSearchHandler(mockConfig);

			// Mock FormData with no entries
			global.FormData = jest.fn(() => ({
				entries: () => [].entries(),
			}));

			// Mock URLSearchParams
			global.URLSearchParams = jest.fn(() => ({
				append: jest.fn(),
				toString: () => "",
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
