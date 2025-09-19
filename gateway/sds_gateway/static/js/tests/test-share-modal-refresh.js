/**
 * Test script to check shared users list before and after refreshItemList()
 * Run this in the browser console on a page with share modals
 */

class ShareModalRefreshTest {
	constructor() {
		this.testResults = [];
		this.beforeState = null;
		this.afterState = null;
	}

	/**
	 * Extract shared users from the "Users with Access" section
	 * @param {string} modalId - The modal ID to check
	 * @returns {Array} Array of user objects with their details
	 */
	extractSharedUsers(modalId) {
		const modal = document.getElementById(modalId);
		if (!modal) {
			console.warn(`Modal ${modalId} not found`);
			return [];
		}

		const usersWithAccessSection = modal.querySelector(
			`#users-with-access-section-${modalId.replace("share-modal-", "")}`,
		);
		if (!usersWithAccessSection) {
			console.warn(`Users with access section not found in modal ${modalId}`);
			return [];
		}

		const userRows = usersWithAccessSection.querySelectorAll("tbody tr");
		const users = [];

		for (const [index, row] of userRows.entries()) {
			const nameElement = row.querySelector("h5");
			const emailElement = row.querySelector("small.text-muted");
			const permissionElement = row.querySelector(
				".badge, .access-level-dropdown",
			);

			if (nameElement && emailElement) {
				const user = {
					index: index,
					name: nameElement.textContent.trim(),
					email: emailElement.textContent.trim(),
					permission: permissionElement
						? permissionElement.textContent.trim()
						: "Unknown",
					isOwner: index === 0, // First row is typically the owner
					type: nameElement.querySelector(".bi-people-fill") ? "group" : "user",
				};
				users.push(user);
			}
		}

		return users;
	}

	/**
	 * Get all share modals on the page
	 * @returns {Array} Array of modal elements
	 */
	getAllShareModals() {
		return document.querySelectorAll(".modal[data-item-uuid][data-item-type]");
	}

	/**
	 * Capture the current state of all share modals
	 * @returns {Object} State object with modal data
	 */
	captureCurrentState() {
		const modals = this.getAllShareModals();
		const state = {};

		for (const modal of modals) {
			const modalId = modal.id;
			const itemUuid = modal.getAttribute("data-item-uuid");
			const itemType = modal.getAttribute("data-item-type");

			state[modalId] = {
				itemUuid,
				itemType,
				sharedUsers: this.extractSharedUsers(modalId),
				timestamp: new Date().toISOString(),
			};
		}

		return state;
	}

	/**
	 * Compare two states and return differences
	 * @param {Object} before - Before state
	 * @param {Object} after - After state
	 * @returns {Object} Comparison results
	 */
	compareStates(before, after) {
		const comparison = {
			modalsChanged: [],
			usersAdded: [],
			usersRemoved: [],
			usersModified: [],
			unchanged: [],
		};

		// Check each modal
		for (const modalId of Object.keys(before)) {
			const beforeModal = before[modalId];
			const afterModal = after[modalId];

			if (!afterModal) {
				comparison.modalsChanged.push({
					modalId,
					change: "removed",
					before: beforeModal,
				});
				continue;
			}

			const beforeUsers = beforeModal.sharedUsers;
			const afterUsers = afterModal.sharedUsers;

			// Check for user changes
			const beforeUserMap = new Map(beforeUsers.map((u) => [u.email, u]));
			const afterUserMap = new Map(afterUsers.map((u) => [u.email, u]));

			// Find added users
			for (const afterUser of afterUsers) {
				if (!beforeUserMap.has(afterUser.email)) {
					comparison.usersAdded.push({
						modalId,
						user: afterUser,
					});
				}
			}

			// Find removed users
			for (const beforeUser of beforeUsers) {
				if (!afterUserMap.has(beforeUser.email)) {
					comparison.usersRemoved.push({
						modalId,
						user: beforeUser,
					});
				}
			}

			// Find modified users
			for (const beforeUser of beforeUsers) {
				const afterUser = afterUserMap.get(beforeUser.email);
				if (afterUser && this.hasUserChanged(beforeUser, afterUser)) {
					comparison.usersModified.push({
						modalId,
						before: beforeUser,
						after: afterUser,
					});
				}
			}

			// Check if modal is unchanged
			if (
				beforeUsers.length === afterUsers.length &&
				comparison.usersAdded.length === 0 &&
				comparison.usersRemoved.length === 0 &&
				comparison.usersModified.length === 0
			) {
				comparison.unchanged.push(modalId);
			}
		}

		return comparison;
	}

	/**
	 * Check if a user has changed between states
	 * @param {Object} before - Before user object
	 * @param {Object} after - After user object
	 * @returns {boolean} True if user has changed
	 */
	hasUserChanged(before, after) {
		return (
			before.name !== after.name ||
			before.permission !== after.permission ||
			before.type !== after.type
		);
	}

	/**
	 * Run the test by capturing state before and after refresh
	 * @param {string} itemType - Type of item to refresh ('dataset' or 'capture')
	 * @returns {Promise<Object>} Test results
	 */
	async runTest(itemType = "dataset") {
		console.log("🧪 Starting Share Modal Refresh Test...");

		// Capture initial state
		console.log("📸 Capturing initial state...");
		this.beforeState = this.captureCurrentState();
		console.log("Before state:", this.beforeState);

		// Find a ShareActionManager instance to call refreshItemList
		const shareManager = this.findShareActionManager(itemType);
		if (!shareManager) {
			throw new Error(`No ShareActionManager found for item type: ${itemType}`);
		}

		// Call refreshItemList
		console.log("🔄 Calling refreshItemList()...");
		try {
			await shareManager.refreshItemList();
			console.log("✅ refreshItemList() completed successfully");
		} catch (error) {
			console.error("❌ refreshItemList() failed:", error);
			throw error;
		}

		// Wait a moment for DOM updates
		await new Promise((resolve) => setTimeout(resolve, 1000));

		// Capture state after refresh
		console.log("📸 Capturing state after refresh...");
		this.afterState = this.captureCurrentState();
		console.log("After state:", this.afterState);

		// Compare states
		const comparison = this.compareStates(this.beforeState, this.afterState);

		// Log results
		this.logResults(comparison);

		return {
			before: this.beforeState,
			after: this.afterState,
			comparison,
		};
	}

	/**
	 * Find a ShareActionManager instance for the given item type
	 * @param {string} itemType - Item type to find
	 * @returns {ShareActionManager|null} ShareActionManager instance or null
	 */
	findShareActionManager(itemType) {
		// Look for modals with the specified item type
		const modals = document.querySelectorAll(
			`.modal[data-item-type="${itemType}"]`,
		);

		for (const modal of modals) {
			if (modal.shareActionManager) {
				return modal.shareActionManager;
			}
		}

		// If not found on modals, look for any ShareActionManager in the global scope
		if (window.ShareActionManager) {
			// This is a fallback - in practice, we'd need the actual instance
			console.warn(
				"Found ShareActionManager class but no instance. You may need to manually trigger refresh.",
			);
		}

		return null;
	}

	/**
	 * Log test results in a readable format
	 * @param {Object} comparison - Comparison results
	 */
	logResults(comparison) {
		console.log("\n📊 TEST RESULTS:");
		console.log("================");

		if (comparison.unchanged.length > 0) {
			console.log(`✅ Unchanged modals: ${comparison.unchanged.length}`);
			for (const modalId of comparison.unchanged) {
				console.log(`   - ${modalId}`);
			}
		}

		if (comparison.usersAdded.length > 0) {
			console.log(`➕ Users added: ${comparison.usersAdded.length}`);
			for (const change of comparison.usersAdded) {
				console.log(
					`   - ${change.modalId}: ${change.user.name} (${change.user.email})`,
				);
			}
		}

		if (comparison.usersRemoved.length > 0) {
			console.log(`➖ Users removed: ${comparison.usersRemoved.length}`);
			for (const change of comparison.usersRemoved) {
				console.log(
					`   - ${change.modalId}: ${change.user.name} (${change.user.email})`,
				);
			}
		}

		if (comparison.usersModified.length > 0) {
			console.log(`🔄 Users modified: ${comparison.usersModified.length}`);
			for (const change of comparison.usersModified) {
				console.log(
					`   - ${change.modalId}: ${change.before.name} (${change.before.email})`,
				);
				console.log(`     Before: ${change.before.permission}`);
				console.log(`     After:  ${change.after.permission}`);
			}
		}

		if (comparison.modalsChanged.length > 0) {
			console.log(`🔄 Modals changed: ${comparison.modalsChanged.length}`);
			for (const change of comparison.modalsChanged) {
				console.log(`   - ${change.modalId}: ${change.change}`);
			}
		}

		// Summary
		const totalChanges =
			comparison.usersAdded.length +
			comparison.usersRemoved.length +
			comparison.usersModified.length +
			comparison.modalsChanged.length;

		if (totalChanges === 0) {
			console.log(
				"\n🎉 No changes detected - shared users list is consistent!",
			);
		} else {
			console.log(`\n⚠️  ${totalChanges} changes detected in shared users list`);
		}
	}

	/**
	 * Quick test method for console usage
	 * @param {string} itemType - Item type to test
	 */
	async quickTest(itemType = "dataset") {
		try {
			const results = await this.runTest(itemType);
			return results;
		} catch (error) {
			console.error("Test failed:", error);
			return null;
		}
	}
}

// Make it available globally for console usage
window.ShareModalRefreshTest = ShareModalRefreshTest;

// Auto-run if in console
if (typeof window !== "undefined" && window.console) {
	console.log("🧪 Share Modal Refresh Test loaded!");
	console.log("Usage:");
	console.log("  const test = new ShareModalRefreshTest();");
	console.log('  await test.quickTest("dataset"); // or "capture"');
	console.log("");
	console.log("Or run directly:");
	console.log('  await new ShareModalRefreshTest().quickTest("dataset");');
}
