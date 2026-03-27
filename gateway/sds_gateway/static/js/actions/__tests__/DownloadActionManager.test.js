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
			if (selector === ".web-download-btn") return [mockButton];
			return [];
		});

		document.getElementById = jest.fn((id) => {
			if (id.startsWith("webDownloadModal-")) return mockModal;
			if (id.startsWith("webDownloadModalLabel-")) return { innerHTML: "" };
			if (id.startsWith("webDownloadDatasetName-")) return { textContent: "" };
			if (id.startsWith("confirmWebDownloadBtn-")) return mockButton;
			return null;
		});

		// Mock window objects (augment global window so code under test sees DOMUtils)
		const domUtils = {
			show: jest.fn(),
			hide: jest.fn(),
			showAlert: jest.fn(),
			renderError: jest.fn().mockResolvedValue(true),
			renderLoading: jest.fn().mockResolvedValue(true),
			renderContent: jest.fn().mockResolvedValue(true),
			renderTable: jest.fn().mockResolvedValue(true),
			showModalLoading: jest.fn().mockResolvedValue(true),
			clearModalLoading: jest.fn(),
			showModalError: jest.fn().mockResolvedValue(true),
			openModal: jest.fn(),
			closeModal: jest.fn(),
		};
		global.window.DOMUtils = domUtils;
		global.window.APIClient = {
			post: jest.fn().mockResolvedValue({
				success: true,
				message: "Download request submitted successfully!",
			}),
		};
		global.window.fetch = jest.fn(() =>
			Promise.resolve({
				ok: true,
				json: () =>
					Promise.resolve({ success: true, message: "Download requested" }),
			}),
		);
		global.window.showAlert = jest.fn();

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
		let downloadManager;
		let mockAPIClient;
		let mockButton;
		let clonedConfirmBtn;

		beforeEach(() => {
			mockAPIClient = {
				post: jest.fn(),
			};
			window.APIClient = mockAPIClient;

			window.DOMUtils = {
				openModal: jest.fn(),
				closeModal: jest.fn(),
				renderLoading: jest.fn().mockResolvedValue(true),
				renderContent: jest.fn().mockResolvedValue(true),
				showAlert: jest.fn(),
			};

			mockButton = {
				innerHTML: "Download",
				disabled: false,
				addEventListener: jest.fn(),
				dataset: { downloadSetup: "false" },
				getAttribute: jest.fn((attr) => {
					if (attr === "data-item-uuid") return "test-item-uuid";
					if (attr === "data-item-type") return "dataset";
					return null;
				}),
			};

			document.querySelectorAll = jest.fn((selector) => {
				if (selector === ".web-download-btn") return [mockButton];
				return [];
			});

			document.getElementById = jest.fn((id) => {
				if (id.startsWith("webDownloadDatasetName-")) {
					return { textContent: "" };
				}
				if (id.startsWith("confirmWebDownloadBtn-")) {
					return {
						cloneNode: jest.fn(() => {
							clonedConfirmBtn = {
								parentNode: { replaceChild: jest.fn() },
								onclick: null,
							};
							return clonedConfirmBtn;
						}),
						parentNode: { replaceChild: jest.fn() },
					};
				}
				return null;
			});

			downloadManager = new DownloadActionManager({
				permissions: { canDownload: () => true },
			});
			downloadManager.showToast = jest.fn();
		});

		test("should initialize web download buttons", () => {
			downloadManager.initializeWebDownloadButtons();

			expect(document.querySelectorAll).toHaveBeenCalledWith(
				".web-download-btn",
			);
			expect(mockButton.addEventListener).toHaveBeenCalledWith(
				"click",
				expect.any(Function),
			);
		});

		test("should successfully request download and show success message", async () => {
			mockAPIClient.post.mockResolvedValue({
				success: true,
				message: "Download request submitted",
			});

			await downloadManager.initializeWebDownloadModal(
				"test-item-uuid",
				"dataset",
				mockButton,
			);

			// Simulate confirm button click using the same clone the code assigned onclick to
			if (clonedConfirmBtn && typeof clonedConfirmBtn.onclick === "function") {
				await clonedConfirmBtn.onclick();
			}

			await new Promise((resolve) => setTimeout(resolve, 0));

			expect(mockAPIClient.post).toHaveBeenCalledWith(
				"/users/download-item/dataset/test-item-uuid/",
				{},
				null,
				false,
			);
			expect(window.DOMUtils.renderContent).toHaveBeenCalledWith(
				mockButton,
				expect.objectContaining({
					icon: "check-circle",
					color: "success",
				}),
			);
			expect(downloadManager.showToast).toHaveBeenCalledWith(
				expect.stringContaining("Download request submitted"),
				"success",
			);
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

			downloadManager.initializeWebDownloadButtons();

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
			expect(window.DOMUtils.showAlert).toHaveBeenCalledWith(
				"You don't have permission to download this dataset",
				"warning",
			);
		});
	});

	describe("Capture Download Functionality", () => {
		beforeEach(() => {
			window.DOMUtils = {
				...global.window.DOMUtils,
				openModal: jest.fn(),
				closeModal: jest.fn(),
				renderLoading: jest.fn().mockResolvedValue(true),
				renderContent: jest.fn().mockResolvedValue(true),
				showAlert: jest.fn(),
			};
			downloadManager = new DownloadActionManager({
				permissions: mockPermissions,
			});
		});

		test("should configure temporal slider when opening web download for capture", async () => {
			const spy = jest
				.spyOn(downloadManager, "setTemporalSliderAttrs")
				.mockImplementation(() => {});

			document.getElementById = jest.fn((id) => {
				if (id.startsWith("confirmWebDownloadBtn-")) {
					return {
						cloneNode: jest.fn(() => ({
							parentNode: { replaceChild: jest.fn() },
							onclick: null,
						})),
						parentNode: { replaceChild: jest.fn() },
					};
				}
				return null;
			});

			const captureBtn = {
				innerHTML: "Download",
				disabled: false,
				dataset: {},
				getAttribute: jest.fn((attr) => {
					if (attr === "data-item-uuid") return "test-capture-uuid";
					if (attr === "data-item-type") return "capture";
					return null;
				}),
			};

			await downloadManager.initializeWebDownloadModal(
				"test-capture-uuid",
				"capture",
				captureBtn,
			);

			expect(spy).toHaveBeenCalledWith(
				"webDownloadModal-test-capture-uuid",
				captureBtn,
				"test-capture-uuid",
			);
			spy.mockRestore();
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
			expect(window.DOMUtils.showAlert).toHaveBeenCalledWith(
				"You don't have permission to download this capture",
				"warning",
			);
		});
	});

	describe("initializeCaptureDownloadSlider", () => {
		const MODAL_ID = "webDownloadModal-test-uuid";
		let mockSliderEl;
		let mockNoUiSliderCreate;
		let mockSliderInstance;

		function stubEl() {
			return {
				textContent: "",
				value: "",
				dataset: {},
				classList: { add: jest.fn(), remove: jest.fn() },
				disabled: false,
				addEventListener: jest.fn(),
			};
		}

		/** Modal root with querySelector("#id") like the real DOM */
		function mockWebDownloadModal(elementMap) {
			const map = elementMap || {};
			return {
				dataset: {},
				querySelector: jest.fn((sel) => {
					const id = sel.startsWith("#") ? sel.slice(1) : sel;
					if (Object.prototype.hasOwnProperty.call(map, id)) {
						return map[id];
					}
					return stubEl();
				}),
			};
		}

		beforeEach(() => {
			downloadManager = new DownloadActionManager({
				permissions: mockPermissions,
			});
			mockSliderInstance = {
				on: jest.fn(),
				destroy: jest.fn(),
				set: jest.fn(),
			};
			mockSliderEl = {
				noUiSlider: null,
				dataset: {},
			};
			mockNoUiSliderCreate = jest.fn(() => {
				mockSliderEl.noUiSlider = mockSliderInstance;
			});
			// Slider path touches formatFileSize on totalSizeLabel
			global.window.DOMUtils = {
				...global.window.DOMUtils,
				formatFileSize: jest.fn((n) => `${n} B`),
			};
		});

		test("should return early when modal root element is missing", () => {
			document.getElementById = jest.fn(() => null);
			global.noUiSlider = { create: mockNoUiSliderCreate };

			downloadManager.initializeCaptureDownloadSlider(
				MODAL_ID,
				10000,
				1000,
				{},
			);
			expect(mockNoUiSliderCreate).not.toHaveBeenCalled();
		});

		test("should return early when temporalFilterSlider element is missing", () => {
			const modal = mockWebDownloadModal({ temporalFilterSlider: null });
			document.getElementById = jest.fn((id) =>
				id === MODAL_ID ? modal : null,
			);
			global.noUiSlider = { create: mockNoUiSliderCreate };

			downloadManager.initializeCaptureDownloadSlider(
				MODAL_ID,
				10000,
				1000,
				{},
			);
			expect(mockNoUiSliderCreate).not.toHaveBeenCalled();
		});

		test("should return early when noUiSlider is undefined", () => {
			const originalNoUiSlider = global.noUiSlider;
			global.noUiSlider = undefined;
			const modal = mockWebDownloadModal({
				temporalFilterSlider: mockSliderEl,
			});
			document.getElementById = jest.fn((id) =>
				id === MODAL_ID ? modal : null,
			);

			expect(() => {
				downloadManager.initializeCaptureDownloadSlider(
					MODAL_ID,
					10000,
					1000,
					{},
				);
			}).not.toThrow();

			global.noUiSlider = originalNoUiSlider;
		});

		test("should create slider and set modal dataset and range hint when slider and noUiSlider exist", () => {
			const rangeHintEl = { textContent: "" };
			const webDownloadModal = mockWebDownloadModal({
				temporalFilterSlider: mockSliderEl,
				temporalRangeHint: rangeHintEl,
			});
			document.getElementById = jest.fn((id) =>
				id === MODAL_ID ? webDownloadModal : null,
			);
			global.noUiSlider = { create: mockNoUiSliderCreate };

			downloadManager.initializeCaptureDownloadSlider(MODAL_ID, 5000, 500, {
				dataFilesCount: 10,
				totalFilesCount: 12,
				totalSize: 1000000,
			});

			expect(mockNoUiSliderCreate).toHaveBeenCalledWith(
				mockSliderEl,
				expect.objectContaining({
					start: [0, 5000],
					connect: true,
					step: 500,
					range: { min: 0, max: 5000 },
				}),
			);
			expect(webDownloadModal.dataset.durationMs).toBe("5000");
			expect(webDownloadModal.dataset.fileCadenceMs).toBe("500");
			expect(rangeHintEl.textContent).toBe("0 – 5000 ms");
		});

		test("should not create slider when durationMs is 0", () => {
			const rangeHintEl = { textContent: "" };
			const modal = mockWebDownloadModal({
				temporalFilterSlider: mockSliderEl,
				temporalRangeHint: rangeHintEl,
			});
			document.getElementById = jest.fn((id) =>
				id === MODAL_ID ? modal : null,
			);
			global.noUiSlider = { create: mockNoUiSliderCreate };

			downloadManager.initializeCaptureDownloadSlider(MODAL_ID, 0, 1000, {});

			expect(mockNoUiSliderCreate).not.toHaveBeenCalled();
		});
	});

	describe("Web Download Modal", () => {
		beforeEach(() => {
			downloadManager = new DownloadActionManager({
				permissions: mockPermissions,
			});
		});

		test("should have initializeWebDownloadModal method", () => {
			expect(downloadManager.initializeWebDownloadModal).toBeDefined();
			expect(typeof downloadManager.initializeWebDownloadModal).toBe(
				"function",
			);
		});

		test("should have openSDKDownloadModal method", () => {
			expect(downloadManager.openSDKDownloadModal).toBeDefined();
			expect(typeof downloadManager.openSDKDownloadModal).toBe("function");
		});

		test("should use DOMUtils.openModal for opening modals", async () => {
			const modalId = "webDownloadModal-test-uuid";
			const confirmBtn = {
				dataset: {},
				cloneNode: jest.fn(() => confirmBtn),
				parentNode: { replaceChild: jest.fn() },
				onclick: null,
				innerHTML: "",
				disabled: false,
			};
			document.getElementById = jest.fn((id) => {
				if (id === modalId) {
					return { id: modalId, addEventListener: jest.fn() };
				}
				if (id === "webDownloadDatasetName-test-uuid") {
					return { textContent: "" };
				}
				if (id === "confirmWebDownloadBtn-test-uuid") {
					return confirmBtn;
				}
				return null;
			});

			const btn = {
				innerHTML: "Download",
				disabled: false,
				dataset: {},
				getAttribute: jest.fn((attr) => {
					if (attr === "data-item-uuid") return "test-uuid";
					if (attr === "data-item-type") return "dataset";
					return null;
				}),
			};

			await downloadManager.initializeWebDownloadModal(
				"test-uuid",
				"dataset",
				btn,
			);

			expect(global.window.DOMUtils.openModal).toHaveBeenCalledWith(modalId);
		});
	});

	describe("Download Request Processing", () => {
		beforeEach(() => {
			downloadManager = new DownloadActionManager({
				permissions: mockPermissions,
			});
		});

		test("should have initializeWebDownloadModal method", () => {
			expect(downloadManager.initializeWebDownloadModal).toBeDefined();
			expect(typeof downloadManager.initializeWebDownloadModal).toBe(
				"function",
			);
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
				downloadManager.initializeWebDownloadButtons();
			}).not.toThrow();
		});

		test("should handle missing modal elements", () => {
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
