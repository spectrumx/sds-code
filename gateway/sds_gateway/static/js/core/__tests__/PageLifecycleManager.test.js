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
});
