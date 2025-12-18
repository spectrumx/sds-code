/**
 * Jest tests for DatasetModeManager
 * Tests dataset creation and editing mode management
 */

// Import PermissionLevels to set up window.PermissionLevels
import "../../constants/PermissionLevels.js";
// Mock dependencies first
jest.mock("../../core/PermissionsManager");
jest.mock("../DatasetEditingHandler");
jest.mock("../DatasetCreationHandler");

import { PermissionsManager } from "../../core/PermissionsManager.js";
import { DatasetCreationHandler } from "../DatasetCreationHandler.js";
import { DatasetEditingHandler } from "../DatasetEditingHandler.js";
// Import the DatasetModeManager class
import { DatasetModeManager } from "../DatasetModeManager.js";

describe("DatasetModeManager", () => {
	let modeManager;
	let mockConfig;

	beforeEach(() => {
		// Reset mocks
		jest.clearAllMocks();

		// Mock config for edit mode
		mockConfig = {
			datasetUuid: "test-dataset-uuid",
			userPermissionLevel: "owner",
			currentUserId: 1,
			isOwner: true,
			datasetPermissions: {
				canEditMetadata: true,
				canAddAssets: true,
			},
		};

		// Mock PermissionsManager instance
		const mockPermissions = {
			canEditMetadata: jest.fn(() => true),
			canAddAssets: jest.fn(() => true),
			canRemoveAnyAssets: jest.fn(() => true),
			canRemoveOwnAssets: jest.fn(() => true),
			canShare: jest.fn(() => true),
			canDownload: jest.fn(() => true),
			canView: jest.fn(() => true),
		};

		// Mock the constructor
		PermissionsManager.mockImplementation(() => mockPermissions);

		// Mock handler instances
		const mockEditingHandler = {
			initialize: jest.fn(),
			setupEventListeners: jest.fn(),
			loadDatasetData: jest.fn(),
			filesSearchHandler: {
				initialize: jest.fn(),
				search: jest.fn(),
			},
		};

		const mockCreationHandler = {
			initialize: jest.fn(),
			setupEventListeners: jest.fn(),
			filesSearchHandler: {
				initialize: jest.fn(),
				search: jest.fn(),
			},
		};

		DatasetEditingHandler.mockImplementation(() => mockEditingHandler);
		DatasetCreationHandler.mockImplementation(() => mockCreationHandler);
	});

	describe("Edit Mode Initialization", () => {
		beforeEach(() => {
			modeManager = new DatasetModeManager(mockConfig);
		});

		test("should initialize in edit mode when datasetUuid is provided", () => {
			expect(modeManager.isEditMode).toBe(true);
			expect(modeManager.config).toEqual(mockConfig);
		});

		test("should initialize PermissionsManager with correct config", () => {
			expect(modeManager.permissions).toBeDefined();
			expect(modeManager.permissions.userPermissionLevel).toBe("owner");
			expect(modeManager.permissions.datasetUuid).toBe("test-dataset-uuid");
		});

		test("should initialize DatasetEditingHandler in edit mode", () => {
			expect(modeManager.handler).toBeDefined();
			expect(modeManager.isEditMode).toBe(true);
			// Verify it's actually a DatasetEditingHandler by checking for edit-specific methods
			expect(typeof modeManager.handler.markCaptureForRemoval).toBe("function");
			expect(typeof modeManager.handler.markFileForRemoval).toBe("function");
			expect(typeof modeManager.handler.getPendingChanges).toBe("function");
		});

		test("should set global reference for backward compatibility", () => {
			expect(window.datasetEditingHandler).toBeDefined();
		});

		test("should initialize step numbers correctly", () => {
			expect(modeManager.step1).toBe(0);
			expect(modeManager.step2).toBe(1);
			expect(modeManager.step3).toBe(2);
			expect(modeManager.step4).toBe(3);
		});
	});

	describe("Creation Mode Initialization", () => {
		beforeEach(() => {
			// Clean up any existing global reference
			window.datasetEditingHandler = undefined;

			const creationConfig = {
				...mockConfig,
				datasetUuid: null,
			};
			modeManager = new DatasetModeManager(creationConfig);
		});

		test("should initialize in creation mode when datasetUuid is null", () => {
			expect(modeManager.isEditMode).toBe(false);
		});

		test("should initialize DatasetCreationHandler in creation mode", () => {
			expect(modeManager.handler).toBeDefined();
			expect(modeManager.isEditMode).toBe(false);
			// Verify it's actually a DatasetCreationHandler by checking for creation-specific methods
			expect(typeof modeManager.handler.navigateStep).toBe("function");
			expect(typeof modeManager.handler.validateCurrentStep).toBe("function");
			expect(typeof modeManager.handler.updateReviewStep).toBe("function");
		});

		test("should not set global reference in creation mode", () => {
			expect(window.datasetEditingHandler).toBeUndefined();
		});
	});

	describe("Permission Management", () => {
		beforeEach(() => {
			modeManager = new DatasetModeManager(mockConfig);
		});

		test("should provide access to permissions manager", () => {
			expect(modeManager.permissions).toBeDefined();
			expect(modeManager.permissions.canEditMetadata()).toBe(true);
		});

		test("should delegate permission checks to PermissionsManager", () => {
			const result = modeManager.permissions.canAddAssets();
			expect(result).toBe(true);
			expect(modeManager.permissions).toBeDefined();
		});
	});

	describe("Handler Delegation", () => {
		beforeEach(() => {
			modeManager = new DatasetModeManager(mockConfig);
		});

		test("should delegate to appropriate handler based on mode", () => {
			expect(modeManager.handler).toBeDefined();

			if (modeManager.isEditMode) {
				// Edit mode should have editing-specific capabilities
				expect(typeof modeManager.handler.markCaptureForRemoval).toBe(
					"function",
				);
				expect(typeof modeManager.handler.markFileForRemoval).toBe("function");
				expect(typeof modeManager.handler.getPendingChanges).toBe("function");
				// Should NOT have creation-specific methods
				expect(typeof modeManager.handler.navigateStep).toBe("undefined");
				expect(typeof modeManager.handler.validateCurrentStep).toBe(
					"undefined",
				);
			} else {
				// Creation mode should have creation-specific capabilities
				expect(typeof modeManager.handler.navigateStep).toBe("function");
				expect(typeof modeManager.handler.validateCurrentStep).toBe("function");
				expect(typeof modeManager.handler.updateReviewStep).toBe("function");
				// Should NOT have editing-specific methods
				expect(typeof modeManager.handler.markCaptureForRemoval).toBe(
					"undefined",
				);
				expect(typeof modeManager.handler.getPendingChanges).toBe("undefined");
			}
		});

		test("should provide access to files search handler", () => {
			expect(modeManager.filesSearchHandler).toBeDefined();
			expect(typeof modeManager.filesSearchHandler).toBe("object");
		});
	});

	describe("Mode Detection", () => {
		test.each([
			["edit", "test-uuid", true],
			["creation", null, false],
			["creation", undefined, false],
			["creation", "", false],
		])(
			"should detect %s mode with %s datasetUuid",
			(modeName, datasetUuid, expectedEditMode) => {
				const config = datasetUuid === undefined ? {} : { datasetUuid };
				const manager = new DatasetModeManager(config);
				expect(manager.isEditMode).toBe(expectedEditMode);
			},
		);
	});

	describe("Configuration Management", () => {
		beforeEach(() => {
			modeManager = new DatasetModeManager(mockConfig);
		});

		test("should store configuration correctly", () => {
			expect(modeManager.config).toEqual(mockConfig);
		});

		test("should pass configuration to handlers", () => {
			expect(modeManager.handler).toBeDefined();
			expect(modeManager.config).toBeDefined();
		});
	});

	describe("Backward Compatibility", () => {
		test("should set global reference only in edit mode", () => {
			// Clear any existing global reference
			window.datasetEditingHandler = undefined;

			// Test edit mode
			const editManager = new DatasetModeManager({ datasetUuid: "test-uuid" });
			expect(window.datasetEditingHandler).toBeDefined();

			// Clear global reference
			window.datasetEditingHandler = undefined;

			// Test creation mode
			const creationManager = new DatasetModeManager({ datasetUuid: null });
			expect(window.datasetEditingHandler).toBeUndefined();
		});
	});

	describe("Error Handling", () => {
		test("should handle missing configuration gracefully", () => {
			expect(() => {
				new DatasetModeManager({});
			}).not.toThrow();
		});

		test("should handle invalid configuration gracefully", () => {
			expect(() => {
				new DatasetModeManager(null);
			}).toThrow();
		});
	});
	
	describe("Public/Private Dataset Management", () => {
		beforeEach(() => {
			modeManager = new DatasetModeManager(mockConfig);
		});

		test("should correctly identify existing public vs private datasets", () => {
			const publicConfig = {
				...mockConfig,
				existingDatasetIsPublic: true,
			};
			const privateConfig = {
				...mockConfig,
				existingDatasetIsPublic: false,
			};
			
			const publicManager = new DatasetModeManager(publicConfig);
			const privateManager = new DatasetModeManager(privateConfig);
			
			expect(publicManager.isExistingPublicDataset()).toBe(true);
			expect(privateManager.isExistingPublicDataset()).toBe(false);
		});

		test("should correctly detect public/private and final/draft status from DOM", () => {
			const publicOption = document.createElement("input");
			publicOption.id = "public-option";
			publicOption.type = "radio";
			publicOption.checked = true;
			
			const statusField = document.createElement("input");
			statusField.id = "id_status";
			statusField.value = "final";
			
			document.getElementById = jest.fn((id) => {
				if (id === "public-option") return publicOption;
				if (id === "id_status") return statusField;
				return null;
			});

			expect(modeManager.isCurrentSessionPublicDataset()).toBe(true);
			expect(modeManager.isCurrentSessionFinalDataset()).toBe(true);
			
			// Test draft/private combination
			publicOption.checked = false;
			statusField.value = "draft";
			
			expect(modeManager.isCurrentSessionPublicDataset()).toBe(false);
			expect(modeManager.isCurrentSessionFinalDataset()).toBe(false);
		});

		test("should update status badge for final status", () => {
			const statusBadge = document.createElement("span");
			statusBadge.id = "current-status-badge";
			document.getElementById = jest.fn((id) => {
				if (id === "current-status-badge") return statusBadge;
				return null;
			});

			modeManager.updateStatusBadge("final");
			expect(statusBadge.textContent).toBe("Final");
			expect(statusBadge.className).toBe("badge bg-success");
		});

		test("should update status badge for draft status", () => {
			const statusBadge = document.createElement("span");
			statusBadge.id = "current-status-badge";
			document.getElementById = jest.fn((id) => {
				if (id === "current-status-badge") return statusBadge;
				return null;
			});

			modeManager.updateStatusBadge("draft");
			expect(statusBadge.textContent).toBe("Draft");
			expect(statusBadge.className).toBe("badge bg-secondary");
		});

		test("should update card border for public dataset", () => {
			const publishingCard = document.createElement("div");
			publishingCard.id = "publishing-info-card";
			const addSpy = jest.spyOn(publishingCard.classList, "add");
			document.getElementById = jest.fn((id) => {
				if (id === "publishing-info-card") return publishingCard;
				return null;
			});

			modeManager.updateCardBorder(true);
			expect(addSpy).toHaveBeenCalledWith("border-danger", "border-3");
		});

		test("should remove card border for private dataset", () => {
			const publishingCard = document.createElement("div");
			publishingCard.id = "publishing-info-card";
			const removeSpy = jest.spyOn(publishingCard.classList, "remove");
			document.getElementById = jest.fn((id) => {
				if (id === "publishing-info-card") return publishingCard;
				return null;
			});

			modeManager.updateCardBorder(false);
			expect(removeSpy).toHaveBeenCalledWith("border-danger", "border-3");
		});

		test("should update submit button for publishing public dataset", () => {
			const submitBtn = document.createElement("button");
			submitBtn.id = "submitForm";
			submitBtn.classList = {
				contains: jest.fn(() => false),
			};
			// Mock offsetParent as read-only property
			Object.defineProperty(submitBtn, "offsetParent", {
				get: () => submitBtn,
				configurable: true,
			});

			const publishToggle = document.createElement("input");
			publishToggle.id = "publish-dataset-toggle";
			publishToggle.checked = true;

			const statusField = document.createElement("input");
			statusField.id = "id_status";
			statusField.value = "final";

			const publicOption = document.createElement("input");
			publicOption.id = "public-option";
			publicOption.checked = true;

			document.getElementById = jest.fn((id) => {
				const elements = {
					submitForm: submitBtn,
					"publish-dataset-toggle": publishToggle,
					id_status: statusField,
					"public-option": publicOption,
				};
				return elements[id] || null;
			});

			// Mock getComputedStyle
			window.getComputedStyle = jest.fn(() => ({
				display: "block",
			}));

			modeManager.updateSubmitButton();
			expect(submitBtn.className).toBe("btn btn-danger");
			expect(submitBtn.textContent).toBe("Publish Dataset");
		});

		test("should update submit button for publishing private dataset", () => {
			const submitBtn = document.createElement("button");
			submitBtn.id = "submitForm";
			submitBtn.classList = {
				contains: jest.fn(() => false),
			};
			// Mock offsetParent as read-only property
			Object.defineProperty(submitBtn, "offsetParent", {
				get: () => submitBtn,
				configurable: true,
			});

			const publishToggle = document.createElement("input");
			publishToggle.id = "publish-dataset-toggle";
			publishToggle.checked = true;

			const statusField = document.createElement("input");
			statusField.id = "id_status";
			statusField.value = "final";

			const publicOption = document.createElement("input");
			publicOption.id = "public-option";
			publicOption.checked = false;

			document.getElementById = jest.fn((id) => {
				const elements = {
					submitForm: submitBtn,
					"publish-dataset-toggle": publishToggle,
					id_status: statusField,
					"public-option": publicOption,
				};
				return elements[id] || null;
			});

			window.getComputedStyle = jest.fn(() => ({
				display: "block",
			}));

			modeManager.updateSubmitButton();
			expect(submitBtn.className).toBe("btn btn-warning");
			expect(submitBtn.textContent).toBe("Publish Dataset");
		});

		test("should update submit button for draft dataset", () => {
			const submitBtn = document.createElement("button");
			submitBtn.id = "submitForm";
			submitBtn.classList = {
				contains: jest.fn(() => false),
			};
			// Mock offsetParent as read-only property
			Object.defineProperty(submitBtn, "offsetParent", {
				get: () => submitBtn,
				configurable: true,
			});

			const publishToggle = document.createElement("input");
			publishToggle.id = "publish-dataset-toggle";
			publishToggle.checked = false;

			document.getElementById = jest.fn((id) => {
				const elements = {
					submitForm: submitBtn,
					"publish-dataset-toggle": publishToggle,
				};
				return elements[id] || null;
			});

			window.getComputedStyle = jest.fn(() => ({
				display: "block",
			}));

			modeManager.updateSubmitButton();
			expect(submitBtn.className).toBe("btn btn-success");
			expect(submitBtn.textContent).toBe("Update Dataset");
		});

		test("should update publishing info alerts for final and public", () => {
			const alertsContainer = document.createElement("div");
			alertsContainer.id = "publishing-alerts-container";

			const statusField = document.createElement("input");
			statusField.id = "id_status";
			statusField.value = "final";

			const publicOption = document.createElement("input");
			publicOption.id = "public-option";
			publicOption.checked = true;

			document.getElementById = jest.fn((id) => {
				const elements = {
					"publishing-alerts-container": alertsContainer,
					id_status: statusField,
					"public-option": publicOption,
				};
				return elements[id] || null;
			});

			modeManager.updatePublishingInfo();
			expect(alertsContainer.innerHTML).toContain(
				"This dataset will be published",
			);
			expect(alertsContainer.innerHTML).toContain(
				"This dataset will be publicly viewable",
			);
		});

		test("should update publishing info alerts for draft", () => {
			const alertsContainer = document.createElement("div");
			alertsContainer.id = "publishing-alerts-container";

			const statusField = document.createElement("input");
			statusField.id = "id_status";
			statusField.value = "draft";

			document.getElementById = jest.fn((id) => {
				const elements = {
					"publishing-alerts-container": alertsContainer,
					id_status: statusField,
				};
				return elements[id] || null;
			});

			modeManager.updatePublishingInfo();
			expect(alertsContainer.innerHTML).toContain(
				"This dataset will remain in <strong>Draft</strong> status",
			);
		});
	});
});
