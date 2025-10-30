// PermissionLevels and window.getPermissionHierarchy are now available globally

/**
 * Centralized Permissions Manager
 * Handles all permission checking and user access control
 */
window.PermissionsManager = class PermissionsManager {
	/**
	 * Initialize permissions manager
	 * @param {Object} config - Configuration object
	 * @param {string} config.userPermissionLevel - User's permission level (viewer, contributor, co-owner, owner)
	 * @param {string|null} config.datasetUuid - Dataset UUID (null for create mode)
	 * @param {number} config.currentUserId - Current user ID
	 * @param {boolean} config.isOwner - Whether user is the owner
	 * @param {Object} config.datasetPermissions - Dataset-specific permissions
	 */
	constructor(config) {
		this.userPermissionLevel =
			config.userPermissionLevel || window.window.PermissionLevels.VIEWER;
		this.datasetUuid = config.datasetUuid;
		this.currentUserId = config.currentUserId;
		this.isOwner = config.isOwner || false;
		this.isEditMode = !!this.datasetUuid;

		// Dataset-specific permissions
		this.datasetPermissions = {
			canEditMetadata: config.datasetPermissions?.canEditMetadata || false,
			canAddAssets: config.datasetPermissions?.canAddAssets || false,
			canRemoveAssets: config.datasetPermissions?.canRemoveAssets || false,
			canShare: config.datasetPermissions?.canShare || false,
			canDownload: config.datasetPermissions?.canDownload || false,
			...config.datasetPermissions,
		};
	}

	/**
	 * Check if user can edit dataset metadata
	 * @returns {boolean}
	 */
	canEditMetadata() {
		if (
			this.isOwner ||
			this.userPermissionLevel === window.PermissionLevels.CO_OWNER
		)
			return true;
		return this.datasetPermissions.canEditMetadata;
	}

	/**
	 * Check if user can add assets to dataset
	 * @returns {boolean}
	 */
	canAddAssets() {
		if (
			this.isOwner ||
			[
				window.PermissionLevels.CO_OWNER,
				window.PermissionLevels.CONTRIBUTOR,
			].includes(this.userPermissionLevel)
		)
			return true;
		return this.datasetPermissions.canAddAssets || false;
	}

	/**
	 * Check if user can remove any assets from dataset
	 * @returns {boolean}
	 */
	canRemoveOwnAssets() {
		if (
			this.isOwner ||
			[
				window.PermissionLevels.CO_OWNER,
				window.PermissionLevels.CONTRIBUTOR,
			].includes(this.userPermissionLevel)
		)
			return true;
		return this.datasetPermissions.canRemoveOwnAssets || false;
	}

	/**
	 * Check if user can remove assets from dataset
	 * @returns {boolean}
	 */
	canRemoveAnyAssets() {
		if (
			this.isOwner ||
			this.userPermissionLevel === window.PermissionLevels.CO_OWNER
		)
			return true;
		return this.datasetPermissions.canRemoveAnyAssets;
	}

	/**
	 * Check if user can share dataset
	 * @returns {boolean}
	 */
	canShare() {
		if (
			this.isOwner ||
			this.userPermissionLevel === window.PermissionLevels.CO_OWNER
		)
			return true;
		return this.datasetPermissions.canShare;
	}

	/**
	 * Check if user can download dataset
	 * @returns {boolean}
	 */
	canDownload() {
		if (
			this.isOwner ||
			[
				window.PermissionLevels.CO_OWNER,
				window.PermissionLevels.CONTRIBUTOR,
				window.PermissionLevels.VIEWER,
			].includes(this.userPermissionLevel)
		)
			return true;
		return this.datasetPermissions.canDownload;
	}

	/**
	 * Check if user can view dataset
	 * @returns {boolean}
	 */
	canView() {
		return [
			window.PermissionLevels.OWNER,
			window.PermissionLevels.CO_OWNER,
			window.PermissionLevels.CONTRIBUTOR,
			window.PermissionLevels.VIEWER,
		].includes(this.userPermissionLevel);
	}

	/**
	 * Check if user can edit specific asset (capture/file)
	 * @param {Object} asset - Asset object
	 * @returns {boolean}
	 */
	canRemoveAsset(asset) {
		if (
			this.isOwner ||
			this.userPermissionLevel === window.PermissionLevels.CO_OWNER
		)
			return true;

		// Check if asset is owned by current user
		const isAssetOwner = asset.owner_id === this.currentUserId;

		// Contributors can edit their own assets
		if (
			this.userPermissionLevel === window.PermissionLevels.CONTRIBUTOR &&
			isAssetOwner
		)
			return true;

		return false;
	}

	/**
	 * Check if user can add specific asset (capture/file)
	 * @param {Object} asset - Asset object
	 * @returns {boolean}
	 */
	canAddAsset(asset) {
		if (
			this.isOwner ||
			this.userPermissionLevel === window.PermissionLevels.CO_OWNER
		)
			return true;

		// Check if asset is owned by current user
		const isAssetOwner = asset.owner_id === this.currentUserId;

		// Contributors can add their own assets
		if (
			this.userPermissionLevel === window.PermissionLevels.CONTRIBUTOR &&
			isAssetOwner
		) {
			return true;
		}

		return false;
	}

	/**
	 * Get the appropriate removal permission level for UI display
	 * @returns {string} 'any', 'own', or 'none'
	 */
	getRemovalPermissionLevel() {
		if (this.canRemoveAnyAssets()) {
			return "any";
		}
		if (this.canRemoveOwnAssets()) {
			return "own";
		}
		return "none";
	}

	/**
	 * Get permission level display name
	 * @param {string} level - Permission level
	 * @returns {string} Display name
	 */
	getPermissionDisplayName(level) {
		const displayNames = {
			[window.PermissionLevels.OWNER]: "Owner",
			[window.PermissionLevels.CO_OWNER]: "Co-Owner",
			[window.PermissionLevels.CONTRIBUTOR]: "Contributor",
			[window.PermissionLevels.VIEWER]: "Viewer",
		};
		return displayNames[level] || level;
	}

	/**
	 * Get permission level description
	 * @param {string} level - Permission level
	 * @returns {string} Description
	 */
	getPermissionDescription(level) {
		const descriptions = {
			[window.PermissionLevels.OWNER]:
				"Full control over the dataset including deletion and sharing",
			[window.PermissionLevels.CO_OWNER]:
				"Can edit metadata, add/remove assets, and share the dataset",
			[window.PermissionLevels.CONTRIBUTOR]:
				"Can add and remove their own assets and view others' additions",
			[window.PermissionLevels.VIEWER]:
				"Can only view and download the dataset",
		};
		return descriptions[level] || "Unknown permission level";
	}

	/**
	 * Get permission level icon class
	 * @param {string} level - Permission level
	 * @returns {string} Icon class
	 */
	getPermissionIcon(level) {
		const icons = {
			[window.PermissionLevels.OWNER]: "bi-person-circle",
			[window.PermissionLevels.CO_OWNER]: "bi-gear",
			[window.PermissionLevels.CONTRIBUTOR]: "bi-plus-circle",
			[window.PermissionLevels.VIEWER]: "bi-eye",
			remove: "bi-person-slash",
		};
		return icons[level] || "bi-question-circle";
	}

	/**
	 * Get permission level badge class
	 * @param {string} level - Permission level
	 * @returns {string} Badge class
	 */
	getPermissionBadgeClass(level) {
		const badgeClasses = {
			[window.PermissionLevels.OWNER]: "bg-owner",
			[window.PermissionLevels.CO_OWNER]: "bg-co-owner",
			[window.PermissionLevels.CONTRIBUTOR]: "bg-contributor",
			[window.PermissionLevels.VIEWER]: "bg-viewer",
		};
		return badgeClasses[level] || "bg-light";
	}

	/**
	 * Check if permission level is higher than another
	 * @param {string} level1 - First permission level
	 * @param {string} level2 - Second permission level
	 * @returns {boolean} True if level1 is higher than level2
	 */
	static isHigherPermission(level1, level2) {
		return (
			window.getPermissionHierarchy(level1) >
			window.getPermissionHierarchy(level2)
		);
	}

	/**
	 * Get permission summary for display
	 * @returns {Object} Permission summary
	 */
	getPermissionSummary() {
		return {
			userPermissionLevel: this.userPermissionLevel,
			displayName: this.getPermissionDisplayName(this.userPermissionLevel),
			description: this.getPermissionDescription(this.userPermissionLevel),
			icon: this.getPermissionIcon(this.userPermissionLevel),
			badgeClass: this.getPermissionBadgeClass(this.userPermissionLevel),
			isEditMode: this.isEditMode,
			isOwner: this.isOwner,
			permissions: {
				canEditMetadata: this.canEditMetadata(),
				canAddAssets: this.canAddAssets(),
				canRemoveAnyAssets: this.canRemoveAnyAssets(),
				canRemoveOwnAssets: this.canRemoveOwnAssets(),
				removalPermissionLevel: this.getRemovalPermissionLevel(),
				canShare: this.canShare(),
				canDownload: this.canDownload(),
				canView: this.canView(),
			},
		};
	}

	/**
	 * Update dataset permissions
	 * @param {Object} newPermissions - New permissions object
	 */
	updateDatasetPermissions(newPermissions) {
		this.datasetPermissions = {
			...this.datasetPermissions,
			...newPermissions,
		};
	}

	/**
	 * Check if user has any of the specified permissions
	 * @param {Array} permissionNames - Array of permission names to check
	 * @returns {boolean} True if user has any of the permissions
	 */
	hasAnyPermission(permissionNames) {
		return permissionNames.some((permission) => {
			if (typeof this[permission] === "function") {
				return this[permission]();
			}
			return this.datasetPermissions[permission] || false;
		});
	}

	/**
	 * Check if user has all of the specified permissions
	 * @param {Array} permissionNames - Array of permission names to check
	 * @returns {boolean} True if user has all of the permissions
	 */
	hasAllPermissions(permissionNames) {
		return permissionNames.every((permission) => {
			if (typeof this[permission] === "function") {
				return this[permission]();
			}
			return this.datasetPermissions[permission] || false;
		});
	}
};

// Make class available globally
window.PermissionsManager = PermissionsManager;

// Export for ES6 modules (Jest testing) - only if in module context
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { PermissionsManager };
}
