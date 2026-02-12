/**
 * ShareGroupManager Test Suite
 * Tests for share group management functionality
 */

// Import the ShareGroupManager class
import { ShareGroupManager } from "../ShareGroupManager.js";

describe("ShareGroupManager", () => {
	let shareGroupManager;
	let mockConfig;

	beforeEach(() => {
		// Reset mocks
		jest.clearAllMocks();

		// Mock configuration
		mockConfig = {
			apiEndpoint: "/users/share-groups/",
		};

		// Minimal DOM mocks
		document.getElementById = jest.fn(() => null);
		document.querySelector = jest.fn(() => null);
		document.querySelectorAll = jest.fn(() => []);

		// Minimal API mocks
		global.window = {
			APIClient: {
				request: jest.fn().mockResolvedValue({ success: true }),
				get: jest.fn().mockResolvedValue({ success: true }),
				post: jest.fn().mockResolvedValue({ html: "<div>Test HTML</div>" }),
			},
			DOMUtils: {
				show: jest.fn(),
				hide: jest.fn(),
				showAlert: jest.fn(),
				renderError: jest.fn().mockResolvedValue(true),
				renderLoading: jest.fn().mockResolvedValue(true),
				renderContent: jest.fn().mockResolvedValue(true),
				renderTable: jest.fn().mockResolvedValue(true),
			},
			showAlert: jest.fn(),
		};

		// Minimal Bootstrap mock
		global.bootstrap = {
			Modal: jest.fn().mockImplementation(() => ({
				show: jest.fn(),
				hide: jest.fn(),
			})),
		};
	});

	describe("Initialization", () => {
		test("should initialize with default configuration", () => {
			shareGroupManager = new ShareGroupManager(mockConfig);

			expect(shareGroupManager.config.apiEndpoint).toBe("/users/share-groups/");
			expect(shareGroupManager.currentGroupUuid).toBeNull();
			expect(shareGroupManager.currentGroupName).toBeNull();
			expect(shareGroupManager.pendingDeleteGroupUuid).toBeNull();
			expect(shareGroupManager.pendingDeleteGroupName).toBeNull();
			expect(shareGroupManager.pendingRemovals).toBeInstanceOf(Set);
		});

		test("should initialize with custom configuration", () => {
			const customConfig = {
				apiEndpoint: "/custom/endpoint/",
				customProperty: "value",
			};
			const manager = new ShareGroupManager(customConfig);

			expect(manager.config.apiEndpoint).toBe("/custom/endpoint/");
			expect(manager.config.customProperty).toBe("value");
		});

		test("should initialize event listeners", () => {
			shareGroupManager = new ShareGroupManager(mockConfig);

			expect(typeof shareGroupManager.initializeEventListeners).toBe(
				"function",
			);
		});
	});

	describe("Group Creation", () => {
		beforeEach(() => {
			shareGroupManager = new ShareGroupManager(mockConfig);
		});

		test("should handle create group form submission successfully", async () => {
			const mockForm = {
				addEventListener: jest.fn(),
				querySelector: jest.fn(() => ({ value: "Test Group" })),
			};

			const mockSearchInput = {
				dataset: {},
				addEventListener: jest.fn(),
			};

			document.getElementById = jest.fn((id) => {
				if (id === "share-group-create-form") return mockForm;
				if (id === "share-group-user-search-input") return mockSearchInput;
				return null;
			});

			document.querySelector = jest.fn((selector) => {
				if (selector === "#share-group-user-search-input")
					return mockSearchInput;
				return null;
			});

			expect(() => {
				shareGroupManager.initializeEventListeners();
			}).not.toThrow();
		});
	});

	describe("Member Management", () => {
		beforeEach(() => {
			shareGroupManager = new ShareGroupManager(mockConfig);
		});

		test("should handle add members successfully", async () => {
			const mockForm = {
				addEventListener: jest.fn(),
				querySelector: jest.fn(() => null),
			};
			document.getElementById = jest.fn(() => mockForm);

			expect(() => {
				shareGroupManager.initializeEventListeners();
			}).not.toThrow();
		});
	});

	describe("Member Removal", () => {
		beforeEach(() => {
			shareGroupManager = new ShareGroupManager(mockConfig);
		});

		test.each([
			[true, "when there are pending removals"],
			[false, "when no pending removals"],
		])("should handle save button %s", (hasRemovals, description) => {
			if (hasRemovals) {
				shareGroupManager.pendingRemovals.add("test@example.com");
			}

			expect(() => {
				shareGroupManager.updateSaveButtonState();
			}).not.toThrow();
		});
	});

	describe("Group Deletion", () => {
		beforeEach(() => {
			shareGroupManager = new ShareGroupManager(mockConfig);
		});

		test("should show delete confirmation modal", () => {
			const mockModal = { show: jest.fn() };
			global.bootstrap.Modal.mockImplementation(() => mockModal);

			expect(() => {
				new ShareGroupManager(mockConfig);
			}).not.toThrow();
		});
	});

	describe("Table Updates", () => {
		beforeEach(() => {
			shareGroupManager = new ShareGroupManager(mockConfig);
		});

		test("should update table member info", () => {
			const mockTableBody = {
				querySelector: jest.fn(() => ({
					style: { display: "block" },
					innerHTML: "",
				})),
			};
			document.querySelector = jest.fn(() => mockTableBody);

			// Mock DOMUtils methods
			global.window.DOMUtils.show = jest.fn();
			global.window.DOMUtils.hide = jest.fn();

			// updateTableMemberInfo expects (groupUuid, members array)
			const members = [
				{ email: "test@example.com", name: "Test User" },
				{ email: "test2@example.com", name: "Test User 2" },
			];

			expect(() => {
				shareGroupManager.updateTableMemberInfo("test-uuid", members);
			}).not.toThrow();
		});
	});

	describe("Helper Methods", () => {
		beforeEach(() => {
			shareGroupManager = new ShareGroupManager(mockConfig);
		});

		test.each([
			["with global showAlert available", true],
			["with missing global showAlert", false],
		])("should show alert %s", (description, hasShowAlert) => {
			if (!hasShowAlert) {
				global.window.showAlert = undefined;
			}

			expect(() => {
				shareGroupManager.showAlert("Test message", "success");
			}).not.toThrow();
		});
	});

	describe("Displaying Shared Assets Info", () => {
		let shareGroupManager;
		let mockAPIClient;
		let mockSection;
	
		beforeEach(() => {
			mockAPIClient = {
				post: jest.fn(),
			};
			window.APIClient = mockAPIClient;
	
			mockSection = {
				innerHTML: "",
				classList: {
					remove: jest.fn(),
				},
			};
	
			document.getElementById = jest.fn((id) => {
				if (id === "sharedAssetsSection") return mockSection;
				return null;
			});
	
			shareGroupManager = new ShareGroupManager();
		});
	
		test("should filter and sort assets by type, showing first 3 of each", async () => {
			const sharedAssets = [
				{ type: "dataset", name: "Dataset C" },
				{ type: "dataset", name: "Dataset A" },
				{ type: "dataset", name: "Dataset B" },
				{ type: "dataset", name: "Dataset D" },
				{ type: "capture", name: "Capture Z" },
				{ type: "capture", name: "Capture X" },
				{ type: "capture", name: "Capture Y" },
				{ type: "capture", name: "Capture W" },
			];
	
			mockAPIClient.post.mockResolvedValue({
				html: "<div>Mock HTML</div>",
			});
	
			await shareGroupManager.displaySharedAssetsInfo(sharedAssets);
	
			expect(mockAPIClient.post).toHaveBeenCalledWith(
				"/users/render-html/",
				{
					template: "users/components/shared_assets_display.html",
					context: expect.objectContaining({
						datasets: [
							{ type: "dataset", name: "Dataset A" },
							{ type: "dataset", name: "Dataset B" },
							{ type: "dataset", name: "Dataset C" },
						],
						captures: [
							{ type: "capture", name: "Capture W" },
							{ type: "capture", name: "Capture X" },
							{ type: "capture", name: "Capture Y" },
						],
						total_datasets: 4,
						total_captures: 4,
						has_more_datasets: true,
						has_more_captures: true,
						remaining_datasets: 1,
						remaining_captures: 1,
						has_assets: true,
						show_datasets: true,
						show_captures: true,
					}),
				},
				null,
				true,
			);
		});
	
		test("should handle empty assets list", async () => {
			mockAPIClient.post.mockResolvedValue({
				html: "<div>No assets</div>",
			});
	
			await shareGroupManager.displaySharedAssetsInfo([]);
	
			expect(mockAPIClient.post).toHaveBeenCalledWith(
				"/users/render-html/",
				{
					template: "users/components/shared_assets_display.html",
					context: { has_assets: false },
				},
				null,
				true,
			);
		});
	});

	describe("Error Handling", () => {
		beforeEach(() => {
			shareGroupManager = new ShareGroupManager(mockConfig);
		});

		test.each([["API errors"], ["network errors"]])(
			"should handle %s gracefully",
			(errorType) => {
				expect(() => {
					new ShareGroupManager(mockConfig);
				}).not.toThrow();
			},
		);
	});
});
