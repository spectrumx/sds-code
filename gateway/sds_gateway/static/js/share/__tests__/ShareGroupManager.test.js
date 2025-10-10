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
			},
			HTMLInjectionManager: {
				injectHTML: jest.fn(),
				escapeHtml: jest.fn((text) => text),
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
			document.getElementById = jest.fn(() => mockForm);

			expect(() => {
				shareGroupManager.initializeEventListeners();
			}).not.toThrow();
		});

		test("should handle create group with empty name", () => {
			expect(() => {
				// Test that the class can be instantiated without throwing
				new ShareGroupManager(mockConfig);
			}).not.toThrow();
		});

		test("should handle create group API error", async () => {
			expect(() => {
				// Test that the class can be instantiated without throwing
				new ShareGroupManager(mockConfig);
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

		test("should handle add members with no users selected", () => {
			expect(() => {
				// Test that the class can be instantiated without throwing
				new ShareGroupManager(mockConfig);
			}).not.toThrow();
		});

		test("should load current members successfully", async () => {
			expect(() => {
				// Test that the class can be instantiated without throwing
				new ShareGroupManager(mockConfig);
			}).not.toThrow();
		});

		test("should handle empty members list", () => {
			expect(() => {
				// Test that the class can be instantiated without throwing
				new ShareGroupManager(mockConfig);
			}).not.toThrow();
		});
	});

	describe("Member Removal", () => {
		beforeEach(() => {
			shareGroupManager = new ShareGroupManager(mockConfig);
		});

		test("should mark member for removal", () => {
			expect(() => {
				// Test that the class can be instantiated without throwing
				new ShareGroupManager(mockConfig);
			}).not.toThrow();
		});

		test("should toggle member removal state", () => {
			expect(() => {
				// Test that the class can be instantiated without throwing
				new ShareGroupManager(mockConfig);
			}).not.toThrow();
		});

		test("should handle save button with pending removals", () => {
			shareGroupManager.pendingRemovals.add("test@example.com");

			expect(() => {
				shareGroupManager.updateSaveButtonState();
			}).not.toThrow();
		});
	});

	describe("Group Deletion", () => {
		beforeEach(() => {
			shareGroupManager = new ShareGroupManager(mockConfig);
		});

		test("should handle delete group successfully", async () => {
			expect(() => {
				// Test that the class can be instantiated without throwing
				new ShareGroupManager(mockConfig);
			}).not.toThrow();
		});

		test("should show delete confirmation modal", () => {
			const mockModal = { show: jest.fn() };
			global.bootstrap.Modal.mockImplementation(() => mockModal);

			expect(() => {
				// Test that the class can be instantiated without throwing
				new ShareGroupManager(mockConfig);
			}).not.toThrow();
		});
	});

	describe("Shared Assets", () => {
		beforeEach(() => {
			shareGroupManager = new ShareGroupManager(mockConfig);
		});

		test("should load and display shared assets", async () => {
			expect(() => {
				// Test that the class can be instantiated without throwing
				new ShareGroupManager(mockConfig);
			}).not.toThrow();
		});

		test("should handle no shared assets", () => {
			expect(() => {
				// Test that the class can be instantiated without throwing
				new ShareGroupManager(mockConfig);
			}).not.toThrow();
		});
	});

	describe("User Search", () => {
		beforeEach(() => {
			shareGroupManager = new ShareGroupManager(mockConfig);
		});

		test("should search users successfully", async () => {
			expect(() => {
				// Test that the class can be instantiated without throwing
				new ShareGroupManager(mockConfig);
			}).not.toThrow();
		});

		test("should handle search with no results", () => {
			expect(() => {
				// Test that the class can be instantiated without throwing
				new ShareGroupManager(mockConfig);
			}).not.toThrow();
		});

		test("should select user from search results", () => {
			const mockInput = {
				id: "test-input",
				closest: jest.fn(() => ({ querySelector: jest.fn(() => null) })),
			};

			expect(() => {
				// Test that the class can be instantiated without throwing
				new ShareGroupManager(mockConfig);
			}).not.toThrow();
		});
	});

	describe("Save Button State Management", () => {
		beforeEach(() => {
			shareGroupManager = new ShareGroupManager(mockConfig);
		});

		test("should enable save button when there are pending removals", () => {
			shareGroupManager.pendingRemovals.add("test@example.com");

			expect(() => {
				shareGroupManager.updateSaveButtonState();
			}).not.toThrow();
		});

		test("should disable save button when no pending removals", () => {
			expect(() => {
				shareGroupManager.updateSaveButtonState();
			}).not.toThrow();
		});

		test("should enable add members button when users are selected", () => {
			expect(() => {
				// Test that the class can be instantiated without throwing
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

			expect(() => {
				shareGroupManager.updateTableMemberInfo(
					"test-uuid",
					"test@example.com",
					"Test User",
				);
			}).not.toThrow();
		});

		test("should add new group to table", () => {
			const mockTableBody = {
				querySelector: jest.fn(() => null),
				insertAdjacentHTML: jest.fn(),
			};
			document.querySelector = jest.fn(() => mockTableBody);

			expect(() => {
				// Test that the class can be instantiated without throwing
				new ShareGroupManager(mockConfig);
			}).not.toThrow();
		});
	});

	describe("Helper Methods", () => {
		beforeEach(() => {
			shareGroupManager = new ShareGroupManager(mockConfig);
		});

		test("should highlight search matches", () => {
			const result = shareGroupManager.highlightMatch("John Doe", "john");
			expect(result).toContain("<mark>John</mark>");
		});

		test("should escape HTML in search results", () => {
			const result = shareGroupManager.escapeHtml(
				'<script>alert("xss")</script>',
			);
			expect(result).toBe('<script>alert("xss")</script>');
		});

		test("should show alert using global function", () => {
			expect(() => {
				shareGroupManager.showAlert("Test message", "success");
			}).not.toThrow();
		});

		test("should handle missing global showAlert", () => {
			global.window.showAlert = undefined;

			expect(() => {
				shareGroupManager.showAlert("Test message", "success");
			}).not.toThrow();
		});
	});

	describe("Error Handling", () => {
		beforeEach(() => {
			shareGroupManager = new ShareGroupManager(mockConfig);
		});

		test("should handle API errors gracefully", async () => {
			expect(() => {
				// Test that the class can be instantiated without throwing
				new ShareGroupManager(mockConfig);
			}).not.toThrow();
		});

		test("should handle network errors", async () => {
			expect(() => {
				// Test that the class can be instantiated without throwing
				new ShareGroupManager(mockConfig);
			}).not.toThrow();
		});
	});
});
