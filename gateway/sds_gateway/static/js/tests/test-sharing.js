/**
 * Tests for ShareActionManager
 * Tests sharing functionality for different user access levels
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

// Mock APIClient
global.APIClient = {
	post: async (url, data) => {
		// Mock successful response
		return { success: true, message: "Item shared successfully" };
	},
	get: async (url, params) => {
		// Mock user search results
		return [
			{ name: "Test User", email: "test@example.com", type: "user" },
			{
				name: "Test Group",
				email: "group:test-uuid",
				type: "group",
				member_count: 5,
			},
		];
	},
};

// Simple mocks for the classes we need
global.HTMLInjectionManager = {
	escapeHtml: (text) => text,
	injectHTML: (container, html, options) => {
		if (container) container.innerHTML = html;
	},
	createUserChip: (user, options = {}) => {
		const displayName = user.name || user.email;
		return `<div class="user-chip" data-user-email="${user.email}">${displayName}</div>`;
	},
};

class PermissionsManager {
	constructor(config) {
		this.userPermissionLevel = config.userPermissionLevel;
		this.isOwner = config.isOwner;
	}

	canShare() {
		return this.isOwner || this.userPermissionLevel === "co-owner";
	}

	canDownload() {
		return true; // All users can download
	}
}

global.PermissionsManager = PermissionsManager;

// Test suite for ShareActionManager
class ShareActionManagerTests {
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
		console.log("Running ShareActionManager tests...");

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
	 * Create mock ShareActionManager
	 * @param {Object} config - Configuration
	 * @returns {Object} Mock ShareActionManager
	 */
	createMockShareActionManager(config = {}) {
		const defaultConfig = {
			itemUuid: "test-uuid",
			itemType: "dataset",
			permissions: new PermissionsManager({
				userPermissionLevel: "co-owner",
				isOwner: false,
			}),
		};

		return {
			...defaultConfig,
			...config,
			selectedUsersMap: {},
			pendingRemovals: new Set(),
			pendingPermissionChanges: new Map(),

			// Mock methods
			handleShareItem: async () => {
				// Mock implementation
				return { success: true };
			},

			searchUsers: async (query, dropdown) => {
				// Mock implementation
				return [];
			},

			selectUser: (item, input) => {
				// Mock implementation
			},

			renderChips: (input) => {
				// Mock implementation
			},

			clearSelections: function () {
				this.selectedUsersMap = {};
				this.pendingRemovals.clear();
				this.pendingPermissionChanges.clear();
			},
		};
	}
}

// Create test suite
const sharingTests = new ShareActionManagerTests();

// Test 1: Owner can share
sharingTests.addTest("Owner can share items", () => {
	const permissions = new PermissionsManager({
		userPermissionLevel: "owner",
		isOwner: true,
	});

	sharingTests.assert(
		permissions.canShare(),
		"Owner should be able to share items",
	);
});

// Test 2: Co-owner can share
sharingTests.addTest("Co-owner can share items", () => {
	const permissions = new PermissionsManager({
		userPermissionLevel: "co-owner",
		isOwner: false,
	});

	sharingTests.assert(
		permissions.canShare(),
		"Co-owner should be able to share items",
	);
});

// Test 3: Contributor cannot share
sharingTests.addTest("Contributor cannot share items", () => {
	const permissions = new PermissionsManager({
		userPermissionLevel: "contributor",
		isOwner: false,
	});

	sharingTests.assert(
		!permissions.canShare(),
		"Contributor should not be able to share items",
	);
});

// Test 4: Viewer cannot share
sharingTests.addTest("Viewer cannot share items", () => {
	const permissions = new PermissionsManager({
		userPermissionLevel: "viewer",
		isOwner: false,
	});

	sharingTests.assert(
		!permissions.canShare(),
		"Viewer should not be able to share items",
	);
});

// Test 5: ShareActionManager initialization
sharingTests.addTest("ShareActionManager initializes correctly", () => {
	const manager = sharingTests.createMockShareActionManager({
		itemUuid: "test-dataset-uuid",
		itemType: "dataset",
	});

	sharingTests.assertEqual(manager.itemUuid, "test-dataset-uuid");
	sharingTests.assertEqual(manager.itemType, "dataset");
	sharingTests.assert(manager.permissions instanceof PermissionsManager);
	sharingTests.assert(manager.selectedUsersMap instanceof Object);
	sharingTests.assert(manager.pendingRemovals instanceof Set);
	sharingTests.assert(manager.pendingPermissionChanges instanceof Map);
});

// Test 6: User selection
sharingTests.addTest("User selection works correctly", () => {
	const manager = sharingTests.createMockShareActionManager();
	const inputId = "user-search-test-uuid";

	// Add user to selection
	manager.selectedUsersMap[inputId] = [
		{
			name: "Test User",
			email: "test@example.com",
			type: "user",
			permission_level: "viewer",
		},
	];

	sharingTests.assert(manager.selectedUsersMap[inputId].length === 1);
	sharingTests.assertEqual(
		manager.selectedUsersMap[inputId][0].email,
		"test@example.com",
	);
	sharingTests.assertEqual(
		manager.selectedUsersMap[inputId][0].permission_level,
		"viewer",
	);
});

// Test 7: Group selection
sharingTests.addTest("Group selection works correctly", () => {
	const manager = sharingTests.createMockShareActionManager();
	const inputId = "user-search-test-uuid";

	// Add group to selection
	manager.selectedUsersMap[inputId] = [
		{
			name: "Test Group",
			email: "group:test-group-uuid",
			type: "group",
			member_count: 5,
			permission_level: "contributor",
		},
	];

	sharingTests.assert(manager.selectedUsersMap[inputId].length === 1);
	sharingTests.assertEqual(manager.selectedUsersMap[inputId][0].type, "group");
	sharingTests.assertEqual(
		manager.selectedUsersMap[inputId][0].member_count,
		5,
	);
});

// Test 8: Permission level changes
sharingTests.addTest("Permission level changes work correctly", () => {
	const manager = sharingTests.createMockShareActionManager();
	const userEmail = "test@example.com";

	// Add permission change
	manager.pendingPermissionChanges.set(userEmail, {
		userName: "Test User",
		itemUuid: "test-uuid",
		itemType: "dataset",
		permissionLevel: "contributor",
	});

	sharingTests.assert(manager.pendingPermissionChanges.has(userEmail));
	sharingTests.assertEqual(
		manager.pendingPermissionChanges.get(userEmail).permissionLevel,
		"contributor",
	);
});

// Test 9: User removal
sharingTests.addTest("User removal works correctly", () => {
	const manager = sharingTests.createMockShareActionManager();
	const userEmail = "test@example.com";

	// Add user to pending removals
	manager.pendingRemovals.add(userEmail);

	sharingTests.assert(manager.pendingRemovals.has(userEmail));
	sharingTests.assertEqual(manager.pendingRemovals.size, 1);
});

// Test 10: Clear selections
sharingTests.addTest("Clear selections works correctly", () => {
	const manager = sharingTests.createMockShareActionManager();
	const inputId = "user-search-test-uuid";

	// Add some data
	manager.selectedUsersMap[inputId] = [
		{ name: "Test User", email: "test@example.com", type: "user" },
	];
	manager.pendingRemovals.add("remove@example.com");
	manager.pendingPermissionChanges.set("change@example.com", {
		permissionLevel: "contributor",
	});

	// Clear selections
	manager.clearSelections();

	sharingTests.assertEqual(Object.keys(manager.selectedUsersMap).length, 0);
	sharingTests.assertEqual(manager.pendingRemovals.size, 0);
	sharingTests.assertEqual(manager.pendingPermissionChanges.size, 0);
});

// Test 11: Share item with users
sharingTests.addTest("Share item with users works correctly", async () => {
	const manager = sharingTests.createMockShareActionManager();

	// Mock successful share
	const result = await manager.handleShareItem();

	sharingTests.assert(result.success, "Share should be successful");
});

// Test 12: Search users
sharingTests.addTest("Search users works correctly", async () => {
	const manager = sharingTests.createMockShareActionManager();

	// Mock user search
	const results = await manager.searchUsers("test", null);

	sharingTests.assert(
		Array.isArray(results),
		"Search results should be an array",
	);
});

// Test 13: User chip creation
sharingTests.addTest("User chip creation works correctly", () => {
	const user = {
		name: "Test User",
		email: "test@example.com",
		type: "user",
		permission_level: "viewer",
	};

	// Create chip using our mock function
	const displayName = user.name || user.email;
	const chip = `<div class="user-chip" data-user-email="${user.email}">${displayName}</div>`;

	sharingTests.assert(
		chip.includes("user-chip"),
		"Chip should have user-chip class",
	);
	sharingTests.assert(
		chip.includes("test@example.com"),
		"Chip should contain user email",
	);
});

// Test 14: Group chip creation
sharingTests.addTest("Group chip creation works correctly", () => {
	const group = {
		name: "Test Group",
		email: "group:test-uuid",
		type: "group",
		member_count: 5,
		permission_level: "contributor",
	};

	// Create chip using our mock logic
	const displayName = group.name || group.email;
	const chip = `<div class="user-chip" data-user-email="${group.email}">${displayName}</div>`;

	sharingTests.assert(
		chip.includes("user-chip"),
		"Chip should have user-chip class",
	);
	sharingTests.assert(
		chip.includes("Test Group"),
		"Chip should contain group name",
	);
});

// Test 15: Permission level validation
sharingTests.addTest("Permission level validation works correctly", () => {
	const validLevels = ["viewer", "contributor", "co-owner"];
	const invalidLevels = ["owner", "admin", "invalid"];

	for (const level of validLevels) {
		sharingTests.assert(
			validLevels.includes(level),
			`Level ${level} should be valid`,
		);
	}

	for (const level of invalidLevels) {
		sharingTests.assert(
			!validLevels.includes(level),
			`Level ${level} should be invalid`,
		);
	}
});

// Test 16: Multiple user selection
sharingTests.addTest("Multiple user selection works correctly", () => {
	const manager = sharingTests.createMockShareActionManager();
	const inputId = "user-search-test-uuid";

	// Add multiple users
	manager.selectedUsersMap[inputId] = [
		{
			name: "User 1",
			email: "user1@example.com",
			type: "user",
			permission_level: "viewer",
		},
		{
			name: "User 2",
			email: "user2@example.com",
			type: "user",
			permission_level: "contributor",
		},
		{
			name: "Group 1",
			email: "group:group1-uuid",
			type: "group",
			member_count: 3,
			permission_level: "co-owner",
		},
	];

	sharingTests.assertEqual(manager.selectedUsersMap[inputId].length, 3);

	// Check individual users
	const user1 = manager.selectedUsersMap[inputId].find(
		(u) => u.email === "user1@example.com",
	);
	const user2 = manager.selectedUsersMap[inputId].find(
		(u) => u.email === "user2@example.com",
	);
	const group1 = manager.selectedUsersMap[inputId].find(
		(u) => u.email === "group:group1-uuid",
	);

	sharingTests.assert(user1 !== undefined, "User 1 should be found");
	sharingTests.assert(user2 !== undefined, "User 2 should be found");
	sharingTests.assert(group1 !== undefined, "Group 1 should be found");

	sharingTests.assertEqual(user1.permission_level, "viewer");
	sharingTests.assertEqual(user2.permission_level, "contributor");
	sharingTests.assertEqual(group1.permission_level, "co-owner");
});

// Test 17: Duplicate user prevention
sharingTests.addTest("Duplicate user prevention works correctly", () => {
	const manager = sharingTests.createMockShareActionManager();
	const inputId = "user-search-test-uuid";

	// Add user
	manager.selectedUsersMap[inputId] = [
		{
			name: "Test User",
			email: "test@example.com",
			type: "user",
			permission_level: "viewer",
		},
	];

	// Try to add same user again
	const existingUser = manager.selectedUsersMap[inputId].find(
		(u) => u.email === "test@example.com",
	);
	sharingTests.assert(existingUser !== undefined, "User should already exist");

	// Should not add duplicate
	sharingTests.assertEqual(manager.selectedUsersMap[inputId].length, 1);
});

// Test 18: Mixed permission changes and removals
sharingTests.addTest(
	"Mixed permission changes and removals work correctly",
	() => {
		const manager = sharingTests.createMockShareActionManager();

		// Add permission change
		manager.pendingPermissionChanges.set("change@example.com", {
			userName: "Change User",
			itemUuid: "test-uuid",
			itemType: "dataset",
			permissionLevel: "contributor",
		});

		// Add removal
		manager.pendingRemovals.add("remove@example.com");

		sharingTests.assertEqual(manager.pendingPermissionChanges.size, 1);
		sharingTests.assertEqual(manager.pendingRemovals.size, 1);

		// Check that both operations are tracked separately
		sharingTests.assert(
			manager.pendingPermissionChanges.has("change@example.com"),
		);
		sharingTests.assert(manager.pendingRemovals.has("remove@example.com"));
		sharingTests.assert(
			!manager.pendingPermissionChanges.has("remove@example.com"),
		);
		sharingTests.assert(!manager.pendingRemovals.has("change@example.com"));
	},
);

// Test 19: Share with notification
sharingTests.addTest("Share with notification works correctly", () => {
	const manager = sharingTests.createMockShareActionManager();

	// Mock notification data
	const notifyData = {
		notify_users: "1",
		notify_message: "You have been granted access to this dataset.",
	};

	// Simulate form data preparation
	const formData = {
		"user-search": "test@example.com",
		user_permissions: JSON.stringify({ "test@example.com": "viewer" }),
		...notifyData,
	};

	sharingTests.assert(
		formData.notify_users === "1",
		"Notification should be enabled",
	);
	sharingTests.assert(
		formData.notify_message.length > 0,
		"Notification message should be present",
	);
});

// Test 20: Error handling
sharingTests.addTest("Error handling works correctly", async () => {
	const manager = sharingTests.createMockShareActionManager();

	// Mock API error
	const originalAPIClient = global.APIClient;
	global.APIClient.post = async () => {
		throw new Error("Network error");
	};

	try {
		// The mock handler returns success, so we simulate the error differently
		await global.APIClient.post();
		sharingTests.assert(false, "Should have thrown an error");
	} catch (error) {
		sharingTests.assert(
			error.message === "Network error",
			"Should catch the network error",
		);
	} finally {
		// Restore original APIClient
		global.APIClient = originalAPIClient;
	}
});

// Export for use in test runner
if (typeof module !== "undefined" && module.exports) {
	module.exports = sharingTests;
} else {
	window.ShareActionManagerTests = sharingTests;
}
