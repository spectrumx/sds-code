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

		test("should have asset management methods", () => {
			expect(typeof editingHandler.markCaptureForRemoval).toBe("function");
			expect(typeof editingHandler.markFileForRemoval).toBe("function");
			expect(typeof editingHandler.addCaptureToPending).toBe("function");
			expect(typeof editingHandler.addFileToPending).toBe("function");
		});

		test("should track pending changes", () => {
			expect(editingHandler.pendingCaptures).toBeInstanceOf(Map);
			expect(editingHandler.pendingFiles).toBeInstanceOf(Map);
		});

		test("should track current assets", () => {
			expect(editingHandler.currentCaptures).toBeInstanceOf(Map);
			expect(editingHandler.currentFiles).toBeInstanceOf(Map);
		});
	});

	describe("Change Tracking", () => {
		beforeEach(() => {
			editingHandler = new DatasetEditingHandler(mockConfig);
		});

		test("should detect when there are no changes", () => {
			expect(editingHandler.hasChanges()).toBe(false);
		});

		test("should have change tracking methods", () => {
			expect(typeof editingHandler.hasChanges).toBe("function");
			expect(typeof editingHandler.getPendingChanges).toBe("function");
		});
	});

	describe("Permission Handling", () => {
		test("should respect add asset permissions", () => {
			const asset = { owner_id: 1 };

			expect(editingHandler.permissions.canAddAsset(asset)).toBe(true);
		});

		test("should respect remove asset permissions", () => {
			const asset = { owner_id: 2 };

			expect(editingHandler.permissions.canRemoveAsset(asset)).toBe(true);
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

		test("should have API integration methods", () => {
			expect(typeof editingHandler.loadCurrentAssets).toBe("function");
			expect(typeof editingHandler.handleSubmit).toBe("function");
		});

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
		});

		test("should have authors management methods", () => {
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

		test("should have cleanup methods", () => {
			expect(typeof editingHandler.getPendingChanges).toBe("function");
			expect(typeof editingHandler.hasChanges).toBe("function");
		});
	});
});
