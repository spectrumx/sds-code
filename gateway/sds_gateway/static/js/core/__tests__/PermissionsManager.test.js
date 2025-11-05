/**
 * Jest tests for PermissionsManager
 * Tests permission checking functionality for different user access levels
 */

// Import the PermissionsManager class
import { PermissionsManager } from "../PermissionsManager.js";

describe("PermissionsManager", () => {
	let permissions;

	beforeEach(() => {
		// Reset mocks before each test
		jest.clearAllMocks();
	});

	describe("Owner permissions", () => {
		beforeEach(() => {
			permissions = new PermissionsManager({
				userPermissionLevel: "owner",
				datasetUuid: "test-uuid",
				currentUserId: 1,
				isOwner: true,
				datasetPermissions: {},
			});
		});

		test("should have all permissions", () => {
			expect(permissions.canEditMetadata()).toBe(true);
			expect(permissions.canAddAssets()).toBe(true);
			expect(permissions.canRemoveAnyAssets()).toBe(true);
			expect(permissions.canRemoveOwnAssets()).toBe(true);
			expect(permissions.canShare()).toBe(true);
			expect(permissions.canDownload()).toBe(true);
			expect(permissions.canView()).toBe(true);
		});
	});

	describe("Co-owner permissions", () => {
		beforeEach(() => {
			permissions = new PermissionsManager({
				userPermissionLevel: "co-owner",
				datasetUuid: "test-uuid",
				currentUserId: 2,
				isOwner: false,
				datasetPermissions: {},
			});
		});

		test("should have same permissions as owner", () => {
			expect(permissions.canEditMetadata()).toBe(true);
			expect(permissions.canAddAssets()).toBe(true);
			expect(permissions.canRemoveAnyAssets()).toBe(true);
			expect(permissions.canRemoveOwnAssets()).toBe(true);
			expect(permissions.canShare()).toBe(true);
			expect(permissions.canDownload()).toBe(true);
			expect(permissions.canView()).toBe(true);
		});
	});

	describe("Contributor permissions", () => {
		beforeEach(() => {
			permissions = new PermissionsManager({
				userPermissionLevel: "contributor",
				datasetUuid: "test-uuid",
				currentUserId: 3,
				isOwner: false,
				datasetPermissions: {},
			});
		});

		test("should have limited permissions", () => {
			expect(permissions.canEditMetadata()).toBe(false);
			expect(permissions.canAddAssets()).toBe(true);
			expect(permissions.canRemoveAnyAssets()).toBe(false);
			expect(permissions.canRemoveOwnAssets()).toBe(true);
			expect(permissions.canShare()).toBe(false);
			expect(permissions.canDownload()).toBe(true);
			expect(permissions.canView()).toBe(true);
		});
	});

	describe("Viewer permissions", () => {
		beforeEach(() => {
			permissions = new PermissionsManager({
				userPermissionLevel: "viewer",
				datasetUuid: "test-uuid",
				currentUserId: 4,
				isOwner: false,
				datasetPermissions: {},
			});
		});

		test("should have minimal permissions", () => {
			expect(permissions.canEditMetadata()).toBe(false);
			expect(permissions.canAddAssets()).toBe(false);
			expect(permissions.canRemoveAnyAssets()).toBe(false);
			expect(permissions.canRemoveOwnAssets()).toBe(false);
			expect(permissions.canShare()).toBe(false);
			expect(permissions.canDownload()).toBe(true);
			expect(permissions.canView()).toBe(true);
		});
	});

	describe("Asset ownership permissions", () => {
		beforeEach(() => {
			permissions = new PermissionsManager({
				userPermissionLevel: "contributor",
				datasetUuid: "test-uuid",
				currentUserId: 5,
				isOwner: false,
				datasetPermissions: {},
			});
		});

		test("should handle asset ownership correctly", () => {
			const ownedAsset = { owner_id: 5, name: "test-asset" };
			const otherAsset = { owner_id: 6, name: "other-asset" };

			expect(permissions.canAddAsset(ownedAsset)).toBe(true);
			expect(permissions.canAddAsset(otherAsset)).toBe(false);
			expect(permissions.canRemoveAsset(ownedAsset)).toBe(true);
			expect(permissions.canRemoveAsset(otherAsset)).toBe(false);
		});
	});

	describe("Co-owner asset permissions", () => {
		beforeEach(() => {
			permissions = new PermissionsManager({
				userPermissionLevel: "co-owner",
				datasetUuid: "test-uuid",
				currentUserId: 7,
				isOwner: false,
				datasetPermissions: {},
			});
		});

		test("should handle co-owner asset permissions", () => {
			const ownedAsset = { owner_id: 7, name: "test-asset" };
			const otherAsset = { owner_id: 8, name: "other-asset" };

			expect(permissions.canAddAsset(ownedAsset)).toBe(true);
			expect(permissions.canAddAsset(otherAsset)).toBe(true);
			expect(permissions.canRemoveAsset(ownedAsset)).toBe(true);
			expect(permissions.canRemoveAsset(otherAsset)).toBe(true);
		});
	});

	describe("Permission display names", () => {
		test.each([
			["owner", "Owner"],
			["co-owner", "Co-Owner"],
			["contributor", "Contributor"],
			["viewer", "Viewer"],
		])("should return correct display name for %s", (level, expected) => {
			expect(permissions.getPermissionDisplayName(level)).toBe(expected);
		});
	});

	describe("Permission descriptions", () => {
		test.each([
			["owner", "Full control"],
			["co-owner", "edit metadata"],
			["contributor", "their own"],
			["viewer", "only view"],
		])(
			"should return description containing '%s' for %s",
			(level, expectedText) => {
				const desc = permissions.getPermissionDescription(level);
				expect(desc).toContain(expectedText);
			},
		);
	});

	describe("Permission icons", () => {
		test.each([
			["owner", "bi-person-circle"],
			["co-owner", "bi-gear"],
			["contributor", "bi-plus-circle"],
			["viewer", "bi-eye"],
		])("should return correct icon for %s", (level, expected) => {
			expect(permissions.getPermissionIcon(level)).toBe(expected);
		});
	});

	describe("Permission badge classes", () => {
		test.each([
			["owner", "bg-owner"],
			["co-owner", "bg-co-owner"],
			["contributor", "bg-contributor"],
			["viewer", "bg-viewer"],
		])("should return correct badge class for %s", (level, expected) => {
			expect(permissions.getPermissionBadgeClass(level)).toBe(expected);
		});
	});

	describe("Permission hierarchy", () => {
		test("should correctly identify permission hierarchy", () => {
			expect(PermissionsManager.isHigherPermission("owner", "co-owner")).toBe(
				true,
			);
			expect(
				PermissionsManager.isHigherPermission("co-owner", "contributor"),
			).toBe(true);
			expect(
				PermissionsManager.isHigherPermission("contributor", "viewer"),
			).toBe(true);
			expect(
				PermissionsManager.isHigherPermission("viewer", "contributor"),
			).toBe(false);
		});
	});

	describe("Permission summary", () => {
		beforeEach(() => {
			permissions = new PermissionsManager({
				userPermissionLevel: "contributor",
				datasetUuid: "test-uuid",
				currentUserId: 9,
				isOwner: false,
				datasetPermissions: {},
			});
		});

		test("should return correct permission summary", () => {
			const summary = permissions.getPermissionSummary();

			expect(summary.userPermissionLevel).toBe("contributor");
			expect(summary.displayName).toBe("Contributor");
			expect(summary.isEditMode).toBe(true);
			expect(summary.isOwner).toBe(false);
			expect(summary.permissions.canEditMetadata).toBe(false);
			expect(summary.permissions.canShare).toBe(false);
		});
	});

	describe("Has any permission", () => {
		beforeEach(() => {
			permissions = new PermissionsManager({
				userPermissionLevel: "contributor",
				datasetUuid: "test-uuid",
				currentUserId: 10,
				isOwner: false,
				datasetPermissions: {},
			});
		});

		test("should correctly check if user has any of specified permissions", () => {
			expect(
				permissions.hasAnyPermission(["canAddAssets", "canRemoveAnyAssets"]),
			).toBe(true);
			expect(
				permissions.hasAnyPermission(["canShare", "canEditMetadata"]),
			).toBe(false);
		});
	});

	describe("Has all permissions", () => {
		beforeEach(() => {
			permissions = new PermissionsManager({
				userPermissionLevel: "contributor",
				datasetUuid: "test-uuid",
				currentUserId: 11,
				isOwner: false,
				datasetPermissions: {},
			});
		});

		test("should correctly check if user has all specified permissions", () => {
			expect(
				permissions.hasAllPermissions(["canEditMetadata", "canAddAssets"]),
			).toBe(false);
			expect(
				permissions.hasAllPermissions(["canEditMetadata", "canShare"]),
			).toBe(false);
		});
	});

	describe("Update dataset permissions", () => {
		beforeEach(() => {
			permissions = new PermissionsManager({
				userPermissionLevel: "viewer",
				datasetUuid: "test-uuid",
				currentUserId: 12,
				isOwner: false,
				datasetPermissions: {},
			});
		});

		test("should update dataset permissions correctly", () => {
			// Initially should not be able to edit metadata
			expect(permissions.canEditMetadata()).toBe(false);

			// Update permissions
			permissions.updateDatasetPermissions({ canEditMetadata: true });

			// Now should be able to edit metadata
			expect(permissions.canEditMetadata()).toBe(true);
		});
	});
});
