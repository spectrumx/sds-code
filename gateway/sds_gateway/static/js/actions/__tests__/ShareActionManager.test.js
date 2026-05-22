/**
 * Jest tests for ShareActionManager
 * Tests sharing functionality for different user access levels
 */

// Import the ShareActionManager class
import { ShareActionManager } from "../ShareActionManager.js";

const {
	createDefaultShareActionConfig,
	setupShareActionStandardTest,
	createShareSearchTestContext,
} = require("../../__tests__/helpers/actionTestMocks.js");

describe("ShareActionManager", () => {
	let shareManager;
	let mockConfig;

	beforeEach(() => {
		mockConfig = createDefaultShareActionConfig();
		setupShareActionStandardTest();
	});

	describe("Initialization", () => {
		test("should initialize with correct configuration", () => {
			shareManager = new ShareActionManager(mockConfig);

			expect(shareManager.itemUuid).toBe("test-uuid");
			expect(shareManager.itemType).toBe("dataset");
			expect(shareManager.permissions.canShare).toBe(true);
		});

		test("should initialize with empty state", () => {
			shareManager = new ShareActionManager(mockConfig);

			expect(shareManager.selectedUsersMap).toEqual({});
			expect(shareManager.pendingRemovals).toBeInstanceOf(Set);
			expect(shareManager.pendingPermissionChanges).toBeInstanceOf(Map);
		});
	});

	describe("Searching Users", () => {
		let mockAPIClient;
		let mockDropdown;

		beforeEach(() => {
			({ mockAPIClient, mockDropdown, shareManager } =
				createShareSearchTestContext(ShareActionManager));
		});

		test("should cancel previous request when new search starts", async () => {
			const abortController1 = new AbortController();
			shareManager.currentRequest = abortController1;
			const abortSpy = jest.spyOn(abortController1, "abort");

			mockAPIClient.get.mockResolvedValue([]);
			mockAPIClient.post.mockResolvedValue({ html: "<div>Results</div>" });

			await shareManager.searchUsers("new query", mockDropdown);

			expect(abortSpy).toHaveBeenCalled();
			expect(mockAPIClient.get).toHaveBeenCalledWith(
				"/users/share-item/dataset/test-uuid/",
				{ q: "new query", limit: 10 },
				null,
			);
		});

		test("should handle search errors gracefully", async () => {
			mockAPIClient.get.mockRejectedValue(new Error("Network error"));

			await shareManager.searchUsers("test", mockDropdown);

			expect(shareManager.displayError).toHaveBeenCalledWith(mockDropdown);
			expect(shareManager.currentRequest).toBeNull();
		});

		test("should ignore AbortError when request is cancelled", async () => {
			const abortError = new Error("Request aborted");
			abortError.name = "AbortError";
			mockAPIClient.get.mockRejectedValue(abortError);

			await shareManager.searchUsers("test", mockDropdown);

			expect(shareManager.displayError).not.toHaveBeenCalled();
			expect(shareManager.currentRequest).toBeNull();
		});

		test("should render HTML results from server", async () => {
			mockAPIClient.get.mockResolvedValue([
				{ email: "user1@example.com", name: "User 1" },
			]);
			mockAPIClient.post.mockResolvedValue({
				html: "<div>Rendered HTML</div>",
			});

			await shareManager.searchUsers("user", mockDropdown);

			expect(mockAPIClient.post).toHaveBeenCalledWith(
				"/users/render-html/",
				expect.objectContaining({
					template: "users/components/user_search_results.html",
					context: {
						users: [{ email: "user1@example.com", name: "User 1" }],
					},
				}),
				null,
				true,
			);
			expect(shareManager.displayResults).toHaveBeenCalledWith(
				{ html: "<div>Rendered HTML</div>" },
				mockDropdown,
			);
		});

		test("should handle empty search results", async () => {
			mockAPIClient.get.mockResolvedValue(null);
			shareManager.displayResults = jest.fn();

			await shareManager.searchUsers("nonexistent", mockDropdown);

			expect(shareManager.displayResults).toHaveBeenCalledWith(
				{ html: null, results: [] },
				mockDropdown,
			);
		});
	});

	describe("Selecting Users", () => {
		let shareManager;
		let mockInput;
		let mockItem;

		beforeEach(() => {
			window.PermissionLevels = {
				VIEWER: "viewer",
			};

			mockInput = {
				id: "user-search-test-uuid",
				value: "test@example.com",
				focus: jest.fn(),
			};

			mockItem = {
				dataset: {
					userName: "Test User",
					userEmail: "test@example.com",
					userType: "user",
				},
				closest: jest.fn(() => ({
					querySelector: jest.fn(),
				})),
			};

			shareManager = new ShareActionManager({
				itemUuid: "test-uuid",
				itemType: "dataset",
				permissions: {},
			});
			shareManager.renderChips = jest.fn();
			shareManager.hideDropdown = jest.fn();
			shareManager.checkUserInGroup = jest.fn();
		});

		test("should add user to selectedUsersMap when not already selected", () => {
			shareManager.selectUser(mockItem, mockInput);

			expect(shareManager.selectedUsersMap[mockInput.id]).toHaveLength(1);
			expect(shareManager.selectedUsersMap[mockInput.id][0]).toEqual({
				name: "Test User",
				email: "test@example.com",
				type: "user",
				permission_level: "viewer",
			});
			expect(shareManager.renderChips).toHaveBeenCalledWith(mockInput);
			expect(mockInput.value).toBe("");
		});

		test("should not add duplicate users", () => {
			shareManager.selectedUsersMap[mockInput.id] = [
				{ email: "test@example.com", name: "Test User" },
			];

			shareManager.selectUser(mockItem, mockInput);

			expect(shareManager.selectedUsersMap[mockInput.id]).toHaveLength(1);
			expect(shareManager.renderChips).not.toHaveBeenCalled();
		});

		test("should check if user is in selected group before adding", () => {
			shareManager.selectedUsersMap[mockInput.id] = [
				{
					email: "group:group-uuid",
					name: "Test Group",
					type: "group",
				},
			];

			shareManager.selectUser(mockItem, mockInput);

			expect(shareManager.checkUserInGroup).toHaveBeenCalledWith(
				"test@example.com",
				{ email: "group:group-uuid", name: "Test Group", type: "group" },
				mockInput,
				"Test User",
			);
			expect(shareManager.selectedUsersMap[mockInput.id]).toHaveLength(1);
		});

		test("should handle group selection with member count", () => {
			mockItem.dataset.userType = "group";
			mockItem.dataset.memberCount = "5";

			shareManager.selectUser(mockItem, mockInput);

			expect(shareManager.selectedUsersMap[mockInput.id][0]).toEqual({
				name: "Test User",
				email: "test@example.com",
				type: "group",
				permission_level: "viewer",
				member_count: 5,
			});
		});
	});

	describe("Share Methods", () => {
		let shareManager;
		let mockAPIClient;

		beforeEach(() => {
			mockAPIClient = {
				post: jest.fn(),
			};
			window.APIClient = mockAPIClient;

			window.PermissionLevels = {
				VIEWER: "viewer",
				CONTRIBUTOR: "contributor",
				CO_OWNER: "co-owner",
			};

			document.getElementById = jest.fn((id) => {
				if (id === "notify-users-checkbox-test-uuid") {
					return { checked: false, value: "" };
				}
				return null;
			});

			window.DOMUtils = {
				showMessage: jest.fn(),
			};

			window.location = { reload: jest.fn() };

			shareManager = new ShareActionManager({
				itemUuid: "test-uuid",
				itemType: "dataset",
				permissions: {},
			});

			shareManager.selectedUsersMap = {
				"user-search-test-uuid": [
					{ email: "user1@example.com", permission_level: "viewer" },
					{ email: "user2@example.com", permission_level: "contributor" },
				],
			};
			shareManager.pendingRemovals = new Set(["user3@example.com"]);
			shareManager.pendingPermissionChanges = new Map([
				["user1@example.com", "contributor"],
			]);
			shareManager.closeModal = jest.fn();
		});

		test("should share item with multiple users and handle removals", async () => {
			mockAPIClient.post.mockResolvedValue({
				success: true,
				message: "Dataset shared successfully",
			});

			await shareManager.handleShareItem();

			expect(mockAPIClient.post).toHaveBeenCalledWith(
				"/users/share-item/dataset/test-uuid/",
				expect.objectContaining({
					"user-search": "user1@example.com,user2@example.com",
					remove_users: JSON.stringify(["user3@example.com"]),
					permission_changes: JSON.stringify([
						["user1@example.com", "contributor"],
					]),
				}),
			);
			expect(window.DOMUtils.showMessage).toHaveBeenCalledWith(
				"Dataset shared successfully",
				expect.objectContaining({
					variant: "success",
					placement: "toast",
					presentation: "toast",
				}),
			);
		});

		test("should include notification when checkbox is checked", async () => {
			document.getElementById.mockReturnValue({
				checked: true,
				value: "",
			});

			mockAPIClient.post.mockResolvedValue({ success: true });

			await shareManager.handleShareItem();

			expect(mockAPIClient.post).toHaveBeenCalledWith(
				expect.any(String),
				expect.objectContaining({
					notify_users: "1",
				}),
			);
		});
	});

	describe("List refresh after share", () => {
		let shareManager;
		let mockAPIClient;
		let reloadMock;

		beforeEach(() => {
			mockAPIClient = { post: jest.fn() };
			window.APIClient = mockAPIClient;
			window.PermissionLevels = { VIEWER: "viewer" };
			document.getElementById = jest.fn((id) => {
				if (id === "notify-users-checkbox-test-uuid") {
					return { checked: false, value: "" };
				}
				return null;
			});
			window.DOMUtils = { showMessage: jest.fn() };
			reloadMock = jest.fn();
			Object.defineProperty(window, "location", {
				value: { reload: reloadMock },
				writable: true,
				configurable: true,
			});
			window.listRefreshManager = {
				loadTable: jest.fn().mockResolvedValue("<table></table>"),
			};

			shareManager = new ShareActionManager({
				itemUuid: "test-uuid",
				itemType: "dataset",
				permissions: {},
			});
			shareManager.selectedUsersMap = {
				"user-search-test-uuid": [
					{ email: "user1@example.com", permission_level: "viewer" },
				],
			};
			shareManager.pendingRemovals = new Set();
			shareManager.pendingPermissionChanges = new Map();
			shareManager.closeModal = jest.fn();
			shareManager.showToast = jest.fn();
		});

		test("should await listRefreshManager.loadTable after successful share", async () => {
			mockAPIClient.post.mockResolvedValue({ success: true });

			await shareManager.handleShareItem();

			expect(shareManager.closeModal).toHaveBeenCalledWith(
				"shareModal-test-uuid",
			);
			expect(window.listRefreshManager.loadTable).toHaveBeenCalled();
			expect(reloadMock).not.toHaveBeenCalled();
		});

		test("should reload page when listRefreshManager is unavailable", async () => {
			window.listRefreshManager = undefined;
			console.warn = jest.fn();
			mockAPIClient.post.mockResolvedValue({ success: true });

			await shareManager.handleShareItem();

			expect(console.warn).toHaveBeenCalledWith(
				"listRefreshManager not available, reloading page",
			);
			expect(reloadMock).toHaveBeenCalled();
		});
	});

	describe("Utility methods", () => {
		beforeEach(() => {
			window.DOMUtils.showMessage = jest.fn();
			shareManager = new ShareActionManager(mockConfig);
		});

		test("getPermissionButtonText includes icon class and capitalized label", () => {
			shareManager.permissions = {
				getPermissionIcon: jest.fn(() => "bi-eye"),
			};

			const text = shareManager.getPermissionButtonText("viewer");

			expect(text).toContain('class="bi bi-eye me-1"');
			expect(text).toContain("Viewer");
			expect(shareManager.permissions.getPermissionIcon).toHaveBeenCalledWith(
				"viewer",
			);
		});

		test("showToast routes success and danger through showMessage", () => {
			shareManager.showToast("Saved", "success");
			shareManager.showToast("Failed", "danger");

			expect(shareManager.showMessage).toHaveBeenCalledWith(
				"Saved",
				expect.objectContaining({ variant: "success", presentation: "toast" }),
			);
			expect(shareManager.showMessage).toHaveBeenCalledWith(
				"Failed",
				expect.objectContaining({ variant: "danger", presentation: "toast" }),
			);
		});
	});

	describe("Error Handling", () => {
		beforeEach(() => {
			shareManager = new ShareActionManager(mockConfig);
		});

		test("should handle missing DOM elements gracefully", () => {
			document.getElementById = jest.fn(() => null);
			document.querySelector = jest.fn(() => null);

			// Mock bootstrap.Modal.getInstance to return null for missing modals
			global.bootstrap.Modal.getInstance = jest.fn(() => null);

			expect(() => {
				shareManager.closeModal();
				shareManager.updateSaveButtonState("test-uuid");
			}).not.toThrow();
		});

		test("searchUsers surfaces non-abort errors via displayError", async () => {
			const mockDropdown = { innerHTML: "" };
			shareManager.displayError = jest.fn();
			global.APIClient.get.mockRejectedValue(new Error("API Error"));

			await shareManager.searchUsers("x", mockDropdown);

			expect(shareManager.displayError).toHaveBeenCalledWith(mockDropdown);
			expect(shareManager.currentRequest).toBeNull();
		});

		test("should handle invalid data gracefully", () => {
			expect(() => {
				shareManager.handlePermissionLevelChange(
					"test@example.com",
					"read",
					"test-uuid",
				);
			}).not.toThrow();
		});
	});

	describe("State management", () => {
		const itemUuid = "test-uuid";

		beforeEach(() => {
			shareManager = new ShareActionManager(mockConfig);
		});

		test("clearSelections resets maps and pending change sets", () => {
			shareManager.selectedUsersMap = {
				[`user-search-${itemUuid}`]: [{ email: "a@b.com" }],
			};
			shareManager.pendingRemovals.add("a@b.com");
			shareManager.pendingPermissionChanges.set("a@b.com", "viewer");

			shareManager.clearSelections();

			expect(shareManager.selectedUsersMap).toEqual({});
			expect(shareManager.pendingRemovals.size).toBe(0);
			expect(shareManager.pendingPermissionChanges.size).toBe(0);
		});

		test("updateSaveButtonState disables save when no pending work", () => {
			const saveBtn = { disabled: false };
			document.getElementById = jest.fn((id) =>
				id === `share-item-btn-${itemUuid}` ? saveBtn : null,
			);

			shareManager.updateSaveButtonState(itemUuid);

			expect(saveBtn.disabled).toBe(true);
		});

		test("updateSaveButtonState enables save when users are selected", () => {
			const saveBtn = { disabled: true };
			document.getElementById = jest.fn((id) =>
				id === `share-item-btn-${itemUuid}` ? saveBtn : null,
			);
			shareManager.selectedUsersMap[`user-search-${itemUuid}`] = [
				{ email: "user@example.com" },
			];

			shareManager.updateSaveButtonState(itemUuid);

			expect(saveBtn.disabled).toBe(false);
		});
	});
});
