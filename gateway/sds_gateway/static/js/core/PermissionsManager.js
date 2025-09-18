/**
 * Centralized Permissions Manager
 * Handles all permission checking and user access control
 */
class PermissionsManager {
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
		this.userPermissionLevel = config.userPermissionLevel || "viewer";
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
			canDelete: config.datasetPermissions?.canDelete || false,
			...config.datasetPermissions,
		};
	}

	/**
	 * Check if user can edit dataset metadata
	 * @returns {boolean}
	 */
	canEditMetadata() {
		if (this.isOwner || this.userPermissionLevel === "co-owner") return true;
		return this.datasetPermissions.canEditMetadata;
	}

	/**
	 * Check if user can add assets to dataset
	 * @returns {boolean}
	 */
	canAddAssets() {
		if (
			this.isOwner ||
			["co-owner", "contributor"].includes(this.userPermissionLevel)
		)
			return true;
		return this.datasetPermissions.canAddAssets;
	}

	/**
	 * Check if user can remove any assets from dataset
	 * @returns {boolean}
	 */
	canRemoveOwnAssets() {
		if (
			this.isOwner ||
			["co-owner", "contributor"].includes(this.userPermissionLevel)
		)
			return true;
		return this.datasetPermissions.canRemoveOwnAssets;
	}

	/**
	 * Check if user can remove assets from dataset
	 * @returns {boolean}
	 */
	canRemoveAnyAssets() {
		if (this.isOwner || this.userPermissionLevel === "co-owner") return true;
		return this.datasetPermissions.canRemoveAnyAssets;
	}

	/**
	 * Check if user can share dataset
	 * @returns {boolean}
	 */
	canShare() {
		if (this.isOwner || this.userPermissionLevel === "co-owner") return true;
		return this.datasetPermissions.canShare;
	}

	/**
	 * Check if user can download dataset
	 * @returns {boolean}
	 */
	canDownload() {
		if (
			this.isOwner ||
			["co-owner", "contributor", "viewer"].includes(this.userPermissionLevel)
		)
			return true;
		return this.datasetPermissions.canDownload;
	}

	/**
	 * Check if user can delete dataset
	 * @returns {boolean}
	 */
	canDelete() {
		if (this.isOwner || this.userPermissionLevel === "co-owner") return true;
		return this.datasetPermissions.canDelete;
	}

	/**
	 * Check if user can view dataset
	 * @returns {boolean}
	 */
	canView() {
		return ["owner", "co-owner", "contributor", "viewer"].includes(
			this.userPermissionLevel,
		);
	}

	/**
	 * Check if user can edit specific asset (capture/file)
	 * @param {Object} asset - Asset object
	 * @returns {boolean}
	 */
	canRemoveAsset(asset) {
		if (this.isOwner || this.userPermissionLevel === "co-owner") return true;

		// Check if asset is owned by current user
		const isAssetOwner = asset.owner_id === this.currentUserId;

		// Contributors can edit their own assets
		if (this.userPermissionLevel === "contributor" && isAssetOwner) return true;

		return false;
	}

	/**
	 * Check if user can add specific asset (capture/file)
	 * @param {Object} asset - Asset object
	 * @returns {boolean}
	 */
	canAddAsset(asset) {
		if (this.isOwner || this.userPermissionLevel === "co-owner") return true;

		// Check if asset is owned by current user
		const isAssetOwner = asset.owner_id === this.currentUserId;

		// Contributors can add their own assets
		if (this.userPermissionLevel === "contributor" && isAssetOwner) {
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
	static getPermissionDisplayName(level) {
		const displayNames = {
			owner: "Owner",
			"co-owner": "Co-Owner",
			contributor: "Contributor",
			viewer: "Viewer",
		};
		return displayNames[level] || level;
	}

	/**
	 * Get permission level description
	 * @param {string} level - Permission level
	 * @returns {string} Description
	 */
	static getPermissionDescription(level) {
		const descriptions = {
			owner: "Full control over the dataset including deletion and sharing",
			"co-owner": "Can edit metadata, add/remove assets, and share the dataset",
			contributor:
				"Can add and remove their own assets and view others' additions",
			viewer: "Can only view and download the dataset",
		};
		return descriptions[level] || "Unknown permission level";
	}

	/**
	 * Get permission level icon class
	 * @param {string} level - Permission level
	 * @returns {string} Icon class
	 */
	static getPermissionIcon(level) {
		const icons = {
			owner: "bi-crown",
			"co-owner": "bi-gear",
			contributor: "bi-plus-circle",
			viewer: "bi-eye",
			remove: "bi-person-slash",
		};
		return icons[level] || "bi-question-circle";
	}

	/**
	 * Get permission level badge class
	 * @param {string} level - Permission level
	 * @returns {string} Badge class
	 */
	static getPermissionBadgeClass(level) {
		const badgeClasses = {
			owner: "bg-owner",
			"co-owner": "bg-co-owner",
			contributor: "bg-contributor",
			viewer: "bg-viewer",
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
		const hierarchy = {
			owner: 4,
			"co-owner": 3,
			contributor: 2,
			viewer: 1,
		};

		return (hierarchy[level1] || 0) > (hierarchy[level2] || 0);
	}

	/**
	 * Get all available permission levels
	 * @returns {Array} Array of permission level objects
	 */
	static getAvailablePermissionLevels() {
		return [
			{
				value: "viewer",
				label: "Viewer",
				description: PermissionsManager.getPermissionDescription("viewer"),
				icon: PermissionsManager.getPermissionIcon("viewer"),
				badgeClass: PermissionsManager.getPermissionBadgeClass("viewer"),
			},
			{
				value: "contributor",
				label: "Contributor",
				description: PermissionsManager.getPermissionDescription("contributor"),
				icon: PermissionsManager.getPermissionIcon("contributor"),
				badgeClass: PermissionsManager.getPermissionBadgeClass("contributor"),
			},
			{
				value: "co-owner",
				label: "Co-Owner",
				description: PermissionsManager.getPermissionDescription("co-owner"),
				icon: PermissionsManager.getPermissionIcon("co-owner"),
				badgeClass: PermissionsManager.getPermissionBadgeClass("co-owner"),
			},
		];
	}

	/**
	 * Get permission summary for display
	 * @returns {Object} Permission summary
	 */
	getPermissionSummary() {
		return {
			userPermissionLevel: this.userPermissionLevel,
			displayName: PermissionsManager.getPermissionDisplayName(
				this.userPermissionLevel,
			),
			description: PermissionsManager.getPermissionDescription(
				this.userPermissionLevel,
			),
			icon: PermissionsManager.getPermissionIcon(this.userPermissionLevel),
			badgeClass: PermissionsManager.getPermissionBadgeClass(
				this.userPermissionLevel,
			),
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
				canDelete: this.canDelete(),
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
}

// Make class available globally
window.PermissionsManager = PermissionsManager;
