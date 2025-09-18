/**
 * Simple utility to check shared users in share modals
 * Run this in the browser console to inspect current state
 */

// Function to get shared users from a specific modal
function getSharedUsers(modalId) {
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
				isOwner: index === 0,
				type: nameElement.querySelector(".bi-people-fill") ? "group" : "user",
				element: row,
			};
			users.push(user);
		}
	}

	return users;
}

// Function to get all share modals and their shared users
function getAllSharedUsers() {
	const modals = document.querySelectorAll(
		".modal[data-item-uuid][data-item-type]",
	);
	const result = {};

	for (const modal of modals) {
		const modalId = modal.id;
		const itemUuid = modal.getAttribute("data-item-uuid");
		const itemType = modal.getAttribute("data-item-type");

		result[modalId] = {
			itemUuid,
			itemType,
			sharedUsers: getSharedUsers(modalId),
		};
	}

	return result;
}

// Function to compare two states
function compareSharedUsers(before, after) {
	const changes = {
		added: [],
		removed: [],
		modified: [],
		unchanged: [],
	};

	for (const modalId of Object.keys(before)) {
		const beforeModal = before[modalId];
		const afterModal = after[modalId];

		if (!afterModal) {
			changes.removed.push({ modalId, users: beforeModal.sharedUsers });
			return;
		}

		const beforeUsers = beforeModal.sharedUsers;
		const afterUsers = afterModal.sharedUsers;

		// Create maps for easier comparison
		const beforeMap = new Map(beforeUsers.map((u) => [u.email, u]));
		const afterMap = new Map(afterUsers.map((u) => [u.email, u]));

		// Check for added users
		for (const afterUser of afterUsers) {
			if (!beforeMap.has(afterUser.email)) {
				changes.added.push({ modalId, user: afterUser });
			}
		}

		// Check for removed users
		for (const beforeUser of beforeUsers) {
			if (!afterMap.has(beforeUser.email)) {
				changes.removed.push({ modalId, user: beforeUser });
			}
		}

		// Check for modified users
		for (const beforeUser of beforeUsers) {
			const afterUser = afterMap.get(beforeUser.email);
			if (afterUser && hasUserChanged(beforeUser, afterUser)) {
				changes.modified.push({
					modalId,
					before: beforeUser,
					after: afterUser,
				});
			}
		}

		// Check if unchanged
		if (
			beforeUsers.length === afterUsers.length &&
			changes.added.length === 0 &&
			changes.removed.length === 0 &&
			changes.modified.length === 0
		) {
			changes.unchanged.push(modalId);
		}
	}

	return changes;
}

function hasUserChanged(before, after) {
	return (
		before.name !== after.name ||
		before.permission !== after.permission ||
		before.type !== after.type
	);
}

// Function to log results nicely
function logSharedUsers(users, title = "Shared Users") {
	console.log(`\n📋 ${title}:`);
	console.log("================");

	for (const modalId of Object.keys(users)) {
		const modal = users[modalId];
		console.log(`\n${modalId} (${modal.itemType}):`);
		console.log(`  Item UUID: ${modal.itemUuid}`);
		console.log(`  Users (${modal.sharedUsers.length}):`);

		for (const [index, user] of modal.sharedUsers.entries()) {
			const icon = user.isOwner ? "👑" : user.type === "group" ? "👥" : "👤";
			console.log(
				`    ${index + 1}. ${icon} ${user.name} (${user.email}) - ${user.permission}`,
			);
		}
	}
}

// Function to log changes
function logChanges(changes) {
	console.log("\n🔄 Changes Detected:");
	console.log("===================");

	if (changes.unchanged.length > 0) {
		console.log(`✅ Unchanged modals: ${changes.unchanged.length}`);
		for (const modalId of changes.unchanged) {
			console.log(`   - ${modalId}`);
		}
	}

	if (changes.added.length > 0) {
		console.log(`➕ Users added: ${changes.added.length}`);
		for (const change of changes.added) {
			console.log(
				`   - ${change.modalId}: ${change.user.name} (${change.user.email})`,
			);
		}
	}

	if (changes.removed.length > 0) {
		console.log(`➖ Users removed: ${changes.removed.length}`);
		for (const change of changes.removed) {
			console.log(
				`   - ${change.modalId}: ${change.user.name} (${change.user.email})`,
			);
		}
	}

	if (changes.modified.length > 0) {
		console.log(`🔄 Users modified: ${changes.modified.length}`);
		for (const change of changes.modified) {
			console.log(
				`   - ${change.modalId}: ${change.before.name} (${change.before.email})`,
			);
			console.log(`     Before: ${change.before.permission}`);
			console.log(`     After:  ${change.after.permission}`);
		}
	}
}

// Make functions available globally
window.getSharedUsers = getSharedUsers;
window.getAllSharedUsers = getAllSharedUsers;
window.compareSharedUsers = compareSharedUsers;
window.logSharedUsers = logSharedUsers;
window.logChanges = logChanges;

// Quick test function
window.testShareModalRefresh = async (itemType = "dataset") => {
	console.log("🧪 Testing Share Modal Refresh...");

	// Capture before state
	console.log("📸 Capturing before state...");
	const before = getAllSharedUsers();
	logSharedUsers(before, "BEFORE refreshItemList()");

	// Find and call refreshItemList
	const modals = document.querySelectorAll(
		`.modal[data-item-type="${itemType}"]`,
	);
	let shareManager = null;

	for (const modal of modals) {
		if (modal.shareActionManager) {
			shareManager = modal.shareActionManager;
			break;
		}
	}

	if (!shareManager) {
		console.error(
			"❌ No ShareActionManager found. Make sure a share modal is loaded.",
		);
		return;
	}

	// Call refresh
	console.log("🔄 Calling refreshItemList()...");
	try {
		await shareManager.refreshItemList();
		console.log("✅ refreshItemList() completed");
	} catch (error) {
		console.error("❌ refreshItemList() failed:", error);
		return;
	}

	// Wait for DOM updates
	await new Promise((resolve) => setTimeout(resolve, 1000));

	// Capture after state
	console.log("📸 Capturing after state...");
	const after = getAllSharedUsers();
	logSharedUsers(after, "AFTER refreshItemList()");

	// Compare and log changes
	const changes = compareSharedUsers(before, after);
	logChanges(changes);

	return { before, after, changes };
};

console.log("🔧 Shared Users Checker loaded!");
console.log("Usage:");
console.log("  getAllSharedUsers() - Get all shared users from all modals");
console.log(
	'  getSharedUsers("share-modal-uuid") - Get users from specific modal',
);
console.log('  testShareModalRefresh("dataset") - Run full test');
console.log("  logSharedUsers(users) - Pretty print user data");
