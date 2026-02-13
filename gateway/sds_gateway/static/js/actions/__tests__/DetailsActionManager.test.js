/**
 * Jest tests for DetailsActionManager
 * Tests details functionality for captures and datasets
 */

// Import PermissionLevels to set up window.PermissionLevels
import "../../constants/PermissionLevels.js";
import { PermissionsManager } from "../../core/PermissionsManager.js";
// Import the DetailsActionManager class
import { DetailsActionManager } from "../DetailsActionManager.js";

describe("DetailsActionManager", () => {
	let detailsManager;
	let mockModal;
	let mockButton;
	let mockInput;

	beforeEach(() => {
		// Reset mocks
		jest.clearAllMocks();

		// Create real PermissionsManager instance
		const permissions = new PermissionsManager({
			userPermissionLevel: "owner",
			isOwner: true,
			datasetPermissions: {
				canEditMetadata: true,
				canAddAssets: true,
				canRemoveOwnAssets: true,
				canRemoveAnyAssets: true,
				canShare: true,
				canDownload: true,
			},
		});

		// Mock DOM elements
		mockModal = {
			id: "capture-modal",
			addEventListener: jest.fn(),
			querySelector: jest.fn((selector) => {
				if (selector === ".modal-title") return { textContent: "" };
				if (selector === ".modal-body")
					return {
						innerHTML: "",
						dataset: {},
					};
				return null;
			}),
			querySelectorAll: jest.fn(() => []),
			getAttribute: jest.fn(),
			setAttribute: jest.fn(),
		};

		mockButton = {
			dataset: { detailsSetup: "false" },
			addEventListener: jest.fn(),
			getAttribute: jest.fn((attr) => {
				if (attr === "data-uuid") return "test-uuid";
				if (attr === "data-name") return "Test Capture";
				return null;
			}),
			click: jest.fn(),
			disabled: false,
		};

		mockInput = {
			value: "Test Capture",
			addEventListener: jest.fn(),
			focus: jest.fn(),
			select: jest.fn(),
		};

		// Mock document methods
		document.getElementById = jest.fn((id) => {
			if (
				id === "capture-modal" ||
				id === "test-modal" ||
				id === "captureDetailsModal"
			)
				return mockModal;
			if (id === "capture-name-input") return mockInput;
			return null;
		});

		document.querySelector = jest.fn(() => mockButton);
		document.querySelectorAll = jest.fn((selector) => {
			if (selector === ".capture-details-btn") return [mockButton];
			if (selector === ".dataset-details-btn") return [mockButton];
			return [];
		});
		document.addEventListener = jest.fn();

		// Mock window.bootstrap and global bootstrap
		global.window = {
			bootstrap: {
				Modal: jest.fn(() => ({
					show: jest.fn(),
					hide: jest.fn(),
				})),
			},
		};

		// Also mock global bootstrap for the actual implementation
		global.bootstrap = {
			Modal: jest.fn(() => ({
				show: jest.fn(),
				hide: jest.fn(),
			})),
		};

		// Set up global instances - DOMUtils is now used instead of HTMLInjectionManager
		global.window.DOMUtils = {
			show: jest.fn(),
			hide: jest.fn(),
			showAlert: jest.fn(),
			renderError: jest.fn().mockResolvedValue(true),
			renderLoading: jest.fn().mockResolvedValue(true),
			renderContent: jest.fn().mockResolvedValue(true),
			formatFileSize: jest.fn((size) => (size != null ? `${size} B` : "0 B")),
		};

		// Mock window.APIClient (what the actual code uses)
		global.window.APIClient = {
			get: jest.fn().mockResolvedValue({
				success: true,
				data: {
					name: "Test Capture",
					type: "drf",
					channel: "Channel 1",
				},
			}),
			post: jest.fn().mockResolvedValue({ html: "<div>Test HTML</div>" }),
		};

		// Mock browser APIs
		global.fetch = jest.fn();
		global.fetch.mockResolvedValue({
			ok: true,
			json: () =>
				Promise.resolve({
					success: true,
					data: {
						name: "Test Capture",
						type: "drf",
						channel: "Channel 1",
					},
				}),
		});
	});

	describe("Initialization", () => {
		test("should initialize with permissions", () => {
			const permissions = new PermissionsManager({
				userPermissionLevel: "owner",
				isOwner: true,
				datasetPermissions: { canEditMetadata: true },
			});

			detailsManager = new DetailsActionManager({ permissions });

			expect(detailsManager.permissions).toBeDefined();
			expect(detailsManager.permissions.canEditMetadata()).toBe(true);
		});

		test("should setup event listeners on initialization", () => {
			const permissions = new PermissionsManager({
				userPermissionLevel: "owner",
				isOwner: true,
				datasetPermissions: { canEditMetadata: true },
			});

			detailsManager = new DetailsActionManager({ permissions });

			expect(mockButton.addEventListener).toHaveBeenCalled();
		});
	});

	describe("Capture Details Functionality", () => {
		beforeEach(() => {
			const permissions = new PermissionsManager({
				capturePermissions: { canEditMetadata: true },
			});
			detailsManager = new DetailsActionManager({ permissions });
		});

		test("should initialize capture details buttons", () => {
			detailsManager.initializeCaptureDetailsButtons();

			expect(document.querySelectorAll).toHaveBeenCalledWith(
				".capture-details-btn",
			);
			expect(mockButton.addEventListener).toHaveBeenCalledWith(
				"click",
				expect.any(Function),
			);
		});

		test("should handle capture details click", () => {
			const captureUuid = "test-capture-uuid";

			detailsManager.handleCaptureDetails(captureUuid);

			expect(global.window.APIClient.get).toHaveBeenCalledWith(
				`/users/capture-details/?capture_uuid=${captureUuid}`,
			);
		});

		test("should show modal with capture data", async () => {
			const captureData = {
				name: "Test Capture",
				type: "drf",
				channel: "Channel 1",
			};

			// Mock APIClient response
			global.window.APIClient.get.mockResolvedValueOnce({
				success: true,
				data: captureData,
			});

			await detailsManager.handleCaptureDetails("test-uuid");

			expect(global.bootstrap.Modal).toHaveBeenCalled();
			expect(mockModal.querySelector).toHaveBeenCalled();
		});
	});

	describe("Modal Management", () => {
		beforeEach(() => {
			const permissions = new PermissionsManager({
				capturePermissions: { canEditMetadata: true },
			});
			detailsManager = new DetailsActionManager({ permissions });
		});

		test("should show modal loading state", () => {
			// DOMUtils.renderLoading should be called instead of HTMLInjectionManager
			const renderLoadingSpy = jest.spyOn(
				global.window.DOMUtils,
				"renderLoading",
			);

			// The method exists but requires a modalId parameter
			detailsManager.showModalLoading("test-modal");

			// Verify the appropriate DOMUtils method was called
			expect(renderLoadingSpy).toHaveBeenCalled();

			renderLoadingSpy.mockRestore();
		});
	});

	describe("Permission Handling", () => {
		test("should respect edit permissions", () => {
			// Create a real PermissionsManager instance with limited permissions
			const permissions = new PermissionsManager({
				userPermissionLevel: "viewer",
				isOwner: false,
				datasetPermissions: {
					canEditMetadata: false,
					canAddAssets: false,
					canRemoveOwnAssets: false,
					canRemoveAnyAssets: false,
					canShare: false,
					canDownload: false,
				},
			});
			detailsManager = new DetailsActionManager({ permissions });

			expect(detailsManager.permissions.canEditMetadata()).toBe(false);
		});

		test("should allow view permissions", () => {
			const permissions = new PermissionsManager({
				capturePermissions: { canView: true },
			});
			detailsManager = new DetailsActionManager({ permissions });

			expect(detailsManager.permissions.canView()).toBe(true);
		});
	});

	describe("Error Handling", () => {
		beforeEach(() => {
			const permissions = new PermissionsManager({
				capturePermissions: { canEditMetadata: true },
			});
			detailsManager = new DetailsActionManager({ permissions });
		});

		test("should handle API errors gracefully", async () => {
			// Mock APIClient to reject with an error
			global.window.APIClient.get.mockRejectedValueOnce(new Error("API Error"));

			// The method catches errors and doesn't re-throw them, so it should resolve
			await expect(
				detailsManager.handleCaptureDetails("test-uuid"),
			).resolves.toBeUndefined();
		});

		test("should handle missing modal elements", () => {
			document.getElementById.mockReturnValue(null);

			expect(() => {
				detailsManager.showModalLoading();
			}).not.toThrow();
		});

		test("should handle missing button elements", () => {
			document.querySelectorAll.mockReturnValue([]);

			expect(() => {
				detailsManager.initializeCaptureDetailsButtons();
			}).not.toThrow();
		});
	});

	describe("Dataset Modal Loading", () => {
		let detailsManager;
		let mockDatasetData;
		let mockStatistics;
		let mockTree;
		let mockNameElement;
		let mockDescriptionElement;
		let mockStatusElement;
		let mockAuthorElement;
		let mockKeywordsElement;
		let mockCopyButton;
		let mockTotalFilesElement;
		let mockCapturesElement;
		let mockArtifactsElement;
		let mockTotalSizeElement;
		let mockTreeBody;
		let mockModalBody;
		let mockDatasetModal;
		let appendedChildren;
		let mockCreatedElement;
		let mockUpdatedElement;

		beforeEach(() => {
			mockDatasetData = {
				uuid: "test-uuid",
				name: "Test Dataset",
				description: "A shared dataset",
				status: "Final",
				created_at: "2024-01-01T00:00:00Z",
				updated_at: "2024-01-15T00:00:00Z",
				authors: ["John Doe", "Jane Smith"],
				keywords: ["test", "shared"],
			};

			mockStatistics = {
				total_files: 2,
				captures: 0,
				artifacts: 2,
				total_size: 3072,
			};

			mockTree = {
				type: "directory",
				name: "root",
				files: [
					{
						name: "test-file.txt",
						size: 1024,
						created_at: "2024-01-01T00:00:00Z",
						updated_at: "2024-01-01T00:00:00Z",
						media_type: "text/plain",
						type: "file",
					},
					{
						name: "test-file2.txt",
						size: 2048,
						created_at: "2024-01-01T00:00:00Z",
						updated_at: "2024-01-01T00:00:00Z",
						media_type: "text/plain",
						type: "file",
					},
				],
				children: {},
			};

			global.window.APIClient.get.mockResolvedValueOnce({
				success: true,
				dataset: mockDatasetData,
				statistics: mockStatistics,
				tree: mockTree,
			});

			// Create persistent mock elements (same object returned each time)
			mockNameElement = { textContent: "" };
			mockDescriptionElement = { textContent: "" };
			mockStatusElement = { innerHTML: "" };
			mockCreatedElement = { textContent: "" };
			mockUpdatedElement = { textContent: "" };
			mockAuthorElement = { textContent: "" };
			appendedChildren = [];
			mockKeywordsElement = {
				innerHTML: "",
				appendChild: jest.fn((child) => {
					appendedChildren.push(child);
					return child;
				}),
			};
			mockCopyButton = {
				dataset: {},
				addEventListener: jest.fn(),
				removeEventListener: jest.fn(),
			};
			mockTotalFilesElement = { textContent: "" };
			mockCapturesElement = { textContent: "" };
			mockArtifactsElement = { textContent: "" };
			mockTotalSizeElement = { textContent: "" };
			mockTreeBody = { innerHTML: "" };
			mockModalBody = {
				innerHTML: "",
				dataset: {},
			};

			// Mock modal element with proper querySelector responses
			mockDatasetModal = {
				id: "datasetDetailsModal",
				querySelector: jest.fn((selector) => {
					const selectors = {
						".dataset-details-name": mockNameElement,
						".dataset-details-description": mockDescriptionElement,
						".dataset-details-status": mockStatusElement,
						".dataset-details-created": mockCreatedElement,
						".dataset-details-updated": mockUpdatedElement,
						".dataset-details-author": mockAuthorElement,
						".dataset-details-keywords": mockKeywordsElement,
						".copy-uuid-btn": mockCopyButton,
						"#total-files-count": mockTotalFilesElement,
						"#captures-count": mockCapturesElement,
						"#artifacts-count": mockArtifactsElement,
						"#total-size": mockTotalSizeElement,
						"#dataset-file-tree-table tbody": mockTreeBody,
						".modal-body": mockModalBody,
					};
					return selectors[selector] || null;
				}),
				querySelectorAll: jest.fn(() => []),
			};

			document.getElementById.mockImplementation((id) => {
				if (id === "datasetDetailsModal") return mockDatasetModal;
				return null;
			});
		});

		test.each([
			[
				"owner",
				{
					userPermissionLevel: "owner",
					isOwner: true,
					datasetPermissions: { canView: true, canDownload: true },
				},
			],
			[
				"shared to non-owners",
				{
					userPermissionLevel: "viewer",
					isOwner: false,
					datasetPermissions: { canView: true, canDownload: true },
				},
			],
		])(
			"should show details for %s dataset",
			async (_label, permissionsConfig) => {
				const permissions = new PermissionsManager(permissionsConfig);
				detailsManager = new DetailsActionManager({ permissions });

				// spies to verify the methods are called
				const populateSpy = jest.spyOn(
					detailsManager,
					"populateDatasetDetailsModal",
				);
				const updateFileTreeSpy = jest.spyOn(detailsManager, "updateFileTree");

				await detailsManager.loadDatasetDetailsForModal("test-uuid");

				expect(global.window.APIClient.get).toHaveBeenCalledWith(
					"/users/dataset-details/?dataset_uuid=test-uuid",
				);

				// verify the populateDatasetDetailsModal method is called with the correct arguments
				expect(populateSpy).toHaveBeenCalledWith(
					mockDatasetData,
					mockStatistics,
					mockTree,
				);

				// verify the updateFileTree method is called with the correct arguments
				expect(updateFileTreeSpy).toHaveBeenCalledWith(
					mockDatasetModal,
					mockTree,
				);

				// verify the render-html API call is made to render the file tree
				expect(global.window.APIClient.post).toHaveBeenCalledWith(
					"/users/render-html/",
					expect.objectContaining({
						template: "users/components/modal_file_tree.html",
						context: expect.objectContaining({
							rows: expect.arrayContaining([
								expect.objectContaining({ name: "test-file.txt" }),
								expect.objectContaining({ name: "test-file2.txt" }),
							]),
						}),
					}),
					null,
					true,
				);

				// Verify modal was populated
				expect(mockNameElement.textContent).toBe(mockDatasetData.name);
				expect(mockDescriptionElement.textContent).toBe(
					mockDatasetData.description,
				);
				expect(mockStatusElement.innerHTML).toContain(mockDatasetData.status);
				expect(mockAuthorElement.textContent).toBe(
					mockDatasetData.authors.join(", "),
				);
				expect(mockKeywordsElement.appendChild).toHaveBeenCalledTimes(2);

				// Verify statistics
				expect(mockTotalFilesElement.textContent).toBe(2);
				expect(mockCapturesElement.textContent).toBe(0);
				expect(mockArtifactsElement.textContent).toBe(2);

				// Verify UUID was set on copy button
				expect(mockCopyButton.dataset.uuid).toBe(mockDatasetData.uuid);
			},
		);
	});
});
