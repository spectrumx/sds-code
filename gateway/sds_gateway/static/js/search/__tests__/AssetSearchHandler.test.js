/**
 * Jest tests for AssetSearchHandler
 * Tests search functionality for captures and files in dataset creation/editing
 */

// Import the AssetSearchHandler class
import { AssetSearchHandler } from "../AssetSearchHandler.js";

// Mock APIClient
global.APIClient = {
	get: jest.fn(),
};

// Mock DOMUtils (replaces HTMLInjectionManager)
global.window.DOMUtils = {
	show: jest.fn(),
	hide: jest.fn(),
	showAlert: jest.fn(),
	renderError: jest.fn().mockResolvedValue(true),
	renderLoading: jest.fn().mockResolvedValue(true),
	renderContent: jest.fn().mockResolvedValue(true),
	renderTable: jest.fn().mockResolvedValue(true),
};

describe("AssetSearchHandler", () => {
	let searchHandler;
	let mockConfig;
	let mockForm;
	let mockButton;
	let mockTableBody;

	beforeEach(() => {
		// Reset mocks
		jest.clearAllMocks();

		// Mock DOM elements
		mockForm = {
			addEventListener: jest.fn(),
			querySelectorAll: jest.fn(() => []),
		};

		mockButton = {
			addEventListener: jest.fn(),
			disabled: false,
		};

		mockTableBody = {
			innerHTML: "",
			querySelectorAll: jest.fn(() => []),
		};

		// Mock document methods
		document.getElementById = jest.fn((id) => {
			const elements = {
				"search-form": mockForm,
				"search-button": mockButton,
				"clear-button": mockButton,
				"table-body": mockTableBody,
				"pagination-container": { innerHTML: "" },
				"confirm-file-selection": mockButton,
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
			tableBodyId: "table-body",
			paginationContainerId: "pagination-container",
			confirmFileSelectionId: "confirm-file-selection",
			type: "captures",
			apiEndpoint: "/api/search/",
			formHandler: {
				setSearchHandler: jest.fn(),
			},
			isEditMode: false,
			initialFileDetails: {},
			initialCaptureDetails: {},
		};

		// Mock API responses
		global.APIClient.get.mockResolvedValue({
			success: true,
			results: [
				{ id: 1, name: "Test Capture 1", type: "rh" },
				{ id: 2, name: "Test Capture 2", type: "drf" },
			],
			pagination: {
				current_page: 1,
				total_pages: 1,
				has_next: false,
				has_previous: false,
			},
		});

		// Mock window.datasetEditingHandler
		global.window = {
			datasetEditingHandler: {
				addFileToPending: jest.fn(),
			},
		};
	});

	describe("Initialization", () => {
		test("should initialize with correct configuration", () => {
			searchHandler = new AssetSearchHandler(mockConfig);

			expect(searchHandler.searchForm).toBe(mockForm);
			expect(searchHandler.searchButton).toBe(mockButton);
			expect(searchHandler.clearButton).toBe(mockButton);
			expect(searchHandler.tableBody).toBe(mockTableBody);
			expect(searchHandler.type).toBe("captures");
			expect(searchHandler.isEditMode).toBe(false);
			expect(searchHandler.selectedFiles).toBeInstanceOf(Map);
			expect(searchHandler.selectedCaptureDetails).toBeInstanceOf(Map);
		});

		test("should setup form handler reference", () => {
			searchHandler = new AssetSearchHandler(mockConfig);

			expect(mockConfig.formHandler.setSearchHandler).toHaveBeenCalledWith(
				searchHandler,
				"captures",
			);
		});

		test("should initialize with initial data", () => {
			const configWithInitialData = {
				...mockConfig,
				initialFileDetails: { "file1-uuid": { name: "test.h5" } },
				initialCaptureDetails: { "capture1-uuid": { name: "test capture" } },
			};

			searchHandler = new AssetSearchHandler(configWithInitialData);

			expect(searchHandler.selectedFiles.has("file1-uuid")).toBe(true);
			expect(searchHandler.selectedCaptureDetails.has("capture1-uuid")).toBe(
				true,
			);
		});
	});

	describe("Event Listeners", () => {
		beforeEach(() => {
			searchHandler = new AssetSearchHandler(mockConfig);
		});

		test.each([
			["search button"],
			["clear button"],
			["confirm file selection"],
		])("should setup %s event listener", (buttonName) => {
			expect(mockButton.addEventListener).toHaveBeenCalledWith(
				"click",
				expect.any(Function),
			);
		});

		test("should setup enter key listener on search inputs", () => {
			const mockInput = {
				addEventListener: jest.fn(),
			};
			mockForm.querySelectorAll.mockReturnValue([mockInput]);

			searchHandler.initializeEnterKeyListener();

			expect(mockInput.addEventListener).toHaveBeenCalledWith(
				"keypress",
				expect.any(Function),
			);
		});
	});

	describe("Clear Functionality", () => {
		beforeEach(() => {
			searchHandler = new AssetSearchHandler(mockConfig);
		});

		test("should clear search results", () => {
			searchHandler.handleClear();

			expect(mockTableBody.innerHTML).toBe("");
		});

		test("should clear search form", () => {
			const mockInput = { value: "test search" };
			mockForm.querySelectorAll.mockReturnValue([mockInput]);

			searchHandler.handleClear();

			expect(mockInput.value).toBe("");
		});

	});

	describe("Selection Properties", () => {
		beforeEach(() => {
			searchHandler = new AssetSearchHandler(mockConfig);
		});

		test.each([
			["selectedFiles", Map],
			["selectedCaptureDetails", Map],
		])("should have %s property", (propertyName, expectedType) => {
			expect(searchHandler[propertyName]).toBeDefined();
			expect(searchHandler[propertyName]).toBeInstanceOf(expectedType);
		});

		test("should update selected files list", () => {
			searchHandler.updateSelectedFilesList();
			expect(searchHandler.updateSelectedFilesList).toBeDefined();
		});
	});

	describe("Select All Functionality", () => {
		beforeEach(() => {
			searchHandler = new AssetSearchHandler(mockConfig);
		});

		test("should initialize select all checkbox", () => {
			const mockCheckbox = {
				addEventListener: jest.fn(),
				checked: false,
			};
			document.getElementById.mockImplementation((id) => {
				if (id === "select-all-files-checkbox") return mockCheckbox;
				return null;
			});

			searchHandler.initializeSelectAllCheckbox();

			expect(mockCheckbox.addEventListener).toHaveBeenCalledWith(
				"change",
				expect.any(Function),
			);
		});
	});

	describe("Edit Mode Integration", () => {
		beforeEach(() => {
			const editConfig = {
				...mockConfig,
				isEditMode: true,
			};
			searchHandler = new AssetSearchHandler(editConfig);
		});

		test("should initialize in edit mode", () => {
			expect(searchHandler.isEditMode).toBe(true);
		});
	});

	describe("Error Handling", () => {
		beforeEach(() => {
			searchHandler = new AssetSearchHandler(mockConfig);
		});

		test("should handle missing form handler gracefully", () => {
			const configWithoutFormHandler = {
				...mockConfig,
				formHandler: null,
			};

			expect(() => {
				new AssetSearchHandler(configWithoutFormHandler);
			}).not.toThrow();
		});
	});

	describe("State Management", () => {
		beforeEach(() => {
			searchHandler = new AssetSearchHandler(mockConfig);
		});

		test("should track current filters", () => {
			searchHandler.currentFilters = { type: "spectrum" };

			expect(searchHandler.currentFilters.type).toBe("spectrum");
		});
	});

});
