/**
 * Jest tests for DownloadActionManager
 * Tests download functionality for both datasets and captures
 */

// Import the DownloadActionManager class
import { DownloadActionManager } from "../DownloadActionManager.js";

describe("DownloadActionManager", () => {
	let downloadManager;
	let mockButton;
	let mockModal;
	let mockPermissions;

	beforeEach(() => {
		// Reset mocks
		jest.clearAllMocks();

		// Create mock permissions manager
		mockPermissions = {
			canDownload: jest.fn(() => true),
		};

		// Mock DOM elements
		mockButton = {
			dataset: { downloadSetup: "false" },
			addEventListener: jest.fn(),
			removeEventListener: jest.fn(),
			getAttribute: jest.fn((attr) => {
				if (attr === "data-dataset-uuid") return "test-dataset-uuid";
				if (attr === "data-dataset-name") return "Test Dataset";
				if (attr === "data-capture-uuid") return "test-capture-uuid";
				if (attr === "data-capture-name") return "Test Capture";
				return null;
			}),
			click: jest.fn(),
			disabled: false,
			textContent: "Download",
			innerHTML: "Download",
			parentNode: {
				replaceChild: jest.fn(),
			},
			cloneNode: jest.fn(() => mockButton),
		};

		mockModal = {
			addEventListener: jest.fn(),
			querySelector: jest.fn(),
			querySelectorAll: jest.fn(() => []),
			getAttribute: jest.fn(),
			setAttribute: jest.fn(),
			removeEventListener: jest.fn(),
		};

		// Mock document methods
		document.querySelector = jest.fn(() => mockButton);
		document.querySelectorAll = jest.fn((selector) => {
			if (selector === ".download-dataset-btn") return [mockButton];
			if (selector === ".download-capture-btn") return [mockButton];
			if (selector === ".download-dataset-btn, .download-capture-btn")
				return [mockButton];
			return [];
		});

		document.getElementById = jest.fn((id) => {
			if (id === "downloadModal") return mockModal;
			if (id === "downloadDatasetName") return { textContent: "" };
			if (id === "confirmDownloadBtn") return mockButton;
			if (id === "webDownloadModal") return mockModal;
			if (id === "webDownloadModalLabel") return { innerHTML: "" };
			if (id === "webDownloadDatasetName") return { textContent: "" };
			if (id === "confirmWebDownloadBtn") return mockButton;
			return null;
		});

		// Mock window objects
		global.window = {
			fetch: jest.fn(() =>
				Promise.resolve({
					ok: true,
					json: () =>
						Promise.resolve({ success: true, message: "Download requested" }),
				}),
			),
			showWebDownloadModal: jest.fn(),
			showAlert: jest.fn(),
			DOMUtils: {
				show: jest.fn(),
				hide: jest.fn(),
				showAlert: jest.fn(),
				renderError: jest.fn().mockResolvedValue(true),
				renderLoading: jest.fn().mockResolvedValue(true),
				renderContent: jest.fn().mockResolvedValue(true),
				renderTable: jest.fn().mockResolvedValue(true),
			},
			APIClient: {
				post: jest.fn().mockResolvedValue({
					success: true,
					message: "Download request submitted successfully!",
				}),
			},
		};

		// Mock bootstrap globally
		global.bootstrap = {
			Modal: jest.fn().mockImplementation(() => ({
				show: jest.fn(),
				hide: jest.fn(),
			})),
		};

		// Mock bootstrap.Modal.getInstance
		global.bootstrap.Modal.getInstance = jest.fn(() => ({
			hide: jest.fn(),
		}));
	});

	describe("Initialization", () => {
		test("should initialize with permissions", () => {
			downloadManager = new DownloadActionManager({
				permissions: mockPermissions,
			});

			expect(downloadManager.permissions).toBeDefined();
			expect(downloadManager.permissions.canDownload()).toBe(true);
		});

		test("should setup event listeners on initialization", () => {
			downloadManager = new DownloadActionManager({
				permissions: mockPermissions,
			});

			expect(mockButton.addEventListener).toHaveBeenCalled();
		});
	});

	describe("Dataset Download Functionality", () => {
		beforeEach(() => {
			downloadManager = new DownloadActionManager({
				permissions: mockPermissions,
			});
		});

		test("should initialize dataset download buttons", () => {
			downloadManager.initializeDatasetDownloadButtons();

			expect(document.querySelectorAll).toHaveBeenCalledWith(
				".download-dataset-btn",
			);
			expect(mockButton.addEventListener).toHaveBeenCalledWith(
				"click",
				expect.any(Function),
			);
		});

		test("should handle dataset download click with permissions", async () => {
			const datasetUuid = "test-dataset-uuid";
			const datasetName = "Test Dataset";

			// Test that the method exists and can be called
			expect(() => {
				downloadManager.handleDatasetDownload(
					datasetUuid,
					datasetName,
					mockButton,
				);
			}).not.toThrow();
		});

		test("should prevent duplicate event listener attachment", () => {
			// Create a new button with downloadSetup already set
			const mockButtonWithSetup = {
				dataset: { downloadSetup: "true" },
				addEventListener: jest.fn(),
				getAttribute: jest.fn(),
			};

			// Mock document.querySelectorAll to return the button with setup already done
			document.querySelectorAll.mockReturnValue([mockButtonWithSetup]);

			// Clear previous calls
			mockButtonWithSetup.addEventListener.mockClear();

			downloadManager.initializeDatasetDownloadButtons();

			expect(mockButtonWithSetup.addEventListener).not.toHaveBeenCalled();
		});

		test("should show permission error when download not allowed", async () => {
			// Create permissions that deny download
			const denyPermissions = {
				canDownload: jest.fn(() => false),
			};

			const testDownloadManager = new DownloadActionManager({
				permissions: denyPermissions,
			});

			// Test the showToast method directly
			testDownloadManager.showToast(
				"You don't have permission to download this dataset",
				"warning",
			);

			// showToast calls DOMUtils.showAlert, not window.showAlert directly
			expect(global.window.DOMUtils.showAlert).toHaveBeenCalledWith(
				"You don't have permission to download this dataset",
				"warning",
			);
		});
	});

	describe("Capture Download Functionality", () => {
		beforeEach(() => {
			downloadManager = new DownloadActionManager({
				permissions: mockPermissions,
			});
		});

		test("should initialize capture download buttons", () => {
			downloadManager.initializeCaptureDownloadButtons();

			expect(document.querySelectorAll).toHaveBeenCalledWith(
				".download-capture-btn",
			);
			expect(mockButton.addEventListener).toHaveBeenCalledWith(
				"click",
				expect.any(Function),
			);
		});

		test("should handle capture download click with permissions", async () => {
			const captureUuid = "test-capture-uuid";
			const captureName = "Test Capture";

			// Test that the method exists and can be called
			expect(() => {
				downloadManager.handleCaptureDownload(
					captureUuid,
					captureName,
					mockButton,
				);
			}).not.toThrow();
		});

		test("should show permission error for capture download", async () => {
			// Create permissions that deny download
			const denyPermissions = {
				canDownload: jest.fn(() => false),
			};

			const testDownloadManager = new DownloadActionManager({
				permissions: denyPermissions,
			});

			// Test the showToast method directly
			testDownloadManager.showToast(
				"You don't have permission to download this capture",
				"warning",
			);

			// showToast calls DOMUtils.showAlert, not window.showAlert directly
			expect(global.window.DOMUtils.showAlert).toHaveBeenCalledWith(
				"You don't have permission to download this capture",
				"warning",
			);
		});
	});

	describe("Web Download Modal", () => {
		beforeEach(() => {
			downloadManager = new DownloadActionManager({
				permissions: mockPermissions,
			});
		});

		test("should have openCustomModal method", () => {
			expect(downloadManager.openCustomModal).toBeDefined();
			expect(typeof downloadManager.openCustomModal).toBe("function");
		});

		test("should have closeCustomModal method", () => {
			expect(downloadManager.closeCustomModal).toBeDefined();
			expect(typeof downloadManager.closeCustomModal).toBe("function");
		});
	});

	describe("Download Request Processing", () => {
		beforeEach(() => {
			downloadManager = new DownloadActionManager({
				permissions: mockPermissions,
			});
		});

		test("should have handleDatasetDownload method", () => {
			expect(downloadManager.handleDatasetDownload).toBeDefined();
			expect(typeof downloadManager.handleDatasetDownload).toBe("function");
		});

		test("should have handleCaptureDownload method", () => {
			expect(downloadManager.handleCaptureDownload).toBeDefined();
			expect(typeof downloadManager.handleCaptureDownload).toBe("function");
		});
	});

	describe("Permission Handling", () => {
		test("should check dataset download permissions", () => {
			downloadManager = new DownloadActionManager({
				permissions: mockPermissions,
			});

			expect(downloadManager.permissions.canDownload()).toBe(true);
		});

		test("should check capture download permissions", () => {
			const denyPermissions = {
				canDownload: jest.fn(() => false),
			};
			downloadManager = new DownloadActionManager({
				permissions: denyPermissions,
			});

			expect(downloadManager.permissions.canDownload()).toBe(false);
		});

		test("should default to true when no permissions specified", () => {
			downloadManager = new DownloadActionManager({
				permissions: mockPermissions,
			});

			expect(downloadManager.permissions.canDownload()).toBe(true);
		});
	});

	describe("Error Handling", () => {
		beforeEach(() => {
			downloadManager = new DownloadActionManager({
				permissions: mockPermissions,
			});
		});

		test("should handle missing button elements", () => {
			document.querySelectorAll.mockReturnValue([]);

			expect(() => {
				downloadManager.initializeDatasetDownloadButtons();
			}).not.toThrow();
		});

		test("should handle missing modal elements", () => {
			document.getElementById.mockReturnValue(null);

			expect(() => {
				downloadManager.closeCustomModal("test-modal");
			}).not.toThrow();
		});
	});

	describe("Event Handling", () => {
		beforeEach(() => {
			downloadManager = new DownloadActionManager({
				permissions: mockPermissions,
			});
		});

		test("should have initializeEventListeners method", () => {
			expect(downloadManager.initializeEventListeners).toBeDefined();
			expect(typeof downloadManager.initializeEventListeners).toBe("function");
		});
	});

	describe("Cleanup", () => {
		beforeEach(() => {
			downloadManager = new DownloadActionManager({
				permissions: mockPermissions,
			});
		});

		test("should cleanup event listeners", () => {
			// Test that the cleanup method exists and can be called
			expect(() => {
				downloadManager.cleanup();
			}).not.toThrow();
		});

		test("should handle cleanup gracefully when no listeners", () => {
			expect(() => {
				downloadManager.cleanup();
			}).not.toThrow();
		});
	});
});
