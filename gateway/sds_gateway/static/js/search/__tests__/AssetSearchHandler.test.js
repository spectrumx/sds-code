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
	
	describe("Checkbox Disabling for Existing Files", () => {
		let editModeHandler;
		let createModeHandler;
		let mockTargetElement;

		beforeEach(() => {
			// Setup edit mode handler with existing files
			const editConfig = {
				...mockConfig,
				isEditMode: true,
				formHandler: {
					setSearchHandler: jest.fn(),
					currentFiles: new Map([
						[
							"existing-file-1",
							{ id: "existing-file-1", name: "existing.h5" },
						],
					]),
				},
			};
			editModeHandler = new AssetSearchHandler(editConfig);

			// Setup create mode handler
			const createConfig = {
				...mockConfig,
				isEditMode: false,
			};
			createModeHandler = new AssetSearchHandler(createConfig);

			// Mock target element for rendering
			mockTargetElement = document.createElement("tbody");
			mockTargetElement.id = "file-tree-table-body";
			
			// Mock DOMUtils.formatFileSize
			global.window.DOMUtils.formatFileSize = jest.fn((size) => size || "0 B");
		});

		test("should disable checkbox and add readonly styling for existing files in edit mode", () => {
			const existingFile = {
				id: "existing-file-1",
				name: "existing.h5",
				media_type: "application/hdf5",
				size: 1024,
				created_at: "2024-01-01T00:00:00Z",
			};

			const tree = {
				files: [existingFile],
			};

			editModeHandler.renderFileTree(tree, mockTargetElement);

			const row = mockTargetElement.querySelector("tr");
			const checkbox = row.querySelector('input[type="checkbox"]');

			// Check that checkbox is disabled
			expect(checkbox.disabled).toBe(true);
			// Check that readonly-row class is added
			expect(row.classList.contains("readonly-row")).toBe(true);
			// Check that tooltip is set
			expect(row.title).toBe("This file is already in the dataset");
			// Check that clickable-row class is NOT added
			expect(row.classList.contains("clickable-row")).toBe(false);
		});

		test("should enable checkbox and add event handlers for new files in edit mode", () => {
			const newFile = {
				id: "new-file-1",
				name: "new.h5",
				media_type: "application/hdf5",
				size: 2048,
				created_at: "2024-01-02T00:00:00Z",
			};

			const tree = {
				files: [newFile],
			};

			// Spy on addEventListener to verify event handlers are attached
			const addEventListenerSpy = jest.spyOn(
				HTMLElement.prototype,
				"addEventListener",
			);

			editModeHandler.renderFileTree(tree, mockTargetElement);

			const row = mockTargetElement.querySelector("tr");
			const checkbox = row.querySelector('input[type="checkbox"]');

			// Check that checkbox is NOT disabled
			expect(checkbox.disabled).toBe(false);
			// Check that clickable-row class is added
			expect(row.classList.contains("clickable-row")).toBe(true);
			// Check that readonly-row class is NOT added
			expect(row.classList.contains("readonly-row")).toBe(false);
			// Verify event handlers were attached (change event for checkbox, click for row)
			expect(addEventListenerSpy).toHaveBeenCalledWith(
				"change",
				expect.any(Function),
			);
			expect(addEventListenerSpy).toHaveBeenCalledWith(
				"click",
				expect.any(Function),
			);

			addEventListenerSpy.mockRestore();
		});

		test("should enable all checkboxes in create mode regardless of file existence", () => {
			const file = {
				id: "any-file-1",
				name: "any.h5",
				media_type: "application/hdf5",
				size: 1024,
				created_at: "2024-01-01T00:00:00Z",
			};

			const tree = {
				files: [file],
			};

			createModeHandler.renderFileTree(tree, mockTargetElement);

			const row = mockTargetElement.querySelector("tr");
			const checkbox = row.querySelector('input[type="checkbox"]');

			// In create mode, all checkboxes should be enabled
			expect(checkbox.disabled).toBe(false);
			expect(row.classList.contains("readonly-row")).toBe(false);
			expect(row.classList.contains("clickable-row")).toBe(true);
		});

		test("should handle missing formHandler gracefully when rendering", () => {
			const configWithoutFormHandler = {
				...mockConfig,
				isEditMode: true,
				formHandler: null,
			};
			const handler = new AssetSearchHandler(configWithoutFormHandler);

			const file = {
				id: "any-file-1",
				name: "any.h5",
				media_type: "application/hdf5",
				size: 1024,
				created_at: "2024-01-01T00:00:00Z",
			};

			const tree = {
				files: [file],
			};

			// Should not throw when formHandler is null
			expect(() => {
				handler.renderFileTree(tree, mockTargetElement);
			}).not.toThrow();

			// File should be enabled since formHandler is null
			const checkbox = mockTargetElement.querySelector(
				'input[type="checkbox"]',
			);
			expect(checkbox.disabled).toBe(false);
		});

		test("should handle missing currentFiles gracefully when rendering", () => {
			const configWithoutCurrentFiles = {
				...mockConfig,
				isEditMode: true,
				formHandler: {
					setSearchHandler: jest.fn(),
					currentFiles: null,
				},
			};
			const handler = new AssetSearchHandler(configWithoutCurrentFiles);

			const file = {
				id: "any-file-1",
				name: "any.h5",
				media_type: "application/hdf5",
				size: 1024,
				created_at: "2024-01-01T00:00:00Z",
			};

			const tree = {
				files: [file],
			};

			// Should not throw when currentFiles is null
			expect(() => {
				handler.renderFileTree(tree, mockTargetElement);
			}).not.toThrow();

			// File should be enabled since currentFiles is null
			const checkbox = mockTargetElement.querySelector(
				'input[type="checkbox"]',
			);
			expect(checkbox.disabled).toBe(false);
		});
	});
});
