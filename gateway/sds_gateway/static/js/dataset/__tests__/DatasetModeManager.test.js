/**
 * Jest tests for DatasetModeManager
 * Tests dataset creation and editing mode management
 */

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
			canRemoveAssets: jest.fn(() => true),
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
		test("should detect edit mode with valid datasetUuid", () => {
			const editConfig = { datasetUuid: "test-uuid" };
			const manager = new DatasetModeManager(editConfig);
			expect(manager.isEditMode).toBe(true);
		});

		test("should detect creation mode with null datasetUuid", () => {
			const creationConfig = { datasetUuid: null };
			const manager = new DatasetModeManager(creationConfig);
			expect(manager.isEditMode).toBe(false);
		});

		test("should detect creation mode with undefined datasetUuid", () => {
			const creationConfig = {};
			const manager = new DatasetModeManager(creationConfig);
			expect(manager.isEditMode).toBe(false);
		});

		test("should detect creation mode with empty string datasetUuid", () => {
			const creationConfig = { datasetUuid: "" };
			const manager = new DatasetModeManager(creationConfig);
			expect(manager.isEditMode).toBe(false);
		});
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
			delete window.datasetEditingHandler;

			// Test edit mode
			const editManager = new DatasetModeManager({ datasetUuid: "test-uuid" });
			expect(window.datasetEditingHandler).toBeDefined();

			// Clear global reference
			delete window.datasetEditingHandler;

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
});
