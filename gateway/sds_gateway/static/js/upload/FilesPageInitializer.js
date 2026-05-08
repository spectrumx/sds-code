/** Files page modal/table bootstrap. Migrated from deprecated/files-ui.js */
class FilesPageInitializer {
	constructor() {
		this.boundHandlers = new Map(); // Track event handlers for cleanup
		this.activeHandlers = new Set(); // Track active component handlers
		this.initializeComponents();
	}

	initializeComponents() {
		try {
			this.initializeModalManager();
			this.initializeCapturesTableManager();
			this.initializeUserSearchHandlers();
		} catch (error) {
			ErrorHandler.showError(
				"Failed to initialize page components",
				"component-initialization",
				error,
			);
		}
	}

	initializeModalManager() {
		// Initialize ModalManager for capture modal
		let modalManager = null;
		try {
			if (window.ModalManager) {
				modalManager = new window.ModalManager({
					modalId: "capture-modal",
					modalBodyId: "capture-modal-body",
					modalTitleId: "capture-modal-label",
				});

				this.modalManager = modalManager;
				console.log("ModalManager initialized successfully");
			} else {
				ErrorHandler.showError(
					"Modal functionality is not available. Some features may be limited.",
					"modal-initialization",
				);
			}
		} catch (error) {
			ErrorHandler.showError(
				"Failed to initialize modal functionality",
				"modal-initialization",
				error,
			);
		}
	}

	initializeCapturesTableManager() {
		// Initialize CapturesTableManager for capture edit/download functionality
		try {
			if (window.CapturesTableManager) {
				window.capturesTableManager = new window.CapturesTableManager({
					modalHandler: this.modalManager,
				});
				console.log("CapturesTableManager initialized successfully");
			} else {
				ErrorHandler.showError(
					"Table management functionality is not available. Some features may be limited.",
					"table-initialization",
				);
			}
		} catch (error) {
			ErrorHandler.showError(
				"Failed to initialize table management functionality",
				"table-initialization",
				error,
			);
		}
	}

	initializeUserSearchHandlers() {
		const shareModals = document.querySelectorAll(".modal[data-item-uuid]");

		if (shareModals.length === 0) {
			return;
		}

		if (!window.ShareActionManager || !window.PermissionsManager) {
			console.warn(
				"ShareActionManager or PermissionsManager not available. Share modals will not initialize.",
			);
			return;
		}

		const permConfig =
			window.filesSharePagePermissions || {
				userPermissionLevel: "owner",
				isOwner: true,
				currentUserId: 0,
				datasetPermissions: {
					canShare: true,
					canDownload: true,
					canEditMetadata: false,
					canAddAssets: false,
					canRemoveAnyAssets: false,
					canRemoveOwnAssets: false,
				},
			};

		const permissionsManager = new window.PermissionsManager(permConfig);

		for (const modal of shareModals) {
			this.setupShareActionManager(modal, permissionsManager);
		}
	}

	setupShareActionManager(modal, permissionsManager) {
		try {
			if (!this.boundHandlers) {
				this.boundHandlers = new Map();
			}
			if (!this.activeHandlers) {
				this.activeHandlers = new Set();
			}

			const itemUuid = modal.getAttribute("data-item-uuid");
			const itemType = modal.getAttribute("data-item-type");

			if (!this.validateModalAttributes(itemUuid, itemType)) {
				ErrorHandler.showError(
					"Invalid modal configuration",
					"user-search-setup",
				);
				return;
			}

			const shareManager = new window.ShareActionManager({
				itemUuid,
				itemType,
				permissions: permissionsManager,
			});
			modal.shareActionManager = shareManager;
			this.activeHandlers.add(shareManager);

			const onHidden = () => {
				modal.shareActionManager?.clearSelections?.();
			};

			modal.addEventListener("hidden.bs.modal", onHidden);
			this.boundHandlers.set(modal, { hiddenShare: onHidden });

			console.log(`ShareActionManager initialized for ${itemType}: ${itemUuid}`);
		} catch (error) {
			ErrorHandler.showError(
				"Failed to setup share modal",
				"user-search-setup",
				error,
			);
		}
	}

	/**
	 * Get initialized modal manager
	 * @returns {Object|null} - The modal manager instance
	 */
	getModalManager() {
		return this.modalManager;
	}

	/**
	 * Get captures table manager
	 * @returns {Object|null} - The captures table manager instance
	 */
	getCapturesTableManager() {
		return window.capturesTableManager;
	}

	// Validation methods
	validateModalAttributes(uuid, type) {
		if (!uuid || typeof uuid !== "string") {
			console.warn("Invalid UUID in modal attributes:", uuid);
			return false;
		}

		if (!type || typeof type !== "string") {
			console.warn("Invalid type in modal attributes:", type);
			return false;
		}

		// Validate UUID format (basic check)
		const uuidRegex =
			/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
		if (!uuidRegex.test(uuid)) {
			console.warn("Invalid UUID format in modal attributes:", uuid);
			return false;
		}

		// Validate type
		const validTypes = ["capture", "dataset", "file"];
		if (!validTypes.includes(type)) {
			console.warn("Invalid type in modal attributes:", type);
			return false;
		}

		return true;
	}

	// Memory management and cleanup
	cleanup() {
		for (const [element, handlers] of this.boundHandlers) {
			if (element?.removeEventListener) {
				if (handlers.hiddenShare) {
					element.removeEventListener("hidden.bs.modal", handlers.hiddenShare);
				}
				if (handlers.show) {
					element.removeEventListener("show.bs.modal", handlers.show);
				}
				if (handlers.hide) {
					element.removeEventListener("hidden.bs.modal", handlers.hide);
				}
			}
		}
		this.boundHandlers.clear();

		for (const handler of this.activeHandlers) {
			if (handler && typeof handler.clearSelections === "function") {
				try {
					handler.clearSelections();
				} catch (error) {
					console.warn("Error clearing share selections:", error);
				}
			}
		}
		this.activeHandlers.clear();

		console.log("FilesPageInitializer cleanup completed");
	}
}

if (typeof window !== "undefined") {
	window.FilesPageInitializer = FilesPageInitializer;
}
if (typeof module !== "undefined" && module.exports) {
	module.exports = { FilesPageInitializer };
}

