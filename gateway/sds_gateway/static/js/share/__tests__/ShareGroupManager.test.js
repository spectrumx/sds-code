/**
 * ShareGroupManager Test Suite
 * Tests for share group management functionality
 */

// Import the ShareGroupManager class
import { ShareGroupManager } from "../ShareGroupManager.js";

const { setupStandardUnitTest } = require("../../tests-config/testHelpers.js");

describe("ShareGroupManager", () => {
	let shareGroupManager;
	let mockConfig;

	beforeEach(() => {
		mockConfig = {
			apiEndpoint: "/users/share-groups/",
		};

		setupStandardUnitTest({
			useModalDomUtils: true,
			apiClientOverrides: {
				request: jest.fn().mockResolvedValue({ success: true }),
				get: jest.fn().mockResolvedValue({ success: true }),
				post: jest.fn().mockResolvedValue({ html: "<div>Test HTML</div>" }),
			},
		});

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

	});

	describe("Member Removal", () => {
		beforeEach(() => {
			shareGroupManager = new ShareGroupManager(mockConfig);
			document.getElementById = jest.fn((id) => {
				if (id === "save-sharegroup-btn") {
					return { disabled: true };
				}
				if (id === "add-members-btn") {
					return { disabled: true };
				}
				return null;
			});
		});

		test("updateSaveButtonState enables save only when removals are pending", () => {
			const saveBtn = { disabled: true };
			document.getElementById = jest.fn((id) =>
				id === "save-sharegroup-btn" ? saveBtn : null,
			);

			shareGroupManager.updateSaveButtonState();
			expect(saveBtn.disabled).toBe(true);

			shareGroupManager.pendingRemovals.add("member@example.com");
			shareGroupManager.updateSaveButtonState();
			expect(saveBtn.disabled).toBe(false);
		});
	});

	describe("Table Updates", () => {
		beforeEach(() => {
			shareGroupManager = new ShareGroupManager(mockConfig);
		});

		test("updateTableMemberInfo sets count and first three emails", () => {
			const memberCountElement = { textContent: "" };
			const memberEmailsElement = { innerHTML: "" };
			document.querySelector = jest.fn((selector) => {
				if (selector.includes("member-count")) {
					return memberCountElement;
				}
				if (selector.includes("member-emails")) {
					return memberEmailsElement;
				}
				return null;
			});
			global.window.DOMUtils.show = jest.fn();
			global.window.DOMUtils.hide = jest.fn();

			const members = [
				{ email: "a@example.com" },
				{ email: "b@example.com" },
				{ email: "c@example.com" },
				{ email: "d@example.com" },
			];

			shareGroupManager.updateTableMemberInfo("group-1", members);

			expect(memberCountElement.textContent).toBe("4 members");
			expect(memberEmailsElement.innerHTML).toContain("a@example.com");
			expect(memberEmailsElement.innerHTML).toContain("and 1 more");
			expect(global.window.DOMUtils.show).toHaveBeenCalledWith(
				memberEmailsElement,
			);
		});
	});

	describe("Helper Methods", () => {
		beforeEach(() => {
			shareGroupManager = new ShareGroupManager(mockConfig);
		});

		test("domToast path uses showMessage when group name missing", async () => {
			document.getElementById = jest.fn((id) => {
				if (id === "groupName") return { value: "" };
				return null;
			});
			global.window.DOMUtils.showMessage = jest.fn();
			const mgr = new ShareGroupManager(mockConfig);
			await mgr.handleCreateGroup({});

			expect(global.window.DOMUtils.showMessage).toHaveBeenCalledWith(
				"Group name is required",
				expect.objectContaining({
					variant: "danger",
					placement: "toast",
					presentation: "toast",
				}),
			);
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

});
