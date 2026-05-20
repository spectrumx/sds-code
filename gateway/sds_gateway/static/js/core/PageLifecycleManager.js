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
		this._captureDetailsModalCleanup = null;

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
			case "published-datasets-list":
				this.initializePublishedDatasetsListPage();
				break;
			default:
				console.warn(`Unknown page type: ${this.pageType}`);
		}
	}

	/**
	 * Initialize dataset create page
	 */
	_initDatasetModeAndSearch(afterInit) {
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
		this.initializeSearchHandlers();
		afterInit?.();
	}

	initializeDatasetCreatePage() {
		this._initDatasetModeAndSearch();
	}

	/**
	 * Initialize dataset edit page
	 */
	initializeDatasetEditPage() {
		this._initDatasetModeAndSearch(() => {
			if (this.config.dataset?.datasetUuid && window.ShareActionManager) {
				this.shareActionManager = new window.ShareActionManager({
					itemUuid: this.config.dataset.datasetUuid,
					itemType: "dataset",
					permissions: this.permissions,
				});
				this.managers.push(this.shareActionManager);
			}
		});
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

		this.ensureCaptureDetailsModal();
	}

	/**
	 * Global asset details modal (#asset-details-modal) + delegated clicks.
	 */
	ensureCaptureDetailsModal() {
		if (this._captureDetailsModalCleanup || !window.ModalManager?.initFilesPageCaptureModals) {
			return;
		}
		if (!this.config.permissions) {
			return;
		}
		this._captureDetailsModalCleanup = window.ModalManager.initFilesPageCaptureModals({
			permissions: this.config.permissions,
		});
		this.managers.push({
			cleanup: () => {
				this._captureDetailsModalCleanup?.();
				this._captureDetailsModalCleanup = null;
			},
		});
	}

	/**
	 * Published datasets search page: pagination + dataset modals (same modal wiring as dataset list, no sort UI).
	 */
	initializePublishedDatasetsListPage() {
		this.initializePagination();
		this.initializeDatasetModals();
	}

	/**
	 * Single DownloadActionManager for document-wide .web-download-btn / SDK buttons (not per modal).
	 */
	ensureDownloadActionManager() {
		if (
			this.downloadActionManager ||
			!this.permissions ||
			!window.DownloadActionManager
		) {
			return;
		}
		this.downloadActionManager = new window.DownloadActionManager({
			permissions: this.permissions,
		});
		this.managers.push(this.downloadActionManager);
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
		const containerIds = [
			"captures-pagination",
			"datasets-pagination",
			"files-pagination",
		];
		const onPageChange = (page) => {
			const urlParams = new URLSearchParams(window.location.search);
			urlParams.set("page", String(page));
			window.location.search = urlParams.toString();
		};

		for (const containerId of containerIds) {
			PageLifecycleManager.wireServerRenderedPagination(
				containerId,
				onPageChange,
			);
		}
	}

	/**
	 * Initialize dataset modals
	 */
	initializeDatasetModals() {
		window.ModalManager.wireDatasetListModals(this.permissions, this.managers);
		this.ensureDownloadActionManager();
		const detachDetails =
			window.ModalManager?.ensureDetailsModalClickDelegation?.();
		if (detachDetails) {
			this.managers.push({ cleanup: detachDetails });
		}
	}

	/**
	 * Initialize capture modals
	 */
	initializeCaptureModals() {
		window.ModalManager.wireCaptureListModals(this.permissions, this.managers);
		this.ensureDownloadActionManager();
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

		// Do not dispose Bootstrap modals here. Disposing all modals before initialize()
		// runs creates a gap where getOrCreateInstance can return a disposed instance
		// (_config undefined). Modals are disposed and re-created per-element in
		// initializeDatasetModals() so there is no gap.

		// Clear manager references from modal elements so re-init creates fresh managers
		const datasetModals = document.querySelectorAll(
			".modal[data-item-type='dataset']",
		);
		for (const modal of datasetModals) {
			modal.shareActionManager = undefined;
			modal.versioningActionManager = undefined;
			modal.downloadActionManager = undefined;
			modal.detailsActionManager = undefined;
		}
		const captureModals = document.querySelectorAll(
			".modal[data-item-type='capture']",
		);
		for (const modal of captureModals) {
			modal.shareActionManager = undefined;
			modal.downloadActionManager = undefined;
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

	/**
	 * Wire server-rendered Bootstrap pagination links (data-page + .page-link).
	 * @param {string} containerId
	 * @param {(page: number) => void} onPageChange
	 */
	static wireServerRenderedPagination(containerId, onPageChange) {
		const el = document.getElementById(containerId);
		if (!el || typeof onPageChange !== "function") return;

		const links = el.querySelectorAll(".pagination a.page-link");
		for (const link of links) {
			if (link.dataset.paginationSetup === "true") continue;
			link.dataset.paginationSetup = "true";
			link.addEventListener("click", (e) => {
				e.preventDefault();
				const p = Number.parseInt(link.getAttribute("data-page") || "", 10);
				if (p) onPageChange(p);
			});
		}
	}
}

// Make class available globally
window.PageLifecycleManager = PageLifecycleManager;

// Export for ES6 modules (Jest testing) - only if in module context
if (typeof module !== "undefined" && module.exports) {
	module.exports = { PageLifecycleManager };
}
