/**
 * Permission level constants that match the Python PermissionLevel enum.
 * These should be kept in sync with the backend enum values.
 */
window.PermissionLevels = {
	OWNER: "owner",
	CO_OWNER: "co-owner",
	CONTRIBUTOR: "contributor",
	VIEWER: "viewer",
};

/**
 * Array of all permission levels in order of hierarchy (highest to lowest)
 */
window.PERMISSION_OPTIONS = [
	window.PermissionLevels.OWNER,
	window.PermissionLevels.CO_OWNER,
	window.PermissionLevels.CONTRIBUTOR,
	window.PermissionLevels.VIEWER,
];

/**
 * Check if a permission level is valid
 * @param {string} level - The permission level to validate
 * @returns {boolean} - True if valid, false otherwise
 */
window.isValidPermissionLevel = (level) =>
	Object.values(window.PermissionLevels).includes(level);
