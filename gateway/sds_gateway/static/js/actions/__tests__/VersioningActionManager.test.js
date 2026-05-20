/**
 * Jest tests for VersioningActionManager
 * Tests version creation and dataset versioning functionality
 */

// Import the VersioningActionManager class
import { VersioningActionManager } from "../VersioningActionManager.js";
import { flushMicrotasks } from "../../tests-config/testHelpers.js";
const {
	setupVersioningActionTestEnvironment,
	createVersionCreationClickEvent,
} = require("../../__tests__/helpers/actionTestMocks.js");

describe("VersioningActionManager", () => {
	let versioningManager;
	let mockConfig;
	let mockButton;
	let mockPermissions;

	beforeEach(() => {
		({ mockConfig, mockPermissions, mockButton } =
			setupVersioningActionTestEnvironment());
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
			const event = createVersionCreationClickEvent();

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
				createVersionCreationClickEvent(),
				mockButton,
			);

			expect(global.window.APIClient.post).not.toHaveBeenCalled();
		});

		test("should show modal loading state", async () => {
			await versioningManager.handleVersionCreation(
				createVersionCreationClickEvent(),
				mockButton,
			);

			expect(global.window.DOMUtils.showModalLoading).toHaveBeenCalledWith(
				"versioningModal-test-dataset-uuid",
			);
		});

		test("should disable button during processing", async () => {
			await versioningManager.handleVersionCreation(
				createVersionCreationClickEvent(),
				mockButton,
			);

			expect(mockButton.disabled).toBe(true);
			expect(mockButton.dataset.processing).toBe("true");
		});

		test("should make API call to dataset-versioning endpoint", async () => {
			await versioningManager.handleVersionCreation(
				createVersionCreationClickEvent(),
				mockButton,
			);

			expect(global.window.APIClient.post).toHaveBeenCalledWith(
				"/users/dataset-versioning/",
				{
					dataset_uuid: "test-dataset-uuid",
					copy_shared_users: false,
				},
			);
		});

		test("should handle successful version creation", async () => {
			global.window.APIClient.post.mockResolvedValue({
				success: true,
				version: 3,
			});

			await versioningManager.handleVersionCreation(
				createVersionCreationClickEvent(),
				mockButton,
			);

			// Wait for promises to resolve
			await flushMicrotasks();

			expect(global.window.DOMUtils.closeModal).toHaveBeenCalledWith(
				"versioningModal-test-dataset-uuid",
			);
			expect(global.window.DOMUtils.showMessage).toHaveBeenCalledWith(
				"Dataset version updated to v3 successfully",
				expect.objectContaining({
					variant: "success",
					placement: "toast",
					presentation: "toast",
				}),
			);
		});

		test("should refresh list on success", async () => {
			global.window.APIClient.post.mockResolvedValue({
				success: true,
				version: 2,
			});

			await versioningManager.handleVersionCreation(
				createVersionCreationClickEvent(),
				mockButton,
			);

			// Wait for promises to resolve
			await flushMicrotasks();

			expect(global.window.listRefreshManager.loadTable).toHaveBeenCalled();
		});

		test("should fallback to page reload if listRefreshManager not available", async () => {
			global.window.listRefreshManager = undefined;
			const reloadMock = jest.fn();
			Object.defineProperty(global.window, "location", {
				value: { reload: reloadMock },
				writable: true,
				configurable: true,
			});
			global.window.APIClient.post.mockResolvedValue({
				success: true,
				version: 2,
			});
			console.warn = jest.fn();

			await versioningManager.handleVersionCreation(
				createVersionCreationClickEvent(),
				mockButton,
			);

			// Wait for promises to resolve
			await flushMicrotasks();

			expect(console.warn).toHaveBeenCalledWith(
				"listRefreshManager not available, reloading page",
			);
			expect(reloadMock).toHaveBeenCalled();
		});

		test("should handle API error response", async () => {
			global.window.APIClient.post.mockResolvedValue({
				success: false,
				error: "Version creation failed",
			});

			await versioningManager.handleVersionCreation(
				createVersionCreationClickEvent(),
				mockButton,
			);

			// Wait for promises to resolve
			await flushMicrotasks();

			expect(global.window.DOMUtils.showMessage).toHaveBeenCalledWith(
				"Version creation failed",
				expect.objectContaining({
					variant: "danger",
					placement: "toast",
					presentation: "toast",
				}),
			);
			expect(global.window.DOMUtils.closeModal).not.toHaveBeenCalled();
		});

		test("should handle API exception", async () => {
			global.window.APIClient.post.mockRejectedValue(
				new Error("Network error"),
			);

			await versioningManager.handleVersionCreation(
				createVersionCreationClickEvent(),
				mockButton,
			);

			// Wait for promises to resolve
			await flushMicrotasks();

			expect(global.window.DOMUtils.showMessage).toHaveBeenCalledWith(
				"Network error",
				expect.objectContaining({
					variant: "danger",
					placement: "toast",
					presentation: "toast",
				}),
			);
		});

		test("should re-enable button after processing", async () => {
			await versioningManager.handleVersionCreation(
				createVersionCreationClickEvent(),
				mockButton,
			);

			// Wait for promises to resolve
			await flushMicrotasks();

			expect(mockButton.disabled).toBe(false);
			expect(mockButton.dataset.processing).toBe("false");
		});

		test("should re-enable button even on error", async () => {
			global.window.APIClient.post.mockRejectedValue(
				new Error("Network error"),
			);

			await versioningManager.handleVersionCreation(
				createVersionCreationClickEvent(),
				mockButton,
			);

			// Wait for promises to resolve
			await flushMicrotasks();

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
				createVersionCreationClickEvent(),
				mockButton,
			);

			// Wait for promises to resolve
			await flushMicrotasks();

			expect(global.window.DOMUtils.showMessage).toHaveBeenCalledWith(
				expect.stringMatching(/Failed to create dataset version|Network error/),
				expect.objectContaining({
					variant: "danger",
					placement: "toast",
					presentation: "toast",
				}),
			);
		});

		test("should handle success response without version number", async () => {
			global.window.listRefreshManager = { loadTable: jest.fn() };
			global.window.APIClient.post.mockResolvedValue({
				success: true,
			});
			document.getElementById = jest.fn(() => null);

			await versioningManager.handleVersionCreation(
				createVersionCreationClickEvent(),
				mockButton,
			);

			// Wait for promises to resolve
			await flushMicrotasks();

			expect(global.window.DOMUtils.showMessage).toHaveBeenCalledWith(
				expect.stringContaining("successfully"),
				expect.objectContaining({
					variant: "success",
					placement: "toast",
					presentation: "toast",
				}),
			);
		});
	});
});
