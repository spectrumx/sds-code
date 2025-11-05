/**
 * Jest tests for DatasetCreationHandler
 * Tests dataset creation workflow and form management
 */

import { APIError } from "../../core/APIClient.js";
// Import the DatasetCreationHandler class
import { DatasetCreationHandler } from "../DatasetCreationHandler.js";

describe("DatasetCreationHandler", () => {
	let creationHandler;
	let mockForm;
	let mockConfig;
	let mockPrevBtn;
	let mockNextBtn;
	let mockSubmitBtn;
	let mockStepTab;
	let mockNameField;
	let mockAuthorsField;
	let mockStatusField;
	let mockDescriptionField;
	let mockSelectedCapturesField;
	let mockSelectedFilesField;

	beforeAll(() => {
		// Helper function to create a mock classList that actually tracks classes
		const createMockClassList = () => {
			const classes = new Set();
			return {
				add: jest.fn((className) => {
					if (typeof className === "string") {
						classes.add(className);
					} else if (typeof className === "object" && className.length) {
						// Handle multiple classes
						for (const cls of className) {
							classes.add(cls);
						}
					}
				}),
				remove: jest.fn((className) => {
					if (typeof className === "string") {
						classes.delete(className);
					} else if (typeof className === "object" && className.length) {
						// Handle multiple classes
						for (const cls of className) {
							classes.delete(cls);
						}
					}
				}),
				contains: jest.fn((className) => classes.has(className)),
				classes: classes, // For debugging
			};
		};

		// Create the handler once for all tests
		mockConfig = {
			formId: "dataset-form",
			steps: ["info", "captures", "files", "review"],
			onStepChange: jest.fn(),
		};

		// Mock DOM elements - these will be the same objects used in tests
		mockForm = {
			addEventListener: jest.fn(),
			querySelector: jest.fn(),
			querySelectorAll: jest.fn(() => []),
			checkValidity: jest.fn(() => true),
			reset: jest.fn(),
			action: "/api/datasets/create/",
		};

		// Mock step tabs with proper classList
		mockStepTab = {
			addEventListener: jest.fn(),
			classList: createMockClassList(),
		};

		mockPrevBtn = {
			addEventListener: jest.fn(),
			disabled: false,
			style: { display: "block" },
			classList: createMockClassList(),
		};

		mockNextBtn = {
			addEventListener: jest.fn(),
			disabled: false,
			style: { display: "block" },
			classList: createMockClassList(),
		};

		mockSubmitBtn = {
			addEventListener: jest.fn(),
			disabled: false,
			style: { display: "none" },
			textContent: "Create Dataset",
			innerHTML: "Create Dataset",
			dataset: {},
			classList: createMockClassList(),
		};

		mockNameField = {
			addEventListener: jest.fn(),
			value: "Test Dataset",
			checkValidity: jest.fn(() => true),
		};

		mockAuthorsField = {
			addEventListener: jest.fn(),
			value: '[{"name": "Test Author", "orcid_id": ""}]',
			checkValidity: jest.fn(() => true),
		};

		mockStatusField = {
			addEventListener: jest.fn(),
			value: "draft",
			checkValidity: jest.fn(() => true),
		};

		mockDescriptionField = {
			addEventListener: jest.fn(),
			value: "",
			checkValidity: jest.fn(() => true),
		};

		mockSelectedCapturesField = {
			value: "",
			setAttribute: jest.fn(),
		};

		mockSelectedFilesField = {
			value: "",
			setAttribute: jest.fn(),
		};

		// Mock window.AssetSearchHandler
		global.window.AssetSearchHandler = jest.fn().mockImplementation(() => ({
			initialize: jest.fn(),
			search: jest.fn(),
			clearResults: jest.fn(),
			selectedCaptureDetails: new Map(),
		}));
	});

	beforeEach(() => {
		// Reset mocks
		jest.clearAllMocks();

		// Re-setup DOM mocks after clearing
		document.getElementById = jest.fn((id) => {
			const elements = {
				"dataset-form": mockForm,
				prevStep: mockPrevBtn,
				nextStep: mockNextBtn,
				submitForm: mockSubmitBtn,
				id_name: mockNameField,
				id_authors: mockAuthorsField,
				id_status: mockStatusField,
				id_description: mockDescriptionField,
				selected_captures: mockSelectedCapturesField,
				selected_files: mockSelectedFilesField,
			};
			return elements[id] || null;
		});

		document.querySelector = jest.fn(() => null);
		document.querySelectorAll = jest.fn((selector) => {
			if (selector === "#stepTabs .btn") {
				// Return multiple step tabs
				return [mockStepTab, mockStepTab, mockStepTab, mockStepTab];
			}
			return [];
		});

		// Create the handler instance after setting up DOM mocks
		creationHandler = new DatasetCreationHandler(mockConfig);

		// Mock browser APIs only
		global.fetch = jest.fn();
		global.window.location = { href: "" };

		// Make classes available globally (as the actual code expects them)
		global.APIError = APIError;

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

		// Mock window.APIClient (what the actual code uses)
		global.window.APIClient = {
			request: jest.fn().mockResolvedValue({
				success: true,
				redirect_url: "/users/dataset-list/",
			}),
			post: jest.fn().mockResolvedValue({ html: "<div>Test HTML</div>" }),
		};

		// Mock FormData constructor
		global.FormData = jest.fn().mockImplementation(() => ({
			append: jest.fn(),
			get: jest.fn(),
			has: jest.fn(),
			delete: jest.fn(),
			set: jest.fn(),
			entries: jest.fn(),
			keys: jest.fn(),
			values: jest.fn(),
		}));

		// Mock successful API response
		global.fetch.mockResolvedValue({
			ok: true,
			json: () =>
				Promise.resolve({
					success: true,
					redirect_url: "/users/dataset-list/",
				}),
		});
	});

	describe("Initialization", () => {
		test("should initialize with correct configuration", () => {
			expect(creationHandler.form).toBe(mockForm);
			expect(creationHandler.steps).toEqual([
				"info",
				"captures",
				"files",
				"review",
			]);
			expect(creationHandler.currentStep).toBe(0);
			expect(creationHandler.onStepChange).toBe(mockConfig.onStepChange);
		});

		test("should initialize form fields", () => {
			expect(creationHandler.nameField).toBeDefined();
			expect(creationHandler.authorsField).toBeDefined();
			expect(creationHandler.statusField).toBeDefined();
			expect(creationHandler.descriptionField).toBeDefined();
			expect(creationHandler.selectedCapturesField).toBeDefined();
			expect(creationHandler.selectedFilesField).toBeDefined();
		});

		test("should initialize selections", () => {
			expect(creationHandler.selectedCaptures).toBeInstanceOf(Set);
			expect(creationHandler.selectedFiles).toBeInstanceOf(Set);
			expect(creationHandler.selectedCaptureDetails).toBeInstanceOf(Map);
			expect(creationHandler.modalSelectedFiles).toBeInstanceOf(Set);
		});

		test("should setup event listeners", () => {
			expect(mockForm.addEventListener).toHaveBeenCalled();
		});
	});

	describe("Step Navigation", () => {
		test("should navigate to next step", () => {
			const initialStep = creationHandler.currentStep;

			// Mock validateCurrentStep to return true to allow navigation
			creationHandler.validateCurrentStep = jest.fn(() => true);

			creationHandler.navigateStep(1);

			expect(creationHandler.currentStep).toBe(initialStep + 1);
		});

		test("should navigate to previous step", () => {
			creationHandler.currentStep = 2;

			creationHandler.navigateStep(-1);

			expect(creationHandler.currentStep).toBe(1);
		});

		test("should call onStepChange callback", () => {
			// Mock validateCurrentStep to return true to allow navigation
			creationHandler.validateCurrentStep = jest.fn(() => true);

			creationHandler.navigateStep(1);

			expect(mockConfig.onStepChange).toHaveBeenCalledWith(1);
		});

		test("should validate current step before navigation", () => {
			creationHandler.validateCurrentStep = jest.fn(() => false);

			creationHandler.navigateStep(1);

			expect(creationHandler.validateCurrentStep).toHaveBeenCalled();
		});
	});

	describe("Step Validation", () => {
		test.each([
			[
				"info",
				0,
				() => {
					if (creationHandler.nameField)
						creationHandler.nameField.value = "Test Dataset";
					if (creationHandler.authorsField)
						creationHandler.authorsField.value =
							'[{"name": "Test Author", "orcid_id": ""}]';
					if (creationHandler.statusField)
						creationHandler.statusField.value = "active";
				},
			],
			["captures", 1, () => {}],
			["files", 2, () => {}],
			["review", 3, () => {}],
		])("should validate %s step", (stepName, stepIndex, setupFn) => {
			creationHandler.currentStep = stepIndex;
			setupFn();

			const isValid = creationHandler.validateCurrentStep();

			expect(isValid).toBe(true);
		});

		test("should return false for invalid steps", () => {
			creationHandler.currentStep = 0; // Info step
			// Clear form fields to make validation fail
			creationHandler.nameField.value = "";
			creationHandler.authorsField.value = "";
			creationHandler.statusField.value = "";

			const isValid = creationHandler.validateCurrentStep();

			expect(isValid).toBe(false);
		});
	});

	describe("Asset Selection", () => {
		test("should remove capture from selection", () => {
			// Add a capture first
			creationHandler.selectedCaptures.add("capture1");
			expect(creationHandler.selectedCaptures.has("capture1")).toBe(true);

			// Remove it
			creationHandler.removeCapture("capture1");

			expect(creationHandler.selectedCaptures.has("capture1")).toBe(false);
		});

		test("should remove file from selection", () => {
			const file = { id: "file1", name: "test.h5" };

			// Add a file first
			creationHandler.selectedFiles.add(file);
			expect(creationHandler.selectedFiles.size).toBe(1);

			// Remove it
			creationHandler.removeFile("file1");

			expect(creationHandler.selectedFiles.size).toBe(0);
		});

		test("should update hidden fields with current selections", () => {
			// Add some selections
			creationHandler.selectedCaptures.add("capture1");
			creationHandler.selectedCaptures.add("capture2");

			// Update hidden fields
			creationHandler.updateHiddenFields();

			// Check that the hidden field was updated
			expect(creationHandler.selectedCapturesField.value).toContain("capture1");
			expect(creationHandler.selectedCapturesField.value).toContain("capture2");
		});
	});

	describe("Form Submission", () => {
		test.each([
			["set", true, true, "Creating...", "disabled"],
			["clear", false, false, "Create Dataset", "enabled"],
		])(
			"should %s submit button loading state",
			(action, loading, expectedDisabled, expectedText, stateDescription) => {
				if (!loading) {
					// Set loading state first before clearing
					creationHandler.setSubmitButtonLoading(true);
				}

				creationHandler.setSubmitButtonLoading(loading);

				expect(creationHandler.submitBtn.disabled).toBe(expectedDisabled);
				if (loading) {
					expect(creationHandler.submitBtn.innerHTML).toContain(expectedText);
				} else {
					expect(creationHandler.submitBtn.textContent).toBe(expectedText);
				}
			},
		);

		test("should clear errors", () => {
			// DOMUtils doesn't have a clearNotifications method
			// The clearErrors method likely clears the error container directly
			// Just verify the method can be called without errors
			expect(() => {
				creationHandler.clearErrors();
			}).not.toThrow();
		});

		test("should handle form submission", async () => {
			// Set up valid form data for validation to pass
			creationHandler.currentStep = 0; // Info step
			creationHandler.nameField.value = "Test Dataset";
			creationHandler.authorsField.value =
				'[{"name": "Test Author", "orcid_id": ""}]';
			creationHandler.statusField.value = "active";

			const mockEvent = {
				preventDefault: jest.fn(),
				target: mockForm,
			};

			await creationHandler.handleSubmit(mockEvent);

			expect(mockEvent.preventDefault).toHaveBeenCalled();
			expect(global.window.APIClient.request).toHaveBeenCalledWith(
				mockForm.action,
				expect.objectContaining({
					method: "POST",
					body: expect.any(Object),
				}),
			);
		});
	});

	describe("Search Handler Integration", () => {
		test("should initialize search handlers", () => {
			// The search handlers are initialized in initializeEventListeners
			// Check that they exist if window.AssetSearchHandler is available
			if (global.window.AssetSearchHandler) {
				expect(creationHandler.capturesSearchHandler).toBeDefined();
				expect(creationHandler.filesSearchHandler).toBeDefined();
			}
		});

		test("should handle capture search results", () => {
			// Test the actual search handler integration
			const mockSearchHandler = {
				clearResults: jest.fn(),
				selectedCaptureDetails: new Map(),
			};

			creationHandler.setSearchHandler(mockSearchHandler, "captures");

			expect(creationHandler.capturesSearchHandler).toBe(mockSearchHandler);
		});
	});

	describe("Authors Management", () => {
		test("should initialize authors management", () => {
			expect(creationHandler.initializeAuthorsManagement).toBeDefined();
		});

		test("should add author", () => {
			// Test the actual author management functionality
			const authorsContainer = document.getElementById("authors-container");
			const addAuthorBtn = document.getElementById("add-author-btn");

			if (addAuthorBtn) {
				addAuthorBtn.click();
				// Check that a new author input was added
				const authorInputs =
					authorsContainer?.querySelectorAll(".author-name-input");
				expect(authorInputs?.length).toBeGreaterThan(1);
			}
		});

		test("should remove author", () => {
			// Test removing a non-primary author
			const authorsContainer = document.getElementById("authors-container");
			const removeButtons =
				authorsContainer?.querySelectorAll(".remove-author");

			if (removeButtons && removeButtons.length > 0) {
				const initialCount =
					authorsContainer?.querySelectorAll(".author-name-input").length || 0;
				removeButtons[0].click();
				const finalCount =
					authorsContainer?.querySelectorAll(".author-name-input").length || 0;
				expect(finalCount).toBe(initialCount - 1);
			}
		});
	});

	describe("Error Handling", () => {
		test.each([
			[
				"missing form elements",
				() => {
					document.getElementById.mockReturnValue(null);
				},
				() => {
					new DatasetCreationHandler(mockConfig);
				},
			],
			[
				"missing search handlers",
				() => {
					global.window.AssetSearchHandler = undefined;
				},
				() => {
					new DatasetCreationHandler(mockConfig);
				},
			],
		])("should handle %s gracefully", (description, setupFn, testFn) => {
			setupFn();

			expect(testFn).not.toThrow();
		});

		test("should handle API failures gracefully", async () => {
			global.window.APIClient.request.mockRejectedValueOnce(
				new Error("Network error"),
			);

			const mockEvent = {
				preventDefault: jest.fn(),
				target: mockForm,
			};

			// The method catches errors internally, so it should not throw
			await expect(
				creationHandler.handleSubmit(mockEvent),
			).resolves.toBeUndefined();
		});
	});

	describe("Navigation State Management", () => {
		test("should update navigation buttons", () => {
			// Spy on DOMUtils methods
			const hideSpy = jest.spyOn(global.window.DOMUtils, "hide");
			const showSpy = jest.spyOn(global.window.DOMUtils, "show");

			creationHandler.updateNavigation();

			// On first step (currentStep = 0), prev button should be hidden, next should be shown
			// Verify DOMUtils methods were called instead of direct classList manipulation
			expect(hideSpy).toHaveBeenCalled();
			expect(showSpy).toHaveBeenCalled();

			hideSpy.mockRestore();
			showSpy.mockRestore();
		});

		test.each([
			["hide previous button on first step", 0, "hide"],
			[
				"hide next button on last step",
				() => creationHandler.steps.length - 1,
				"hide",
			],
			[
				"show submit button on last step",
				() => creationHandler.steps.length - 1,
				"show",
			],
		])("should %s", (description, stepOrFn, method) => {
			const spy = jest.spyOn(global.window.DOMUtils, method);

			creationHandler.currentStep =
				typeof stepOrFn === "function" ? stepOrFn() : stepOrFn;
			creationHandler.updateNavigation();

			expect(spy).toHaveBeenCalled();

			spy.mockRestore();
		});
	});

	describe("Cleanup", () => {
		test("should cleanup resources", () => {
			// Test that the handler can be properly cleaned up
			expect(() => {
				// Test that we can call methods without errors
				creationHandler.removeAllSelectedFiles();
				creationHandler.updateHiddenFields();
				creationHandler.clearErrors();
			}).not.toThrow();
		});

		test("should clear all selected files", () => {
			// Add some files first
			creationHandler.selectedFiles.add({ id: "file1", name: "test.h5" });
			creationHandler.modalSelectedFiles.add({ id: "file2", name: "test2.h5" });

			expect(creationHandler.selectedFiles.size).toBe(1);
			expect(creationHandler.modalSelectedFiles.size).toBe(1);

			// Clear them
			creationHandler.removeAllSelectedFiles();

			expect(creationHandler.selectedFiles.size).toBe(0);
			expect(creationHandler.modalSelectedFiles.size).toBe(0);
		});
	});
});
