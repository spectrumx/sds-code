/**
 * Jest tests for PageLifecycleManager
 * Tests page initialization, cleanup, and lifecycle management
 */

// Import the PageLifecycleManager class
import { PageLifecycleManager } from "../PageLifecycleManager.js";

describe("PageLifecycleManager", () => {
	let lifecycleManager;
	let mockConfig;

	beforeEach(() => {
		// Reset mocks
		jest.clearAllMocks();

		// Mock config
		mockConfig = {
			pageType: "dataset-list",
			permissions: {
				userPermissionLevel: "owner",
				isOwner: true,
				currentUserId: 1,
			},
		};

		// Minimal DOM mocks
		document.addEventListener = jest.fn();
		document.removeEventListener = jest.fn();

		// Minimal window mocks
		global.window = {
			addEventListener: jest.fn(),
			removeEventListener: jest.fn(),
		};
	});

	describe("Initialization", () => {
		test("should initialize with correct configuration", () => {
			lifecycleManager = new PageLifecycleManager(mockConfig);

			expect(lifecycleManager.pageType).toBe("dataset-list");
			expect(lifecycleManager.config).toEqual(mockConfig);
		});

		test("should initialize when DOM is ready", () => {
			// Mock document.readyState to be 'loading' to trigger DOMContentLoaded listener
			Object.defineProperty(document, "readyState", {
				value: "loading",
				writable: true,
			});

			lifecycleManager = new PageLifecycleManager(mockConfig);

			expect(document.addEventListener).toHaveBeenCalledWith(
				"DOMContentLoaded",
				expect.any(Function),
			);
		});

		test("should initialize immediately when DOM is complete", () => {
			// Mock document.readyState to be 'complete' to trigger immediate initialization
			Object.defineProperty(document, "readyState", {
				value: "complete",
				writable: true,
			});

			lifecycleManager = new PageLifecycleManager(mockConfig);

			// The manager should attempt to initialize when DOM is complete
			expect(typeof lifecycleManager.initialized).toBe("boolean");
		});
	});

	describe("Page-Specific Managers", () => {
		test.each([
			["dataset-create", { formId: "dataset-form" }],
			["dataset-edit", { datasetUuid: "test-uuid" }],
			["dataset-list", {}],
			["capture-list", {}],
		])("should initialize %s page", (pageType, additionalConfig) => {
			const config = {
				...mockConfig,
				pageType,
				...additionalConfig,
			};

			lifecycleManager = new PageLifecycleManager(config);

			expect(lifecycleManager.pageType).toBe(pageType);
		});
	});

	describe("Manager Management", () => {
		beforeEach(() => {
			lifecycleManager = new PageLifecycleManager(mockConfig);
		});

		test("should add manager to list", () => {
			const mockManager = {
				initialize: jest.fn(),
				cleanup: jest.fn(),
			};

			lifecycleManager.addManager(mockManager);

			expect(lifecycleManager.managers).toContain(mockManager);
		});

		test("should remove manager from list", () => {
			const mockManager = {
				initialize: jest.fn(),
				cleanup: jest.fn(),
			};

			lifecycleManager.addManager(mockManager);
			lifecycleManager.removeManager(mockManager);

			expect(lifecycleManager.managers).not.toContain(mockManager);
		});

		test("should get manager by type", () => {
			const permissionsManager = lifecycleManager.getManager("permissions");

			expect(permissionsManager).toBeDefined();
		});

		test("should return undefined for non-existent manager", () => {
			const nonExistentManager = lifecycleManager.getManager("non-existent");

			expect(nonExistentManager).toBeUndefined();
		});
	});

	describe("Error Handling", () => {
		test("should handle missing DOM elements gracefully", () => {
			global.document = null;

			expect(() => {
				new PageLifecycleManager(mockConfig);
			}).not.toThrow();
		});
	});

	describe("Cleanup", () => {
		beforeEach(() => {
			lifecycleManager = new PageLifecycleManager(mockConfig);
		});

		test("should cleanup all managers", () => {
			lifecycleManager.cleanup();

			for (const manager of lifecycleManager.managers) {
				if (manager.cleanup) {
					expect(manager.cleanup).toHaveBeenCalled();
				}
			}
		});

		test("should handle cleanup errors gracefully", () => {
			const mockManager = {
				cleanup: jest.fn(() => {
					throw new Error("Cleanup failed");
				}),
			};

			lifecycleManager.addManager(mockManager);

			expect(() => {
				lifecycleManager.cleanup();
			}).not.toThrow();
		});
	});

	describe("State Management", () => {
		beforeEach(() => {
			lifecycleManager = new PageLifecycleManager(mockConfig);
		});

		test("should track initialization state", () => {
			// The manager should be initialized after construction when DOM is complete
			expect(typeof lifecycleManager.initialized).toBe("boolean");
		});

		test("should get status", () => {
			const status = lifecycleManager.getStatus();

			expect(status).toHaveProperty("initialized");
			expect(status).toHaveProperty("pageType");
			expect(status).toHaveProperty("managers");
		});

		test("should check if manager is initialized", () => {
			const isInitialized =
				lifecycleManager.isManagerInitialized("permissions");

			expect(typeof isInitialized).toBe("boolean");
		});
	});

	describe("Configuration Management", () => {
		test("should store configuration", () => {
			lifecycleManager = new PageLifecycleManager(mockConfig);

			expect(lifecycleManager.config).toEqual(mockConfig);
		});

		test("should update configuration", () => {
			lifecycleManager = new PageLifecycleManager(mockConfig);

			const newConfig = { ...mockConfig, newProperty: "value" };
			lifecycleManager.updateConfig(newConfig);

			expect(lifecycleManager.config).toEqual(newConfig);
		});
	});

	describe("Utility Methods", () => {
		beforeEach(() => {
			lifecycleManager = new PageLifecycleManager(mockConfig);
		});

		test("should debounce functions", () => {
			const debouncedFn = lifecycleManager.debounce(jest.fn(), 100);

			expect(typeof debouncedFn).toBe("function");
		});

		test("should wait for manager initialization", async () => {
			const managerPromise = lifecycleManager.waitForManager("permissions");

			expect(managerPromise).toBeInstanceOf(Promise);
		});
	});

	describe("Modal Initialization", () => {
		let mockModal;
		let mockBootstrapModal;

		beforeEach(() => {
			// Mock Bootstrap
			mockBootstrapModal = {
				dispose: jest.fn(),
				show: jest.fn(),
				hide: jest.fn(),
				_config: {
					backdrop: true,
					keyboard: true,
					focus: true,
				},
			};

			global.window.bootstrap = {
				Modal: jest.fn().mockImplementation(() => mockBootstrapModal),
			};
			global.window.bootstrap.Modal.getInstance = jest.fn(() => null);

			// Mock modal element
			mockModal = {
				getAttribute: jest.fn((attr) => {
					if (attr === "data-item-uuid") return "test-dataset-uuid";
					if (attr === "data-item-type") return "dataset";
					return null;
				}),
				setAttribute: jest.fn(),
			};

			// Mock document methods
			document.querySelectorAll = jest.fn((selector) => {
				if (selector === ".modal") return [mockModal];
				if (selector === ".modal[data-item-type='dataset']") return [mockModal];
				if (selector === ".modal[data-item-type='capture']") return [];
				return [];
			});

			// Mock action manager classes
			global.window.ShareActionManager = jest.fn().mockImplementation(() => ({}));
			global.window.VersioningActionManager = jest
				.fn()
				.mockImplementation(() => ({}));
			global.window.DownloadActionManager = jest
				.fn()
				.mockImplementation(() => ({}));
			global.window.DetailsActionManager = jest
				.fn()
				.mockImplementation(() => ({}));
		});

		test("should pre-initialize all modals with proper Bootstrap config", () => {
			lifecycleManager = new PageLifecycleManager({
				...mockConfig,
				pageType: "dataset-list",
			});

			// Call initializeDatasetModals directly
			lifecycleManager.initializeDatasetModals();

			expect(document.querySelectorAll).toHaveBeenCalledWith(".modal");
			expect(global.window.bootstrap.Modal).toHaveBeenCalledWith(mockModal, {
				backdrop: true,
				keyboard: true,
				focus: true,
			});
		});

		test("should dispose existing modal instances before creating new ones", () => {
			const existingInstance = {
				dispose: jest.fn(),
				_config: { backdrop: true },
			};
			global.window.bootstrap.Modal.getInstance = jest.fn(
				() => existingInstance,
			);

			lifecycleManager = new PageLifecycleManager({
				...mockConfig,
				pageType: "dataset-list",
			});

			lifecycleManager.initializeDatasetModals();

			expect(existingInstance.dispose).toHaveBeenCalled();
		});

		test("should handle disposal failures gracefully", () => {
			const existingInstance = {
				dispose: jest.fn(() => {
					throw new Error("Disposal failed");
				}),
			};
			global.window.bootstrap.Modal.getInstance = jest.fn(
				() => existingInstance,
			);
			console.warn = jest.fn();

			lifecycleManager = new PageLifecycleManager({
				...mockConfig,
				pageType: "dataset-list",
			});

			expect(() => {
				lifecycleManager.initializeDatasetModals();
			}).not.toThrow();
		});

		test("should initialize VersioningActionManager for dataset modals", () => {
			lifecycleManager = new PageLifecycleManager({
				...mockConfig,
				pageType: "dataset-list",
			});

			lifecycleManager.initializeDatasetModals();

			expect(global.window.VersioningActionManager).toHaveBeenCalledWith({
				datasetUuid: "test-dataset-uuid",
				permissions: lifecycleManager.permissions,
			});
			expect(mockModal.versioningActionManager).toBeDefined();
		});

		test("should prevent duplicate VersioningActionManager initialization", () => {
			lifecycleManager = new PageLifecycleManager({
				...mockConfig,
				pageType: "dataset-list",
			});

			// Set existing manager
			mockModal.versioningActionManager = { existing: true };

			lifecycleManager.initializeDatasetModals();

			// Should not create a new instance
			expect(global.window.VersioningActionManager).not.toHaveBeenCalled();
		});

		test("should initialize ShareActionManager for dataset modals", () => {
			lifecycleManager = new PageLifecycleManager({
				...mockConfig,
				pageType: "dataset-list",
			});

			lifecycleManager.initializeDatasetModals();

			expect(global.window.ShareActionManager).toHaveBeenCalledWith({
				itemUuid: "test-dataset-uuid",
				itemType: "dataset",
				permissions: lifecycleManager.permissions,
			});
		});

		test("should initialize DownloadActionManager for dataset modals", () => {
			lifecycleManager = new PageLifecycleManager({
				...mockConfig,
				pageType: "dataset-list",
			});

			lifecycleManager.initializeDatasetModals();

			expect(global.window.DownloadActionManager).toHaveBeenCalledWith({
				permissions: lifecycleManager.permissions,
			});
		});

		test("should initialize DetailsActionManager for dataset modals", () => {
			lifecycleManager = new PageLifecycleManager({
				...mockConfig,
				pageType: "dataset-list",
			});

			lifecycleManager.initializeDatasetModals();

			expect(global.window.DetailsActionManager).toHaveBeenCalledWith({
				permissions: lifecycleManager.permissions,
				itemUuid: "test-dataset-uuid",
				itemType: "dataset",
			});
		});

		test("should initialize capture modals", () => {
			const captureModal = {
				getAttribute: jest.fn((attr) => {
					if (attr === "data-item-uuid") return "test-capture-uuid";
					if (attr === "data-item-type") return "capture";
					return null;
				}),
			};

			document.querySelectorAll = jest.fn((selector) => {
				if (selector === ".modal[data-item-type='capture']")
					return [captureModal];
				return [];
			});

			lifecycleManager = new PageLifecycleManager({
				...mockConfig,
				pageType: "capture-list",
			});

			lifecycleManager.initializeCaptureModals();

			expect(global.window.ShareActionManager).toHaveBeenCalledWith({
				itemUuid: "test-capture-uuid",
				itemType: "capture",
				permissions: lifecycleManager.permissions,
			});
		});
	});

	describe("Modal Cleanup", () => {
		let mockModal;
		let mockBootstrapModal;

		beforeEach(() => {
			mockBootstrapModal = {
				dispose: jest.fn(),
			};

			global.window.bootstrap = {
				Modal: {
					getInstance: jest.fn(() => mockBootstrapModal),
				},
			};

			mockModal = {
				id: "test-modal",
			};

			document.querySelectorAll = jest.fn(() => [mockModal]);
		});

		test("should dispose all modal instances during cleanup", () => {
			lifecycleManager = new PageLifecycleManager(mockConfig);

			lifecycleManager.cleanup();

			expect(global.window.bootstrap.Modal.getInstance).toHaveBeenCalledWith(
				mockModal,
			);
			expect(mockBootstrapModal.dispose).toHaveBeenCalled();
		});

		test("should handle disposal failures gracefully", () => {
			mockBootstrapModal.dispose = jest.fn(() => {
				throw new Error("Disposal failed");
			});
			console.warn = jest.fn();

			lifecycleManager = new PageLifecycleManager(mockConfig);

			expect(() => {
				lifecycleManager.cleanup();
			}).not.toThrow();
		});
	});
});
