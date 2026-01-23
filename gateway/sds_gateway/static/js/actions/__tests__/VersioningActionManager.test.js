/**
 * Jest tests for VersioningActionManager
 * Tests version creation and dataset versioning functionality
 */

// Import the VersioningActionManager class
import { VersioningActionManager } from "../VersioningActionManager.js";

describe("VersioningActionManager", () => {
	let versioningManager;
	let mockConfig;
	let mockButton;
	let mockPermissions;

	beforeEach(() => {
		// Reset mocks
		jest.clearAllMocks();

		// Create mock permissions
		mockPermissions = {
			canEditMetadata: jest.fn(() => true),
			canShare: jest.fn(() => true),
		};

		// Mock config
		mockConfig = {
			datasetUuid: "test-dataset-uuid",
			permissions: mockPermissions,
		};

		// Mock button element
		mockButton = {
			id: "createVersionBtn-test-dataset-uuid",
			dataset: { versionSetup: "false", processing: "false" },
			addEventListener: jest.fn(),
			disabled: false,
			click: jest.fn(),
		};

		// Mock document methods
		document.getElementById = jest.fn((id) => {
			if (id === `createVersionBtn-${mockConfig.datasetUuid}`)
				return mockButton;
			return null;
		});

		// Mock DOMUtils
		global.window.DOMUtils = {
			showModalLoading: jest.fn().mockResolvedValue(true),
			closeModal: jest.fn(),
			showAlert: jest.fn(),
		};

		// Mock APIClient
		global.window.APIClient = {
			post: jest.fn().mockResolvedValue({
				success: true,
				version: 2,
			}),
		};

		// Mock listRefreshManager
		global.window.listRefreshManager = {
			loadTable: jest.fn().mockResolvedValue(true),
		};

		// Mock window.location
		global.window.location = {
			reload: jest.fn(),
		};
	});

	describe("Initialization", () => {
		test("should initialize with correct configuration", () => {
			versioningManager = new VersioningActionManager(mockConfig);

			expect(versioningManager.permissions).toBe(mockPermissions);
			expect(versioningManager.datasetUuid).toBe("test-dataset-uuid");
			expect(versioningManager.modalId).toBe(
				"versioningModal-test-dataset-uuid",
			);
		});

		test("should setup event listeners on initialization", () => {
			versioningManager = new VersioningActionManager(mockConfig);

			expect(mockButton.addEventListener).toHaveBeenCalledWith(
				"click",
				expect.any(Function),
			);
		});

		test("should prevent duplicate event listener attachment", () => {
			mockButton.dataset.versionSetup = "true";
			mockButton.addEventListener.mockClear();

			versioningManager = new VersioningActionManager(mockConfig);

			expect(mockButton.addEventListener).not.toHaveBeenCalled();
		});

		test("should handle missing button gracefully", () => {
			document.getElementById = jest.fn(() => null);

			expect(() => {
				versioningManager = new VersioningActionManager(mockConfig);
			}).not.toThrow();
		});
	});

	describe("Version Creation", () => {
		beforeEach(() => {
			versioningManager = new VersioningActionManager(mockConfig);
		});

		test("should handle version creation click", () => {
			const event = {
				preventDefault: jest.fn(),
				stopPropagation: jest.fn(),
			};

			// Get the click handler from addEventListener
			const clickHandler = mockButton.addEventListener.mock.calls.find(
				(call) => call[0] === "click",
			)?.[1];

			if (clickHandler) {
				clickHandler(event);
			}

			expect(event.preventDefault).toHaveBeenCalled();
			expect(event.stopPropagation).toHaveBeenCalled();
		});

		test("should prevent double-submission", () => {
			mockButton.dataset.processing = "true";

			versioningManager.handleVersionCreation(
				{ preventDefault: jest.fn(), stopPropagation: jest.fn() },
				mockButton,
			);

			expect(global.window.APIClient.post).not.toHaveBeenCalled();
		});

		test("should show modal loading state", async () => {
			await versioningManager.handleVersionCreation(
				{ preventDefault: jest.fn(), stopPropagation: jest.fn() },
				mockButton,
			);

			expect(global.window.DOMUtils.showModalLoading).toHaveBeenCalledWith(
				"versioningModal-test-dataset-uuid",
			);
		});

		test("should disable button during processing", async () => {
			await versioningManager.handleVersionCreation(
				{ preventDefault: jest.fn(), stopPropagation: jest.fn() },
				mockButton,
			);

			expect(mockButton.disabled).toBe(true);
			expect(mockButton.dataset.processing).toBe("true");
		});

		test("should make API call to dataset-versioning endpoint", async () => {
			await versioningManager.handleVersionCreation(
				{ preventDefault: jest.fn(), stopPropagation: jest.fn() },
				mockButton,
			);

			expect(global.window.APIClient.post).toHaveBeenCalledWith(
				"/users/dataset-versioning/",
				{
					dataset_uuid: "test-dataset-uuid",
				},
			);
		});

		test("should handle successful version creation", async () => {
			global.window.APIClient.post.mockResolvedValue({
				success: true,
				version: 3,
			});

			await versioningManager.handleVersionCreation(
				{ preventDefault: jest.fn(), stopPropagation: jest.fn() },
				mockButton,
			);

			// Wait for promises to resolve
			await new Promise((resolve) => setTimeout(resolve, 0));

			expect(global.window.DOMUtils.closeModal).toHaveBeenCalledWith(
				"versioningModal-test-dataset-uuid",
			);
			expect(global.window.DOMUtils.showAlert).toHaveBeenCalledWith(
				"Dataset version updated to v3 successfully",
				"success",
			);
		});

		test("should refresh list on success", async () => {
			global.window.APIClient.post.mockResolvedValue({
				success: true,
				version: 2,
			});

			await versioningManager.handleVersionCreation(
				{ preventDefault: jest.fn(), stopPropagation: jest.fn() },
				mockButton,
			);

			// Wait for promises to resolve
			await new Promise((resolve) => setTimeout(resolve, 0));

			expect(global.window.listRefreshManager.loadTable).toHaveBeenCalled();
		});

		test("should fallback to page reload if listRefreshManager not available", async () => {
			global.window.listRefreshManager = undefined;
			global.window.APIClient.post.mockResolvedValue({
				success: true,
				version: 2,
			});
			console.warn = jest.fn();

			await versioningManager.handleVersionCreation(
				{ preventDefault: jest.fn(), stopPropagation: jest.fn() },
				mockButton,
			);

			// Wait for promises to resolve
			await new Promise((resolve) => setTimeout(resolve, 0));

			expect(console.warn).toHaveBeenCalledWith(
				"listRefreshManager not available, reloading page",
			);
			expect(global.window.location.reload).toHaveBeenCalled();
		});

		test("should handle API error response", async () => {
			global.window.APIClient.post.mockResolvedValue({
				success: false,
				error: "Version creation failed",
			});

			await versioningManager.handleVersionCreation(
				{ preventDefault: jest.fn(), stopPropagation: jest.fn() },
				mockButton,
			);

			// Wait for promises to resolve
			await new Promise((resolve) => setTimeout(resolve, 0));

			expect(global.window.DOMUtils.showAlert).toHaveBeenCalledWith(
				"Version creation failed",
				"error",
			);
			expect(global.window.DOMUtils.closeModal).not.toHaveBeenCalled();
		});

		test("should handle API exception", async () => {
			global.window.APIClient.post.mockRejectedValue(
				new Error("Network error"),
			);

			await versioningManager.handleVersionCreation(
				{ preventDefault: jest.fn(), stopPropagation: jest.fn() },
				mockButton,
			);

			// Wait for promises to resolve
			await new Promise((resolve) => setTimeout(resolve, 0));

			expect(global.window.DOMUtils.showAlert).toHaveBeenCalledWith(
				"Network error",
				"error",
			);
		});

		test("should re-enable button after processing", async () => {
			await versioningManager.handleVersionCreation(
				{ preventDefault: jest.fn(), stopPropagation: jest.fn() },
				mockButton,
			);

			// Wait for promises to resolve
			await new Promise((resolve) => setTimeout(resolve, 0));

			expect(mockButton.disabled).toBe(false);
			expect(mockButton.dataset.processing).toBe("false");
		});

		test("should re-enable button even on error", async () => {
			global.window.APIClient.post.mockRejectedValue(
				new Error("Network error"),
			);

			await versioningManager.handleVersionCreation(
				{ preventDefault: jest.fn(), stopPropagation: jest.fn() },
				mockButton,
			);

			// Wait for promises to resolve
			await new Promise((resolve) => setTimeout(resolve, 0));

			expect(mockButton.disabled).toBe(false);
			expect(mockButton.dataset.processing).toBe("false");
		});
	});

	describe("Error Handling", () => {
		beforeEach(() => {
			versioningManager = new VersioningActionManager(mockConfig);
		});

		test("should handle missing button element", () => {
			document.getElementById = jest.fn(() => null);

			expect(() => {
				versioningManager.initializeVersionCreationButton();
			}).not.toThrow();
		});

		test("should handle API errors with default message", async () => {
			global.window.APIClient.post.mockRejectedValue(
				new Error("Network error"),
			);

			await versioningManager.handleVersionCreation(
				{ preventDefault: jest.fn(), stopPropagation: jest.fn() },
				mockButton,
			);

			// Wait for promises to resolve
			await new Promise((resolve) => setTimeout(resolve, 0));

			expect(global.window.DOMUtils.showAlert).toHaveBeenCalledWith(
				expect.stringContaining("Failed to create dataset version"),
				"error",
			);
		});

		test("should handle success response without version number", async () => {
			global.window.APIClient.post.mockResolvedValue({
				success: true,
			});

			await versioningManager.handleVersionCreation(
				{ preventDefault: jest.fn(), stopPropagation: jest.fn() },
				mockButton,
			);

			// Wait for promises to resolve
			await new Promise((resolve) => setTimeout(resolve, 0));

			expect(global.window.DOMUtils.showAlert).toHaveBeenCalledWith(
				expect.stringContaining("successfully"),
				"success",
			);
		});
	});
});
