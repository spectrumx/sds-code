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
		test("should return correct display names", () => {
			expect(permissions.getPermissionDisplayName("owner")).toBe("Owner");
			expect(permissions.getPermissionDisplayName("co-owner")).toBe("Co-Owner");
			expect(permissions.getPermissionDisplayName("contributor")).toBe(
				"Contributor",
			);
			expect(permissions.getPermissionDisplayName("viewer")).toBe("Viewer");
		});
	});

	describe("Permission descriptions", () => {
		test("should return correct descriptions", () => {
			const ownerDesc = permissions.getPermissionDescription("owner");
			const coOwnerDesc = permissions.getPermissionDescription("co-owner");
			const contributorDesc =
				permissions.getPermissionDescription("contributor");
			const viewerDesc = permissions.getPermissionDescription("viewer");

			expect(ownerDesc).toContain("Full control");
			expect(coOwnerDesc).toContain("edit metadata");
			expect(contributorDesc).toContain("their own");
			expect(viewerDesc).toContain("only view");
		});
	});

	describe("Permission icons", () => {
		test("should return correct icons", () => {
			expect(permissions.getPermissionIcon("owner")).toBe("bi-person-circle");
			expect(permissions.getPermissionIcon("co-owner")).toBe("bi-gear");
			expect(permissions.getPermissionIcon("contributor")).toBe(
				"bi-plus-circle",
			);
			expect(permissions.getPermissionIcon("viewer")).toBe("bi-eye");
		});
	});

	describe("Permission badge classes", () => {
		test("should return correct badge classes", () => {
			expect(permissions.getPermissionBadgeClass("owner")).toBe("bg-owner");
			expect(permissions.getPermissionBadgeClass("co-owner")).toBe(
				"bg-co-owner",
			);
			expect(permissions.getPermissionBadgeClass("contributor")).toBe(
				"bg-contributor",
			);
			expect(permissions.getPermissionBadgeClass("viewer")).toBe("bg-viewer");
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
