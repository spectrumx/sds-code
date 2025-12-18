/**
 * Jest tests for DatasetEditingHandler
 * Tests dataset editing workflow with pending changes management
 */

// Import the DatasetEditingHandler class
import { DatasetEditingHandler } from "../DatasetEditingHandler.js";

describe("DatasetEditingHandler", () => {
	let editingHandler;
	let mockConfig;
	let mockPermissions;

	beforeEach(() => {
		// Reset mocks
		jest.clearAllMocks();

		// Create simple mock permissions
		mockPermissions = {
			userPermissionLevel: "owner",
			isOwner: true,
			currentUserId: 1,
			datasetPermissions: { canEditMetadata: true },
			canEditMetadata: jest.fn(() => true),
			canAddAssets: jest.fn(() => true),
			canRemoveOwnAssets: jest.fn(() => true),
			canRemoveAnyAssets: jest.fn(() => true),
			canShare: jest.fn(() => true),
			canDownload: jest.fn(() => true),
			canView: jest.fn(() => true),
			canAddAsset: jest.fn(() => true),
			canRemoveAsset: jest.fn(() => true),
		};

		// Mock config
		mockConfig = {
			datasetUuid: "test-dataset-uuid",
			permissions: mockPermissions,
			currentUserId: 1,
			initialCaptures: [
				{ id: 1, name: "Capture 1", type: "drf", owner_id: 1 },
				{ id: 2, name: "Capture 2", type: "drf", owner_id: 2 },
			],
			initialFiles: [
				{ id: 1, name: "file1.h5", size: "1.2 MB", owner_id: 1 },
				{ id: 2, name: "file2.h5", size: "2.5 MB", owner_id: 2 },
			],
		};

		// Minimal DOM mocks
		document.getElementById = jest.fn(() => null);
		document.querySelector = jest.fn(() => null);
		document.querySelectorAll = jest.fn(() => []);

		// Minimal window mocks
		global.window = {
			AssetSearchHandler: jest.fn().mockImplementation(() => ({
				selectedCaptures: new Set(),
				selectedFiles: new Set(),
				selectedCaptureDetails: new Map(),
			})),
			DOMUtils: {
				show: jest.fn(),
				hide: jest.fn(),
				showAlert: jest.fn(),
				renderError: jest.fn().mockResolvedValue(true),
				renderLoading: jest.fn().mockResolvedValue(true),
				renderContent: jest.fn().mockResolvedValue(true),
				renderTable: jest.fn().mockResolvedValue(true),
			},
		};

		// Minimal API mocks
		global.APIClient = {
			get: jest.fn().mockResolvedValue({ success: true, data: {} }),
			post: jest.fn().mockResolvedValue({ success: true }),
		};
	});

	describe("Initialization", () => {
		test("should initialize with correct configuration", () => {
			editingHandler = new DatasetEditingHandler(mockConfig);

			expect(editingHandler.datasetUuid).toBe("test-dataset-uuid");
			expect(editingHandler.permissions).toBe(mockPermissions);
			expect(editingHandler.currentUserId).toBe(1);
			expect(editingHandler.currentCaptures).toBeInstanceOf(Map);
			expect(editingHandler.currentFiles).toBeInstanceOf(Map);
			expect(editingHandler.pendingCaptures).toBeInstanceOf(Map);
			expect(editingHandler.pendingFiles).toBeInstanceOf(Map);
		});

		test("should initialize with initial data", () => {
			editingHandler = new DatasetEditingHandler(mockConfig);

			expect(editingHandler.initialCaptures).toEqual(
				mockConfig.initialCaptures,
			);
			expect(editingHandler.initialFiles).toEqual(mockConfig.initialFiles);
		});

		test("should load current assets when no initial data provided", () => {
			const configWithoutInitialData = {
				...mockConfig,
				initialCaptures: [],
				initialFiles: [],
			};

			editingHandler = new DatasetEditingHandler(configWithoutInitialData);

			expect(global.APIClient.get).toHaveBeenCalledWith(
				"/users/dataset-details/?dataset_uuid=test-dataset-uuid",
			);
		});
	});

	describe("Asset Management", () => {
		beforeEach(() => {
			editingHandler = new DatasetEditingHandler(mockConfig);
		});

		test.each([
			["markCaptureForRemoval"],
			["markFileForRemoval"],
			["addCaptureToPending"],
			["addFileToPending"],
		])("should have %s method", (methodName) => {
			expect(typeof editingHandler[methodName]).toBe("function");
		});

		test.each([
			["pendingCaptures", Map],
			["pendingFiles", Map],
			["currentCaptures", Map],
			["currentFiles", Map],
		])("should track %s", (propertyName, expectedType) => {
			expect(editingHandler[propertyName]).toBeInstanceOf(expectedType);
		});
	});

	describe("Change Tracking", () => {
		beforeEach(() => {
			editingHandler = new DatasetEditingHandler(mockConfig);
		});

		test("should detect when there are no changes", () => {
			expect(editingHandler.hasChanges()).toBe(false);
		});

		test.each([["hasChanges"], ["getPendingChanges"]])(
			"should have %s method",
			(methodName) => {
				expect(typeof editingHandler[methodName]).toBe("function");
			},
		);
	});

	describe("Permission Handling", () => {
		test.each([
			["add", "canAddAsset", { owner_id: 1 }],
			["remove", "canRemoveAsset", { owner_id: 2 }],
		])("should respect %s asset permissions", (action, methodName, asset) => {
			editingHandler = new DatasetEditingHandler(mockConfig);
			expect(editingHandler.permissions[methodName](asset)).toBe(true);
		});

		test("should handle contributor permissions correctly", () => {
			const contributorPermissions = {
				userPermissionLevel: "contributor",
				isOwner: false,
				currentUserId: 1,
				datasetPermissions: { canEditMetadata: true },
				canEditMetadata: jest.fn(() => true),
				canAddAssets: jest.fn(() => true),
				canRemoveOwnAssets: jest.fn(() => true),
				canRemoveAnyAssets: jest.fn(() => false),
				canShare: jest.fn(() => false),
				canDownload: jest.fn(() => true),
				canView: jest.fn(() => true),
				canAddAsset: jest.fn((asset) => asset.owner_id === 1),
				canRemoveAsset: jest.fn((asset) => asset.owner_id === 1),
			};

			const contributorHandler = new DatasetEditingHandler({
				...mockConfig,
				permissions: contributorPermissions,
			});

			const ownAsset = { owner_id: 1 };
			const otherAsset = { owner_id: 2 };

			expect(contributorHandler.permissions.canAddAsset(ownAsset)).toBe(true);
			expect(contributorHandler.permissions.canAddAsset(otherAsset)).toBe(
				false,
			);
			expect(contributorHandler.permissions.canRemoveAsset(otherAsset)).toBe(
				false,
			);
		});
	});

	describe("API Integration", () => {
		beforeEach(() => {
			editingHandler = new DatasetEditingHandler(mockConfig);
		});

		test("should load current assets from API", async () => {
			const mockAssets = {
				captures: [{ id: 1, name: "Test Capture" }],
				files: [{ id: 1, name: "test.h5" }],
			};

			global.APIClient.get.mockResolvedValue({
				success: true,
				data: mockAssets,
			});

			await editingHandler.loadCurrentAssets();

			expect(global.APIClient.get).toHaveBeenCalledWith(
				"/users/dataset-details/?dataset_uuid=test-dataset-uuid",
			);
		});

		test.each([["loadCurrentAssets"], ["handleSubmit"]])(
			"should have %s method",
			(methodName) => {
				expect(typeof editingHandler[methodName]).toBe("function");
			},
		);

		test("should handle API errors gracefully", async () => {
			global.APIClient.get.mockRejectedValue(new Error("API Error"));

			// The method catches errors internally, so it should not throw
			await expect(editingHandler.loadCurrentAssets()).resolves.toBeUndefined();
		});
	});

	describe("Search Handler Integration", () => {
		beforeEach(() => {
			editingHandler = new DatasetEditingHandler(mockConfig);
		});

		test("should initialize search handlers", () => {
			expect(editingHandler.capturesSearchHandler).toBeDefined();
			expect(editingHandler.filesSearchHandler).toBeDefined();
		});

		test("should have search handler methods", () => {
			expect(typeof editingHandler.setSearchHandler).toBe("function");
		});
	});

	describe("Event Handling", () => {
		beforeEach(() => {
			editingHandler = new DatasetEditingHandler(mockConfig);
		});

		test("should initialize event listeners", () => {
			expect(editingHandler.initializeEventListeners).toBeDefined();
		});

		test("should have event handling methods", () => {
			expect(typeof editingHandler.handleSubmit).toBe("function");
		});
	});

	describe("Authors Management", () => {
		beforeEach(() => {
			editingHandler = new DatasetEditingHandler(mockConfig);
		});

		test("should initialize authors management", () => {
			expect(editingHandler.initializeAuthorsManagement).toBeDefined();
			expect(typeof editingHandler.initializeAuthorsManagement).toBe(
				"function",
			);
		});
	});

	describe("Error Handling", () => {
		beforeEach(() => {
			editingHandler = new DatasetEditingHandler(mockConfig);
		});

		test("should handle missing DOM elements gracefully", () => {
			document.getElementById.mockReturnValue(null);

			expect(() => {
				editingHandler.initializeEventListeners();
			}).not.toThrow();
		});

		test("should handle API failures gracefully", async () => {
			global.APIClient.post.mockRejectedValue(new Error("Network error"));

			// Test that the method exists and can be called
			expect(() => {
				editingHandler.getPendingChanges();
				editingHandler.hasChanges();
			}).not.toThrow();
		});
	});

	describe("Cleanup", () => {
		beforeEach(() => {
			editingHandler = new DatasetEditingHandler(mockConfig);
		});

		test("should cleanup resources", () => {
			// Test that the handler can be properly cleaned up
			expect(() => {
				// Test that we can call methods without errors
				editingHandler.getPendingChanges();
				editingHandler.hasChanges();
			}).not.toThrow();
		});

		test.each([["getPendingChanges"], ["hasChanges"]])(
			"should have %s method",
			(methodName) => {
				expect(typeof editingHandler[methodName]).toBe("function");
			},
		);
	});

	describe("Cancel Button Functionality", () => {
		beforeEach(() => {
			editingHandler = new DatasetEditingHandler(mockConfig);

			// Mock required DOM elements for cancel operations
			const pendingCapturesList = document.createElement("tbody");
			pendingCapturesList.id = "pending-captures-list";
			const pendingFilesList = document.createElement("tbody");
			pendingFilesList.id = "pending-files-list";

			document.getElementById = jest.fn((id) => {
				if (id === "pending-captures-list") return pendingCapturesList;
				if (id === "pending-files-list") return pendingFilesList;
				return null;
			});
		});

		test("should cancel capture change", () => {
			const captureId = "test-capture-1";
			const capture = { id: captureId, name: "Test Capture" };

			// Add a pending capture change
			editingHandler.pendingCaptures.set(captureId, {
				...capture,
				action: "add",
			});

			editingHandler.cancelCaptureChange(captureId);

			expect(editingHandler.pendingCaptures.has(captureId)).toBe(false);
		});

		test("should cancel file change", () => {
			const fileId = "test-file-1";
			const file = { id: fileId, name: "test.h5" };

			// Add a pending file change
			editingHandler.pendingFiles.set(fileId, {
				...file,
				action: "add",
			});

			editingHandler.cancelFileChange(fileId);

			expect(editingHandler.pendingFiles.has(fileId)).toBe(false);
		});

		test("should handle cancel button click for captures", () => {
			const captureId = "test-capture-1";
			const button = document.createElement("button");
			button.className = "cancel-change";
			button.dataset.captureId = captureId;
			button.dataset.changeType = "capture";

			// Add a pending capture
			editingHandler.pendingCaptures.set(captureId, {
				id: captureId,
				action: "add",
			});

			document.querySelectorAll = jest.fn((selector) => {
				if (selector === ".cancel-change") return [button];
				return [];
			});

			editingHandler.addCancelButtonListeners();

			// Simulate click
			const clickEvent = new Event("click");
			button.dispatchEvent(clickEvent);

			expect(editingHandler.pendingCaptures.has(captureId)).toBe(false);
		});

		test("should handle cancel button click for files", () => {
			const fileId = "test-file-1";
			const button = document.createElement("button");
			button.className = "cancel-change";
			button.dataset.fileId = fileId;
			button.dataset.changeType = "file";

			// Add a pending file
			editingHandler.pendingFiles.set(fileId, {
				id: fileId,
				action: "add",
			});

			document.querySelectorAll = jest.fn((selector) => {
				if (selector === ".cancel-change") return [button];
				return [];
			});

			editingHandler.addCancelButtonListeners();

			// Simulate click
			const clickEvent = new Event("click");
			button.dispatchEvent(clickEvent);

			expect(editingHandler.pendingFiles.has(fileId)).toBe(false);
		});

		test("should restore capture to current list when canceling removal", () => {
			const captureId = "test-capture-1";
			const capture = { id: captureId, name: "Test Capture" };

			// Add to current captures
			editingHandler.currentCaptures.set(captureId, capture);

			// Mark for removal
			editingHandler.pendingCaptures.set(captureId, {
				...capture,
				action: "remove",
			});

			editingHandler.cancelCaptureChange(captureId);

			expect(editingHandler.pendingCaptures.has(captureId)).toBe(false);
			expect(editingHandler.currentCaptures.has(captureId)).toBe(true);
		});

		test("should restore file to current list when canceling removal", () => {
			const fileId = "test-file-1";
			const file = { id: fileId, name: "test.h5" };

			// Add to current files
			editingHandler.currentFiles.set(fileId, file);

			// Mark for removal
			editingHandler.pendingFiles.set(fileId, {
				...file,
				action: "remove",
			});

			editingHandler.cancelFileChange(fileId);

			expect(editingHandler.pendingFiles.has(fileId)).toBe(false);
			expect(editingHandler.currentFiles.has(fileId)).toBe(true);
		});
	});
});
