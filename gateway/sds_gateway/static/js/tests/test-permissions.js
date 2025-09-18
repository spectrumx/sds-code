/**
 * Tests for PermissionsManager
 * Tests permission checking functionality for different user access levels
 */

// Mock DOM environment for testing
const mockDOM = {
	createElement: (tag) => ({
		tagName: tag,
		textContent: "",
		innerHTML: "",
		classList: {
			add: () => {},
			remove: () => {},
			contains: () => false,
		},
		querySelector: () => null,
		querySelectorAll: () => [],
	}),
	querySelector: () => null,
	querySelectorAll: () => [],
};

// Mock global objects
global.document = mockDOM;
global.window = {};

// Import the actual PermissionsManager
// Since this is a test environment, we need to load the actual implementation
const fs = require("node:fs");
const path = require("node:path");

// Read and evaluate the PermissionsManager.js file
const permissionsManagerPath = path.join(
	__dirname,
	"../core/PermissionsManager.js",
);
const permissionsManagerCode = fs.readFileSync(permissionsManagerPath, "utf8");

// Execute the PermissionsManager code in our context
// biome-ignore lint/security/noGlobalEval: <explanation>
// Loading trusted test code in controlled environment
eval(permissionsManagerCode);

// The PermissionsManager class is now available via window.PermissionsManager
const PermissionsManager = global.window.PermissionsManager;

// Test suite for PermissionsManager
class PermissionsManagerTests {
	constructor() {
		this.tests = [];
		this.passed = 0;
		this.failed = 0;
	}

	/**
	 * Add a test case
	 * @param {string} name - Test name
	 * @param {Function} testFn - Test function
	 */
	addTest(name, testFn) {
		this.tests.push({ name, testFn });
	}

	/**
	 * Run all tests
	 */
	async runTests() {
		console.log("Running PermissionsManager tests...");

		for (const test of this.tests) {
			try {
				await test.testFn();
				this.passed++;
				console.log(`✅ ${test.name}`);
			} catch (error) {
				this.failed++;
				console.log(`❌ ${test.name}: ${error.message}`);
			}
		}

		console.log(`\nTest Results: ${this.passed} passed, ${this.failed} failed`);
		return this.failed === 0;
	}

	/**
	 * Assert that a condition is true
	 * @param {boolean} condition - Condition to test
	 * @param {string} message - Error message if condition is false
	 */
	assert(condition, message) {
		if (!condition) {
			throw new Error(message);
		}
	}

	/**
	 * Assert that two values are equal
	 * @param {*} actual - Actual value
	 * @param {*} expected - Expected value
	 * @param {string} message - Error message if values are not equal
	 */
	assertEqual(actual, expected, message) {
		if (actual !== expected) {
			throw new Error(`${message}. Expected: ${expected}, Actual: ${actual}`);
		}
	}

	/**
	 * Assert that an array contains an item
	 * @param {Array} array - Array to test
	 * @param {*} item - Item to find
	 * @param {string} message - Error message if item is not found
	 */
	assertContains(array, item, message) {
		if (!array.includes(item)) {
			throw new Error(
				`${message}. Array: ${JSON.stringify(array)}, Item: ${item}`,
			);
		}
	}
}

// Create test suite
const permissionsTests = new PermissionsManagerTests();

// Test 1: Owner permissions
permissionsTests.addTest("Owner has all permissions", () => {
	const permissions = new PermissionsManager({
		userPermissionLevel: "owner",
		datasetUuid: "test-uuid",
		currentUserId: 1,
		isOwner: true,
		datasetPermissions: {},
	});

	permissionsTests.assert(
		permissions.canEditMetadata(),
		"Owner should be able to edit metadata",
	);
	permissionsTests.assert(
		permissions.canAddAssets(),
		"Owner should be able to add assets",
	);
	permissionsTests.assert(
		permissions.canRemoveAnyAssets(),
		"Owner should be able to remove any assets",
	);
	permissionsTests.assert(
		permissions.canRemoveOwnAssets(),
		"Owner should be able to remove their own assets",
	);
	permissionsTests.assert(
		permissions.canShare(),
		"Owner should be able to share",
	);
	permissionsTests.assert(
		permissions.canDownload(),
		"Owner should be able to download",
	);
	permissionsTests.assert(
		permissions.canDelete(),
		"Owner should be able to delete",
	);
	permissionsTests.assert(
		permissions.canView(),
		"Owner should be able to view",
	);
});

// Test 2: Co-owner permissions
permissionsTests.addTest("Co-owner has all permissions", () => {
	const permissions = new PermissionsManager({
		userPermissionLevel: "co-owner",
		datasetUuid: "test-uuid",
		currentUserId: 2,
		isOwner: false,
		datasetPermissions: {},
	});

	permissionsTests.assert(
		permissions.canEditMetadata(),
		"Co-owner should be able to edit metadata",
	);
	permissionsTests.assert(
		permissions.canAddAssets(),
		"Co-owner should be able to add assets",
	);
	permissionsTests.assert(
		permissions.canRemoveAnyAssets(),
		"Co-owner should be able to remove any assets",
	);
	permissionsTests.assert(
		permissions.canRemoveOwnAssets(),
		"Co-owner should be able to remove their own assets",
	);
	permissionsTests.assert(
		permissions.canShare(),
		"Co-owner should be able to share",
	);
	permissionsTests.assert(
		permissions.canDownload(),
		"Co-owner should be able to download",
	);
	permissionsTests.assert(
		permissions.canDelete(),
		"Co-owner should be able to delete",
	);
	permissionsTests.assert(
		permissions.canView(),
		"Co-owner should be able to view",
	);
});

// Test 3: Contributor permissions
permissionsTests.addTest("Contributor has limited permissions", () => {
	const permissions = new PermissionsManager({
		userPermissionLevel: "contributor",
		datasetUuid: "test-uuid",
		currentUserId: 3,
		isOwner: false,
		datasetPermissions: {},
	});

	permissionsTests.assert(
		!permissions.canEditMetadata(),
		"Contributor should NOT be able to edit metadata",
	);
	permissionsTests.assert(
		permissions.canAddAssets(),
		"Contributor should be able to add assets",
	);
	permissionsTests.assert(
		!permissions.canRemoveAnyAssets(),
		"Contributor should not be able to remove any assets",
	);
	permissionsTests.assert(
		permissions.canRemoveOwnAssets(),
		"Contributor should be able to remove their own assets",
	);
	permissionsTests.assert(
		!permissions.canShare(),
		"Contributor should not be able to share",
	);
	permissionsTests.assert(
		permissions.canDownload(),
		"Contributor should be able to download",
	);
	permissionsTests.assert(
		!permissions.canDelete(),
		"Contributor should not be able to delete",
	);
	permissionsTests.assert(
		permissions.canView(),
		"Contributor should be able to view",
	);
});

// Test 4: Viewer permissions
permissionsTests.addTest("Viewer has minimal permissions", () => {
	const permissions = new PermissionsManager({
		userPermissionLevel: "viewer",
		datasetUuid: "test-uuid",
		currentUserId: 4,
		isOwner: false,
		datasetPermissions: {},
	});

	permissionsTests.assert(
		!permissions.canEditMetadata(),
		"Viewer should not be able to edit metadata",
	);
	permissionsTests.assert(
		!permissions.canAddAssets(),
		"Viewer should not be able to add assets",
	);
	permissionsTests.assert(
		!permissions.canRemoveAnyAssets(),
		"Viewer should not be able to remove any assets",
	);
	permissionsTests.assert(
		!permissions.canRemoveOwnAssets(),
		"Viewer should not be able to remove their own assets",
	);
	permissionsTests.assert(
		!permissions.canShare(),
		"Viewer should not be able to share",
	);
	permissionsTests.assert(
		permissions.canDownload(),
		"Viewer should be able to download",
	);
	permissionsTests.assert(
		!permissions.canDelete(),
		"Viewer should not be able to delete",
	);
	permissionsTests.assert(
		permissions.canView(),
		"Viewer should be able to view",
	);
});

// Test 5: Asset ownership permissions
permissionsTests.addTest("Contributor asset ownership permissions", () => {
	const permissions = new PermissionsManager({
		userPermissionLevel: "contributor",
		datasetUuid: "test-uuid",
		currentUserId: 5,
		isOwner: false,
		datasetPermissions: {},
	});

	const ownedAsset = { owner_id: 5, name: "test-asset" };
	const otherAsset = { owner_id: 6, name: "other-asset" };

	permissionsTests.assert(
		permissions.canAddAsset(ownedAsset),
		"Contributor should be able to add their own assets",
	);
	permissionsTests.assert(
		!permissions.canAddAsset(otherAsset),
		"Contributor should not be able to add others' assets",
	);
	permissionsTests.assert(
		permissions.canRemoveAsset(ownedAsset),
		"Contributor should be able to remove their own assets",
	);
	permissionsTests.assert(
		!permissions.canRemoveAsset(otherAsset),
		"Contributor should not be able to remove others' assets",
	);
});

// Test 6: Co-owner asset permissions
permissionsTests.addTest("Co-owner asset ownership permissions", () => {
	const permissions = new PermissionsManager({
		userPermissionLevel: "co-owner",
		datasetUuid: "test-uuid",
		currentUserId: 7,
		isOwner: false,
		datasetPermissions: {},
	});

	const ownedAsset = { owner_id: 7, name: "test-asset" };
	const otherAsset = { owner_id: 8, name: "other-asset" };

	permissionsTests.assert(
		permissions.canAddAsset(ownedAsset),
		"Co-owner should be able to add their own assets",
	);
	permissionsTests.assert(
		permissions.canAddAsset(otherAsset),
		"Co-owner should be able to add others' assets",
	);
	permissionsTests.assert(
		permissions.canRemoveAsset(ownedAsset),
		"Co-owner should be able to remove their own assets",
	);
	permissionsTests.assert(
		permissions.canRemoveAsset(otherAsset),
		"Co-owner should be able to remove others' assets",
	);
});

// Test 7: Permission display names
permissionsTests.addTest("Permission display names", () => {
	permissionsTests.assertEqual(
		PermissionsManager.getPermissionDisplayName("owner"),
		"Owner",
	);
	permissionsTests.assertEqual(
		PermissionsManager.getPermissionDisplayName("co-owner"),
		"Co-Owner",
	);
	permissionsTests.assertEqual(
		PermissionsManager.getPermissionDisplayName("contributor"),
		"Contributor",
	);
	permissionsTests.assertEqual(
		PermissionsManager.getPermissionDisplayName("viewer"),
		"Viewer",
	);
});

// Test 8: Permission descriptions
permissionsTests.addTest("Permission descriptions", () => {
	const ownerDesc = PermissionsManager.getPermissionDescription("owner");
	const coOwnerDesc = PermissionsManager.getPermissionDescription("co-owner");
	const contributorDesc =
		PermissionsManager.getPermissionDescription("contributor");
	const viewerDesc = PermissionsManager.getPermissionDescription("viewer");

	permissionsTests.assert(
		ownerDesc.includes("Full control"),
		"Owner description should mention full control",
	);
	permissionsTests.assert(
		coOwnerDesc.includes("edit metadata"),
		"Co-owner description should mention editing metadata",
	);
	permissionsTests.assert(
		contributorDesc.includes("their own"),
		"Contributor description should mention their own assets",
	);
	permissionsTests.assert(
		viewerDesc.includes("only view"),
		"Viewer description should mention only viewing",
	);
});

// Test 9: Permission icons
permissionsTests.addTest("Permission icons", () => {
	permissionsTests.assertEqual(
		PermissionsManager.getPermissionIcon("owner"),
		"bi-crown",
	);
	permissionsTests.assertEqual(
		PermissionsManager.getPermissionIcon("co-owner"),
		"bi-gear",
	);
	permissionsTests.assertEqual(
		PermissionsManager.getPermissionIcon("contributor"),
		"bi-plus-circle",
	);
	permissionsTests.assertEqual(
		PermissionsManager.getPermissionIcon("viewer"),
		"bi-eye",
	);
});

// Test 10: Permission badge classes
permissionsTests.addTest("Permission badge classes", () => {
	permissionsTests.assertEqual(
		PermissionsManager.getPermissionBadgeClass("owner"),
		"bg-owner",
	);
	permissionsTests.assertEqual(
		PermissionsManager.getPermissionBadgeClass("co-owner"),
		"bg-co-owner",
	);
	permissionsTests.assertEqual(
		PermissionsManager.getPermissionBadgeClass("contributor"),
		"bg-contributor",
	);
	permissionsTests.assertEqual(
		PermissionsManager.getPermissionBadgeClass("viewer"),
		"bg-viewer",
	);
});

// Test 11: Permission hierarchy
permissionsTests.addTest("Permission hierarchy", () => {
	permissionsTests.assert(
		PermissionsManager.isHigherPermission("owner", "co-owner"),
		"Owner should be higher than co-owner",
	);
	permissionsTests.assert(
		PermissionsManager.isHigherPermission("co-owner", "contributor"),
		"Co-owner should be higher than contributor",
	);
	permissionsTests.assert(
		PermissionsManager.isHigherPermission("contributor", "viewer"),
		"Contributor should be higher than viewer",
	);
	permissionsTests.assert(
		!PermissionsManager.isHigherPermission("viewer", "contributor"),
		"Viewer should not be higher than contributor",
	);
});

// Test 12: Available permission levels
permissionsTests.addTest("Available permission levels", () => {
	const levels = PermissionsManager.getAvailablePermissionLevels();
	permissionsTests.assert(
		levels.length === 3,
		"Should have 3 available permission levels",
	);
	permissionsTests.assertContains(
		levels.map((l) => l.value),
		"viewer",
		"Should include viewer level",
	);
	permissionsTests.assertContains(
		levels.map((l) => l.value),
		"contributor",
		"Should include contributor level",
	);
	permissionsTests.assertContains(
		levels.map((l) => l.value),
		"co-owner",
		"Should include co-owner level",
	);
});

// Test 13: Permission summary
permissionsTests.addTest("Permission summary", () => {
	const permissions = new PermissionsManager({
		userPermissionLevel: "contributor",
		datasetUuid: "test-uuid",
		currentUserId: 9,
		isOwner: false,
		datasetPermissions: {},
	});

	const summary = permissions.getPermissionSummary();
	permissionsTests.assertEqual(summary.userPermissionLevel, "contributor");
	permissionsTests.assertEqual(summary.displayName, "Contributor");
	permissionsTests.assertEqual(summary.isEditMode, true);
	permissionsTests.assertEqual(summary.isOwner, false);
	permissionsTests.assert(
		!summary.permissions.canEditMetadata,
		"Summary should reflect canEditMetadata permission for contributor",
	);
	permissionsTests.assert(
		!summary.permissions.canShare,
		"Summary should reflect canShare permission for contributor",
	);
});

// Test 14: Update dataset permissions
permissionsTests.addTest("Update dataset permissions", () => {
	const permissions = new PermissionsManager({
		userPermissionLevel: "viewer",
		datasetUuid: "test-uuid",
		currentUserId: 12,
		isOwner: false,
		datasetPermissions: {},
	});

	// Initially should not be able to edit metadata
	permissionsTests.assert(
		!permissions.canEditMetadata(),
		"Initially should not be able to edit metadata",
	);

	// Update permissions
	permissions.updateDatasetPermissions({ canEditMetadata: true });

	// Now should be able to edit metadata
	permissionsTests.assert(
		permissions.canEditMetadata(),
		"Should be able to edit metadata after update",
	);
});

// Export for use in test runner
if (typeof module !== "undefined" && module.exports) {
	module.exports = permissionsTests;
} else {
	window.PermissionsManagerTests = permissionsTests;
}
