/**
 * Files UI Components
 * Manages capture type selection and page initialization
 */

// Error handling utilities
const ErrorHandler = {
	showError(message, context = "", error = null) {
		// Log error details for debugging
		if (error) {
			console.error(`FilesUI Error [${context}]:`, {
				message: error.message,
				stack: error.stack,
				userMessage: message,
				timestamp: new Date().toISOString(),
				userAgent: navigator.userAgent,
			});
		} else {
			console.warn(`FilesUI Warning [${context}]:`, message);
		}

		// Show user-friendly error message
		if (window.components?.showError) {
			window.components.showError(message);
		} else {
			// Fallback: show in console and try to display on page
			this.showFallbackError(message);
		}
	},

	showFallbackError(message) {
		// Try to find an error display area
		const errorContainer = document.querySelector(
			".error-container, .alert-container, .files-container",
		);
		if (errorContainer) {
			const errorDiv = document.createElement("div");
			errorDiv.className = "alert alert-danger alert-dismissible fade show";
			errorDiv.innerHTML = `
				${message}
				<button type="button" class="btn-close" data-bs-dismiss="alert"></button>
			`;
			errorContainer.insertBefore(errorDiv, errorContainer.firstChild);
		}
	},

	getUserFriendlyErrorMessage(error, context = "") {
		if (!error) return "An unexpected error occurred";

		// Handle common error types
		if (error.name === "TypeError" && error.message.includes("Cannot read")) {
			return "Configuration error: Some components are not properly loaded";
		}
		if (error.name === "ReferenceError") {
			return "Component error: Required functionality is not available";
		}

		// Default user-friendly message
		return error.message || "An unexpected error occurred";
	},
};

// Browser compatibility checker
const BrowserCompatibility = {
	checkRequiredFeatures() {
		const requiredFeatures = {
			"DOM API": "document" in window && "addEventListener" in document,
			"Console API": "console" in window && "log" in console,
			Map: "Map" in window,
			Set: "Set" in window,
			"Template Literals": (() => {
				try {
					// Test template literal support without eval
					const test = `test${1}`;
					return test === "test1";
				} catch {
					return false;
				}
			})(),
		};

		const missingFeatures = Object.entries(requiredFeatures)
			.filter(([name, supported]) => !supported)
			.map(([name]) => name);

		if (missingFeatures.length > 0) {
			console.warn("Missing browser features:", missingFeatures);
			return false;
		}

		return true;
	},

	checkBootstrapSupport() {
		return (
			"bootstrap" in window ||
			typeof bootstrap !== "undefined" ||
			document.querySelector("[data-bs-toggle]") !== null
		);
	},
};

/**
 * Capture Type Selection Handler
 * Manages capture type dropdown and conditional form fields
 */
class CaptureTypeSelector {
	constructor() {
		this.boundHandlers = new Map(); // Track event handlers for cleanup
		this.initializeElements();
		this.setupEventListeners();
	}

	initializeElements() {
		this.captureTypeSelect = document.getElementById("captureTypeSelect");
		this.channelInputGroup = document.getElementById("channelInputGroup");
		this.scanGroupInputGroup = document.getElementById("scanGroupInputGroup");
		this.captureChannelsInput = document.getElementById("captureChannelsInput");
		this.captureScanGroupInput = document.getElementById(
			"captureScanGroupInput",
		);
		this.uploadModal = document.getElementById("uploadCaptureModal");
		
		// Log which elements were found for debugging
		console.log("CaptureTypeSelector elements found:", {
			captureTypeSelect: !!this.captureTypeSelect,
			channelInputGroup: !!this.channelInputGroup,
			scanGroupInputGroup: !!this.scanGroupInputGroup,
			captureChannelsInput: !!this.captureChannelsInput,
			captureScanGroupInput: !!this.captureScanGroupInput,
			uploadModal: !!this.uploadModal
		});
	}

	setupEventListeners() {
		// Ensure boundHandlers is initialized
		if (!this.boundHandlers) {
			this.boundHandlers = new Map();
		}

		if (this.captureTypeSelect) {
			const changeHandler = (e) => this.handleTypeChange(e);
			this.boundHandlers.set(this.captureTypeSelect, changeHandler);
			this.captureTypeSelect.addEventListener("change", changeHandler);
		}

		if (this.uploadModal) {
			const hiddenHandler = () => this.resetForm();
			this.boundHandlers.set(this.uploadModal, hiddenHandler);
			this.uploadModal.addEventListener("hidden.bs.modal", hiddenHandler);
		}
	}

	handleTypeChange(event) {
		const selectedType = event.target.value;

		// Validate capture type
		if (!this.validateCaptureType(selectedType)) {
			ErrorHandler.showError(
				"Invalid capture type selected",
				"capture-type-validation",
			);
			return;
		}

		// Hide both input groups initially
		this.hideInputGroups();

		// Clear required attributes
		this.clearRequiredAttributes();

		// Show appropriate input group based on selection
		if (selectedType === "drf") {
			this.showChannelInput();
		} else if (selectedType === "rh") {
			this.showScanGroupInput();
		}
	}

	hideInputGroups() {
		if (this.channelInputGroup) {
			this.channelInputGroup.classList.add("hidden-input-group");
		}
		if (this.scanGroupInputGroup) {
			this.scanGroupInputGroup.classList.add("hidden-input-group");
		}
	}

	clearRequiredAttributes() {
		if (this.captureChannelsInput) {
			this.captureChannelsInput.removeAttribute("required");
		}
		if (this.captureScanGroupInput) {
			this.captureScanGroupInput.removeAttribute("required");
		}
	}

	showChannelInput() {
		if (this.channelInputGroup) {
			this.channelInputGroup.classList.remove("hidden-input-group");
		}
		if (this.captureChannelsInput) {
			this.captureChannelsInput.setAttribute("required", "required");
		}
	}

	showScanGroupInput() {
		if (this.scanGroupInputGroup) {
			this.scanGroupInputGroup.classList.remove("hidden-input-group");
		}
		// scan_group is optional for RadioHound captures, so no required attribute
	}

	// Input validation methods
	validateCaptureType(type) {
		const validTypes = ["drf", "rh"];
		return validTypes.includes(type);
	}

	validateChannelInput(channels) {
		if (!channels || typeof channels !== "string") return false;
		// Basic validation for channel input (can be enhanced based on requirements)
		return channels.trim().length > 0 && channels.length <= 1000;
	}

	validateScanGroupInput(scanGroup) {
		if (!scanGroup || typeof scanGroup !== "string") return false;
		// Basic validation for scan group input
		return scanGroup.trim().length > 0 && scanGroup.length <= 255;
	}

	sanitizeInput(input) {
		if (!input || typeof input !== "string") return "";
		// Remove potentially dangerous characters
		return input.replace(/[<>:"/\\|?*]/g, "_").trim();
	}

	// Memory management and cleanup
	cleanup() {
		// Remove all bound event handlers
		for (const [element, handler] of this.boundHandlers) {
			if (element?.removeEventListener) {
				element.removeEventListener("change", handler);
				element.removeEventListener("hidden.bs.modal", handler);
			}
		}
		this.boundHandlers.clear();
		console.log("CaptureTypeSelector cleanup completed");
	}

	resetForm() {
		// Reset the form
		const form = document.getElementById("uploadCaptureForm");
		if (form) {
			form.reset();
		}

		// Hide input groups
		this.hideInputGroups();

		// Clear required attributes
		this.clearRequiredAttributes();

		// Clear global variables if they exist
		this.cleanupGlobalState();
	}

	// Better global state management
	cleanupGlobalState() {
		const globalVars = ["filesToSkip", "fileCheckResults", "selectedFiles"];

		for (const varName of globalVars) {
			if (window[varName]) {
				if (typeof window[varName].clear === "function") {
					window[varName].clear();
				} else if (Array.isArray(window[varName])) {
					window[varName].length = 0;
				} else {
					window[varName] = null;
				}
				console.log(`Cleaned up global variable: ${varName}`);
			}
		}
	}
}

/**
 * Files Page Initialization
 * Initializes modal managers, capture handlers, and user search components
 */
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
		// Create a UserSearchHandler for each share modal
		const shareModals = document.querySelectorAll(".modal[data-item-uuid]");

		for (const modal of shareModals) {
			this.setupUserSearchHandler(modal);
		}
	}

	setupUserSearchHandler(modal) {
		try {
			// Ensure boundHandlers and activeHandlers are initialized
			if (!this.boundHandlers) {
				this.boundHandlers = new Map();
			}
			if (!this.activeHandlers) {
				this.activeHandlers = new Set();
			}

			// Validate modal attributes
			const itemUuid = modal.getAttribute("data-item-uuid");
			const itemType = modal.getAttribute("data-item-type");

			if (!this.validateModalAttributes(itemUuid, itemType)) {
				ErrorHandler.showError(
					"Invalid modal configuration",
					"user-search-setup",
				);
				return;
			}

			if (!window.UserSearchHandler) {
				ErrorHandler.showError(
					"User search functionality is not available",
					"user-search-setup",
				);
				return;
			}

			const handler = new window.UserSearchHandler();
			// Store the handler on the modal element
			modal.userSearchHandler = handler;
			this.activeHandlers.add(handler);

			// Create bound event handlers for cleanup
			const showHandler = () => {
				if (modal.userSearchHandler) {
					modal.userSearchHandler.setItemInfo(itemUuid, itemType);
					modal.userSearchHandler.init();
				}
			};

			const hideHandler = () => {
				if (modal.userSearchHandler) {
					modal.userSearchHandler.resetAll();
				}
			};

			// Store handlers for cleanup
			this.boundHandlers.set(modal, { show: showHandler, hide: hideHandler });

			// On modal show, set the item info and call init()
			modal.addEventListener("show.bs.modal", showHandler);

			// On modal hide, reset all selections and entered data
			modal.addEventListener("hidden.bs.modal", hideHandler);

			console.log(`UserSearchHandler initialized for ${itemType}: ${itemUuid}`);
		} catch (error) {
			ErrorHandler.showError(
				"Failed to setup user search functionality",
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
		// Remove all bound event handlers
		for (const [element, handlers] of this.boundHandlers) {
			if (element?.removeEventListener) {
				if (handlers.show) {
					element.removeEventListener("show.bs.modal", handlers.show);
				}
				if (handlers.hide) {
					element.removeEventListener("hidden.bs.modal", handlers.hide);
				}
			}
		}
		this.boundHandlers.clear();

		// Cleanup active handlers
		for (const handler of this.activeHandlers) {
			if (handler && typeof handler.cleanup === "function") {
				try {
					handler.cleanup();
				} catch (error) {
					console.warn("Error during handler cleanup:", error);
				}
			}
		}
		this.activeHandlers.clear();

		console.log("FilesPageInitializer cleanup completed");
	}
}

// Initialize when DOM is loaded
document.addEventListener("DOMContentLoaded", () => {
	// Check browser compatibility before proceeding
	if (!BrowserCompatibility.checkRequiredFeatures()) {
		ErrorHandler.showError(
			"Your browser doesn't support required features. Please use a modern browser.",
			"browser-compatibility",
		);
		return;
	}

	// Check Bootstrap support
	if (!BrowserCompatibility.checkBootstrapSupport()) {
		console.warn(
			"Bootstrap not detected. Some UI features may not work properly.",
		);
	}

	try {
		// Check if we're on a page that needs these components
		const needsCaptureSelector = document.getElementById("captureTypeSelect") || 
								   document.getElementById("uploadCaptureModal");
		const needsPageInitializer = document.querySelector(".modal[data-item-uuid]") ||
								   document.getElementById("capture-modal");

		// Initialize capture type selector only if needed
		let captureSelector = null;
		if (needsCaptureSelector) {
			captureSelector = new CaptureTypeSelector();
		}

		// Initialize page components only if needed
		let filesPageInitializer = null;
		if (needsPageInitializer) {
			filesPageInitializer = new FilesPageInitializer();
			window.filesPageInitializer = filesPageInitializer;
		}

		// Store references for cleanup
		window.filesUICleanup = () => {
			if (captureSelector && typeof captureSelector.cleanup === "function") {
				captureSelector.cleanup();
			}
			if (
				filesPageInitializer &&
				typeof filesPageInitializer.cleanup === "function"
			) {
				filesPageInitializer.cleanup();
			}
		};

		console.log("Files UI initialized successfully", {
			captureSelector: !!captureSelector,
			pageInitializer: !!filesPageInitializer
		});
	} catch (error) {
		ErrorHandler.showError(
			"Failed to initialize Files UI components",
			"initialization",
			error,
		);
	}
});
