/**
 * Page Lifecycle Manager
 * Manages initialization, cleanup, and lifecycle of page components
 */
class PageLifecycleManager {
	/**
	 * Initialize page lifecycle manager
	 * @param {Object} config - Configuration object
	 */
	constructor(config) {
		this.pageType = config.pageType; // 'dataset-create', 'dataset-edit', 'dataset-list', etc.
		this.managers = [];
		this.initialized = false;
		this.config = config;

		// Core managers
		this.permissions = null;
		this.datasetModeManager = null;
		this.shareActionManager = null;
		this.downloadActionManager = null;
		this.detailsActionManager = null;

		// Initialize when DOM is ready
		if (document.readyState === "loading") {
			document.addEventListener("DOMContentLoaded", () => this.initialize());
		} else {
			this.initialize();
		}
	}

	/**
	 * Initialize all managers and components
	 */
	initialize() {
		if (this.initialized) {
			console.warn("PageLifecycleManager already initialized");
			return;
		}

		try {
			// Initialize core managers first
			this.initializeCoreManagers();

			// Initialize page-specific managers
			this.initializePageSpecificManagers();

			// Initialize global event listeners
			this.initializeGlobalEventListeners();

			// Mark as initialized
			this.initialized = true;
		} catch (error) {
			console.error("Error initializing PageLifecycleManager:", error);
		}
	}

	/**
	 * Initialize core managers
	 */
	initializeCoreManagers() {
		// Initialize permissions manager
		if (this.config.permissions && window.PermissionsManager) {
			this.permissions = new window.PermissionsManager(this.config.permissions);
			this.managers.push(this.permissions);
		}
	}

	/**
	 * Initialize page-specific managers
	 */
	initializePageSpecificManagers() {
		switch (this.pageType) {
			case "dataset-create":
				this.initializeDatasetCreatePage();
				break;
			case "dataset-edit":
				this.initializeDatasetEditPage();
				break;
			case "dataset-list":
				this.initializeDatasetListPage();
				break;
			case "capture-list":
				this.initializeCaptureListPage();
				break;
			default:
				console.warn(`Unknown page type: ${this.pageType}`);
		}
	}

	/**
	 * Initialize dataset create page
	 */
	initializeDatasetCreatePage() {
		// Initialize dataset mode manager for creation
		if (window.DatasetModeManager) {
			this.datasetModeManager = new window.DatasetModeManager({
				...this.config.dataset,
				userPermissionLevel: this.config.permissions?.userPermissionLevel,
				currentUserId: this.config.permissions?.currentUserId,
				isOwner: this.config.permissions?.isOwner,
				datasetPermissions: this.config.permissions?.datasetPermissions,
			});
		}
		this.managers.push(this.datasetModeManager);

		// Initialize search handlers
		this.initializeSearchHandlers();
	}

	/**
	 * Initialize dataset edit page
	 */
	initializeDatasetEditPage() {
		// Initialize dataset mode manager for editing
		if (window.DatasetModeManager) {
			this.datasetModeManager = new window.DatasetModeManager({
				...this.config.dataset,
				userPermissionLevel: this.config.permissions?.userPermissionLevel,
				currentUserId: this.config.permissions?.currentUserId,
				isOwner: this.config.permissions?.isOwner,
				datasetPermissions: this.config.permissions?.datasetPermissions,
			});
		}
		this.managers.push(this.datasetModeManager);

		// Initialize search handlers
		this.initializeSearchHandlers();

		// Initialize share action manager for the dataset
		if (this.config.dataset?.datasetUuid && window.ShareActionManager) {
			this.shareActionManager = new window.ShareActionManager({
				itemUuid: this.config.dataset.datasetUuid,
				itemType: "dataset",
				permissions: this.permissions,
			});
			this.managers.push(this.shareActionManager);
		}
	}

	/**
	 * Initialize dataset list page
	 */
	initializeDatasetListPage() {
		// Initialize sort functionality
		this.initializeSortFunctionality();

		// Initialize pagination
		this.initializePagination();

		// Initialize modals for each dataset
		this.initializeDatasetModals();
	}

	/**
	 * Initialize capture list page
	 */
	initializeCaptureListPage() {
		// Initialize sort functionality
		this.initializeSortFunctionality();

		// Initialize pagination
		this.initializePagination();

		// Initialize modals for each capture
		this.initializeCaptureModals();
	}

	/**
	 * Initialize search handlers
	 */
	initializeSearchHandlers() {
		// Initialize captures search handler
		if (window.SearchHandler) {
			const capturesSearchHandler = new window.SearchHandler({
				searchFormId: "captures-search-form",
				searchButtonId: "search-captures",
				clearButtonId: "clear-captures-search",
				tableBodyId: "captures-table-body",
				paginationContainerId: "captures-pagination",
				type: "captures",
				formHandler: this.datasetModeManager?.getHandler(),
				isEditMode: this.datasetModeManager?.isInEditMode() || false,
			});
			this.managers.push(capturesSearchHandler);
		}

		// Initialize files search handler
		if (window.SearchHandler) {
			const filesSearchHandler = new window.SearchHandler({
				searchFormId: "files-search-form",
				searchButtonId: "search-files",
				clearButtonId: "clear-files-search",
				tableBodyId: "file-tree-table",
				paginationContainerId: "files-pagination",
				type: "files",
				formHandler: this.datasetModeManager?.getHandler(),
				isEditMode: this.datasetModeManager?.isInEditMode() || false,
			});
			this.managers.push(filesSearchHandler);
		}
	}

	/**
	 * Initialize sort functionality
	 */
	initializeSortFunctionality() {
		const sortableHeaders = document.querySelectorAll("th.sortable");

		for (const header of sortableHeaders) {
			// Prevent duplicate event listener attachment
			if (header.dataset.sortSetup === "true") {
				continue;
			}
			header.dataset.sortSetup = "true";

			header.style.cursor = "pointer";
			header.addEventListener("click", () => {
				const sortField = header.getAttribute("data-sort");
				const urlParams = new URLSearchParams(window.location.search);
				let newOrder = "desc";

				// If already sorting by this field, toggle order
				if (
					urlParams.get("sort_by") === sortField &&
					urlParams.get("sort_order") === "asc"
				) {
					newOrder = "desc";
				}

				// Update URL with new sort parameters
				urlParams.set("sort_by", sortField);
				urlParams.set("sort_order", newOrder);
				urlParams.set("page", "1"); // Reset to first page when sorting

				// Navigate to sorted results
				window.location.search = urlParams.toString();
			});
		}
	}

	/**
	 * Initialize pagination
	 */
	initializePagination() {
		const paginationLinks = document.querySelectorAll(
			".pagination a.page-link",
		);

		for (const link of paginationLinks) {
			// Prevent duplicate event listener attachment
			if (link.dataset.paginationSetup === "true") {
				continue;
			}
			link.dataset.paginationSetup = "true";

			link.addEventListener("click", (e) => {
				e.preventDefault();
				const page = link.getAttribute("data-page");
				if (page) {
					const urlParams = new URLSearchParams(window.location.search);
					urlParams.set("page", page);
					window.location.search = urlParams.toString();
				}
			});
		}
	}

	/**
	 * Initialize dataset modals
	 */
	initializeDatasetModals() {
		// Pre-initialize all modals on the page with proper config to prevent Bootstrap auto-initialization errors
		const allModals = document.querySelectorAll('.modal');
		for (const modal of allModals) {
			if (window.bootstrap) {
				// Dispose any existing instance that might be in a bad state
				const existingInstance = bootstrap.Modal.getInstance(modal);
				if (existingInstance) {
					try {
						existingInstance.dispose();
					} catch (e) {
						// If disposal fails, the instance is already broken - continue
						console.warn('Failed to dispose modal instance:', e);
					}
				}
				
				// Create a new instance with proper config
				new bootstrap.Modal(modal, {
					backdrop: true,
					keyboard: true,
					focus: true,
				});
			}
		}

		const datasetModals = document.querySelectorAll(
			".modal[data-item-type='dataset']",
		);

		for (const modal of datasetModals) {
			const itemUuid = modal.getAttribute("data-item-uuid");

			if (!itemUuid || !this.permissions) {
				console.warn(
					`No item UUID or permissions found for dataset modal: ${modal}`,
				);
				continue;
			}

			if (window.ShareActionManager) {
				const shareManager = new window.ShareActionManager({
					itemUuid: itemUuid,
					itemType: "dataset",
					permissions: this.permissions,
				});
				this.managers.push(shareManager);

				// Store reference on modal
				modal.shareActionManager = shareManager;
			}

			if (window.VersioningActionManager) {
				// Check if manager already exists to prevent duplicate initialization
				if (!modal.versioningActionManager) {
					const versioningManager = new window.VersioningActionManager({
						datasetUuid: itemUuid,
						permissions: this.permissions,
					});
					this.managers.push(versioningManager);

					// Store reference on modal
					modal.versioningActionManager = versioningManager;
				}
			}

			if (window.DownloadActionManager) {
				const downloadManager = new window.DownloadActionManager({
					permissions: this.permissions,
				});
				this.managers.push(downloadManager);

				// Store reference on modal
				modal.downloadActionManager = downloadManager;
			}

			if (window.DetailsActionManager) {
				const detailsManager = new window.DetailsActionManager({
					permissions: this.permissions,
					itemUuid: itemUuid,
					itemType: "dataset",
				});
				this.managers.push(detailsManager);

				// Store reference on modal
				modal.detailsActionManager = detailsManager;
			}
		}
	}

	/**
	 * Initialize capture modals
	 */
	initializeCaptureModals() {
		const captureModals = document.querySelectorAll(
			".modal[data-item-type='capture']",
		);

		for (const modal of captureModals) {
			const itemUuid = modal.getAttribute("data-item-uuid");

			if (!itemUuid || !this.permissions) {
				console.warn(
					`No item UUID or permissions found for capture modal: ${modal}`,
				);
				continue;
			}

			if (window.ShareActionManager) {
				const shareManager = new window.ShareActionManager({
					itemUuid: itemUuid,
					itemType: "capture",
					permissions: this.permissions,
				});
				this.managers.push(shareManager);

				// Store reference on modal
				modal.shareActionManager = shareManager;
			}

			if (window.DownloadActionManager) {
				const downloadManager = new window.DownloadActionManager({
					itemUuid: itemUuid,
					itemType: "capture",
					permissions: this.permissions,
				});
				this.managers.push(downloadManager);

				// Store reference on modal
				modal.downloadActionManager = downloadManager;
			}
		}
	}

	/**
	 * Initialize global event listeners
	 */
	initializeGlobalEventListeners() {
		// Handle window beforeunload for cleanup
		window.addEventListener("beforeunload", () => {
			this.cleanup();
		});
	}

	/**
	 * Get manager by type
	 * @param {string} type - Manager type
	 * @returns {Object|null} Manager instance
	 */
	getManager(type) {
		switch (type) {
			case "permissions":
				return this.permissions;
			case "datasetMode":
				return this.datasetModeManager;
			case "shareAction":
				return this.shareActionManager;
			case "downloadAction":
				return this.downloadActionManager;
			case "detailsAction":
				return this.detailsActionManager;
			default:
				return this.managers.find(
					(manager) => manager.constructor.name === type,
				);
		}
	}

	/**
	 * Add manager
	 * @param {Object} manager - Manager instance
	 */
	addManager(manager) {
		this.managers.push(manager);
	}

	/**
	 * Remove manager
	 * @param {Object} manager - Manager instance to remove
	 */
	removeManager(manager) {
		const index = this.managers.indexOf(manager);
		if (index > -1) {
			this.managers.splice(index, 1);
		}
	}

	/**
	 * Update configuration
	 * @param {Object} newConfig - New configuration
	 */
	updateConfig(newConfig) {
		this.config = { ...this.config, ...newConfig };

		// Update permissions if provided
		if (newConfig.permissions && this.permissions) {
			this.permissions.updateDatasetPermissions(newConfig.permissions);
		}
	}

	/**
	 * Refresh page components
	 */
	async refresh() {
		try {
			// Clean up existing managers
			this.cleanup();

			// Reinitialize
			this.initialized = false;
			this.managers = [];
			await this.initialize();
		} catch (error) {
			console.error("Error refreshing page components:", error);
		}
	}

	/**
	 * Cleanup all managers and resources
	 */
	cleanup() {
		// Cleanup all managers
		for (const manager of this.managers) {
			if (manager.cleanup && typeof manager.cleanup === "function") {
				try {
					manager.cleanup();
				} catch (error) {
					console.error("Error cleaning up manager:", error);
				}
			}
		}

		// Dispose all Bootstrap modal instances to prevent bad state
		if (window.bootstrap && bootstrap.Modal) {
			const allModals = document.querySelectorAll('.modal');
			for (const modal of allModals) {
				const instance = bootstrap.Modal.getInstance(modal);
				if (instance) {
					try {
						instance.dispose();
					} catch (error) {
						// If disposal fails, the instance is already broken - continue
						console.warn('Failed to dispose modal during cleanup:', error);
					}
				}
			}
		}

		// Clear manager references
		this.managers = [];
		this.permissions = null;
		this.datasetModeManager = null;
		this.shareActionManager = null;
		this.downloadActionManager = null;
		this.detailsActionManager = null;

		// Remove global event listeners
		window.removeEventListener("beforeunload", this.cleanup);

		this.initialized = false;
	}

	/**
	 * Debounce function
	 * @param {Function} func - Function to debounce
	 * @param {number} wait - Wait time in milliseconds
	 * @returns {Function} Debounced function
	 */
	debounce(func, wait) {
		let timeout;
		return function executedFunction(...args) {
			const later = () => {
				clearTimeout(timeout);
				func(...args);
			};
			clearTimeout(timeout);
			timeout = setTimeout(later, wait);
		};
	}

	/**
	 * Get page status
	 * @returns {Object} Page status information
	 */
	getStatus() {
		return {
			initialized: this.initialized,
			pageType: this.pageType,
			managersCount: this.managers.length,
			managers: this.managers.map((manager) => manager.constructor.name),
		};
	}

	/**
	 * Check if manager is initialized
	 * @param {string} type - Manager type
	 * @returns {boolean} Whether manager is initialized
	 */
	isManagerInitialized(type) {
		return this.getManager(type) !== null;
	}

	/**
	 * Wait for manager to be initialized
	 * @param {string} type - Manager type
	 * @param {number} timeout - Timeout in milliseconds
	 * @returns {Promise<Object>} Manager instance
	 */
	async waitForManager(type, timeout = 5000) {
		return new Promise((resolve, reject) => {
			const startTime = Date.now();

			const checkManager = () => {
				const manager = this.getManager(type);
				if (manager) {
					resolve(manager);
				} else if (Date.now() - startTime > timeout) {
					reject(
						new Error(`Manager ${type} not initialized within ${timeout}ms`),
					);
				} else {
					setTimeout(checkManager, 100);
				}
			};

			checkManager();
		});
	}
}

// Make class available globally
window.PageLifecycleManager = PageLifecycleManager;

// Export for ES6 modules (Jest testing) - only if in module context
if (typeof module !== "undefined" && module.exports) {
	module.exports = { PageLifecycleManager };
}
